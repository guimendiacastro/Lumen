# lumen/api/app/routers/files.py
"""
File upload and management with new RAG service
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import text

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, member_session
from ..crypto.vault import encrypt_text, decrypt_text
from ..services.file_processor import FileProcessor
from ..services.rag_service import get_rag_service

log = logging.getLogger("lumen.ai")
router = APIRouter(prefix="/files", tags=["files"])

MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB


class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    size_bytes: int
    use_direct_context: bool
    chunk_count: int
    status: str


class FileMetadata(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    use_direct_context: bool
    created_at: str


async def _get_mapping_or_404(idn: Identity):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    return mapping


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    document_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
    idn: Identity = Depends(get_identity)
):
    """
    Upload and process file with new RAG system
    """
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]
    user_id = idn.user_id
    
    # Read file
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # Process file
    try:
        result = FileProcessor.process_file(
            content,
            file.content_type or "application/octet-stream"
        )
        log.info(f"File processed: use_direct={result.use_direct_context}, size={result.total_size}")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process file: {str(e)}"
        )
    
    # Encrypt full text
    content_enc = await encrypt_text(key_id, result.full_text)
    
    # Store file record
    file_id = str(uuid.uuid4())
    
    async with member_session(schema) as s:
        await s.execute(
            text("""
                INSERT INTO uploaded_files 
                (id, document_id, thread_id, filename, mime_type, file_size_bytes, 
                 storage_path, content_enc, status, created_by)
                VALUES (:id, :doc_id, :thread_id, :filename, :mime, :size, 
                        :path, :content, :status, :by)
            """),
            {
                "id": file_id,
                "doc_id": document_id,
                "thread_id": thread_id,
                "filename": file.filename or "unnamed",
                "mime": file.content_type or "application/octet-stream",
                "size": len(content),
                "path": f"local/{file_id}",
                "content": content_enc,
                "status": "processing",
                "by": user_id
            }
        )
        await s.commit()
    
    # Index with RAG if needed
    chunk_count = 0
    if not result.use_direct_context:
        try:
            rag_service = get_rag_service()
            chunk_count = await rag_service.index_document(
                file_id=file_id,
                text=result.full_text,
                metadata={
                    "filename": file.filename or "unnamed",
                    "mime_type": file.content_type,
                    "size": result.total_size
                }
            )
            log.info(f"Indexed {chunk_count} chunks for file {file_id}")
        except Exception as e:
            log.error(f"RAG indexing failed: {e}")
            # Mark as failed
            async with member_session(schema) as s:
                await s.execute(
                    text("UPDATE uploaded_files SET status = 'error' WHERE id = :id"),
                    {"id": file_id}
                )
                await s.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to index document: {str(e)}"
            )
    
    # Mark as ready
    async with member_session(schema) as s:
        await s.execute(
            text("""
                UPDATE uploaded_files 
                SET status = 'ready', processed_at = now()
                WHERE id = :id
            """),
            {"id": file_id}
        )
        await s.commit()
    
    return FileUploadResponse(
        file_id=file_id,
        filename=file.filename or "unnamed",
        size_bytes=len(content),
        use_direct_context=result.use_direct_context,
        chunk_count=chunk_count,
        status="ready"
    )


@router.get("/thread/{thread_id}", response_model=List[FileMetadata])
async def list_files_in_thread(
    thread_id: str,
    idn: Identity = Depends(get_identity)
):
    """List all files in a thread"""
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    
    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                SELECT 
                    id, filename, mime_type, file_size_bytes, 
                    status, created_at
                FROM uploaded_files
                WHERE thread_id = :tid
                ORDER BY created_at DESC
            """),
            {"tid": thread_id}
        )
        
        files = []
        for row in result:
            # Determine if direct context based on size
            use_direct = row[3] <= 50000  # Approximate
            
            files.append(FileMetadata(
                id=str(row[0]),
                filename=row[1],
                mime_type=row[2],
                size_bytes=row[3],
                status=row[4],
                use_direct_context=use_direct,
                created_at=row[5].isoformat()
            ))
        
        return files


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    idn: Identity = Depends(get_identity)
):
    """Delete a file and its RAG index"""
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    
    # Delete from database
    async with member_session(schema) as s:
        await s.execute(
            text("DELETE FROM uploaded_files WHERE id = :id"),
            {"id": file_id}
        )
        await s.commit()
    
    # Delete RAG index
    try:
        rag_service = get_rag_service()
        await rag_service.delete_file_index(file_id)
    except Exception as e:
        log.warning(f"Could not delete RAG index for {file_id}: {e}")
    
    return {"status": "deleted", "file_id": file_id}