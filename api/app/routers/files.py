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
from ..services.azure_rag_service import get_rag_service

log = logging.getLogger("lumen.ai")
router = APIRouter(prefix="/files", tags=["files"])

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB


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
    indexed: bool = False  # Whether chunks exist in Azure AI Search
    chunk_count: int = 0  # Number of indexed chunks
    error_message: str | None = None  # Error details if status='error'


class FileIndexingStatus(BaseModel):
    file_id: str
    filename: str
    upload_status: str  # Database status: processing, ready, error
    indexed: bool  # Whether chunks exist in Azure AI Search
    chunk_count: int  # Number of indexed chunks
    indexing_note: str  # Information about indexing process


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
    
    # Process file (now async to support OCR)
    try:
        result = await FileProcessor.process_file(
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
            log.info(f"Indexing file {file_id} with Azure AI Search")

            upload_result = await rag_service.upload_document(
                file_id=file_id,
                org_id=idn.org_id,
                user_id=user_id,
                content=result.full_text,
                filename=file.filename or "unnamed"
            )

            # Get chunk count from upload result
            chunk_count = upload_result.get("chunk_count", 0)
            log.info(f"Indexed {chunk_count} chunks for file {file_id}. {upload_result.get('note', '')}")
        except Exception as e:
            log.error(f"RAG indexing failed: {e}")
            error_msg = str(e)[:500]  # Limit to 500 chars
            # Mark as failed with error message
            async with member_session(schema) as s:
                await s.execute(
                    text("UPDATE uploaded_files SET status = 'error', error_message = :msg WHERE id = :id"),
                    {"id": file_id, "msg": error_msg}
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
    """List all files in a thread with indexing status"""
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    org_id = idn.org_id
    user_id = idn.user_id

    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                SELECT
                    id, filename, mime_type, file_size_bytes,
                    status, created_at, error_message
                FROM uploaded_files
                WHERE thread_id = :tid
                ORDER BY created_at DESC
            """),
            {"tid": thread_id}
        )

        files = []
        rag_service = get_rag_service()

        for row in result:
            file_id = str(row[0])
            # Determine if direct context based on size
            use_direct = row[3] <= 50000  # Approximate

            # Check indexing status for non-direct files
            indexed = False
            chunk_count = 0
            if not use_direct:
                try:
                    rag_status = await rag_service.get_document_status(
                        file_id=file_id,
                        org_id=org_id,
                        user_id=user_id
                    )
                    indexed = rag_status["indexed"]
                    chunk_count = rag_status["chunk_count"]
                except Exception as e:
                    log.warning(f"Could not check indexing status for {file_id}: {e}")

            files.append(FileMetadata(
                id=file_id,
                filename=row[1],
                mime_type=row[2],
                size_bytes=row[3],
                status=row[4],
                use_direct_context=use_direct,
                created_at=row[5].isoformat(),
                indexed=indexed,
                chunk_count=chunk_count,
                error_message=row[6]  # Include error message
            ))

        return files


@router.get("/{file_id}/status", response_model=FileIndexingStatus)
async def get_file_indexing_status(
    file_id: str,
    idn: Identity = Depends(get_identity)
):
    """Check the indexing status of a file in Azure AI Search"""
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    user_id = idn.user_id
    org_id = idn.org_id

    # Get file info from database
    async with member_session(schema) as s:
        result = await s.execute(
            text("SELECT filename, status, created_by FROM uploaded_files WHERE id = :id"),
            {"id": file_id}
        )
        row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    filename = row[0]
    upload_status = row[1]
    file_owner = row[2]

    # Security: Only allow owner to check status
    if file_owner != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this file"
        )

    # Check Azure AI Search indexing status
    try:
        rag_service = get_rag_service()
        rag_status = await rag_service.get_document_status(
            file_id=file_id,
            org_id=org_id,
            user_id=user_id
        )

        indexed = rag_status["indexed"]
        chunk_count = rag_status["chunk_count"]
        indexing_note = rag_status["note"]

    except Exception as e:
        log.error(f"Error checking RAG status for {file_id}: {e}")
        indexed = False
        chunk_count = 0
        indexing_note = f"Error checking indexing status: {str(e)}"

    return FileIndexingStatus(
        file_id=file_id,
        filename=filename,
        upload_status=upload_status,
        indexed=indexed,
        chunk_count=chunk_count,
        indexing_note=indexing_note
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    idn: Identity = Depends(get_identity)
):
    """Delete a file and its RAG index with ownership verification"""
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    user_id = idn.user_id
    org_id = idn.org_id

    # Security: Verify the user owns this file before deletion
    async with member_session(schema) as s:
        result = await s.execute(
            text("SELECT created_by FROM uploaded_files WHERE id = :id"),
            {"id": file_id}
        )
        row = result.first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )

        file_owner = row[0]
        if file_owner != user_id:
            log.warning(f"User {user_id} attempted to delete file {file_id} owned by {file_owner}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this file"
            )

    # Delete from database
    async with member_session(schema) as s:
        await s.execute(
            text("DELETE FROM uploaded_files WHERE id = :id AND created_by = :user"),
            {"id": file_id, "user": user_id}
        )
        await s.commit()

    # Delete RAG index with security parameters
    try:
        rag_service = get_rag_service()
        await rag_service.delete_document(
            file_id=file_id,
            org_id=org_id,
            user_id=user_id
        )
        log.info(f"Deleted RAG index for file {file_id}")
    except Exception as e:
        log.warning(f"Could not delete RAG index for {file_id}: {e}")

    return {"status": "deleted", "file_id": file_id}


@router.get("/indexer-status")
async def get_indexer_debug_status(idn: Identity = Depends(get_identity)):
    """
    Debug endpoint to check Azure AI Search indexer status and errors.
    Helps diagnose why files aren't being indexed.
    """
    try:
        rag_service = get_rag_service()
        status = await rag_service.get_indexer_status()
        return status
    except Exception as e:
        log.error(f"Error getting indexer status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get indexer status: {str(e)}"
        )


@router.post("/{file_id}/retry-indexing")
async def retry_file_indexing(
    file_id: str,
    idn: Identity = Depends(get_identity)
):
    """
    Retry indexing for a file that failed or is stuck in processing.
    Only works for files with status='error' or stuck in 'processing' for >10 minutes.
    """
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    user_id = idn.user_id
    org_id = idn.org_id

    # Get file info
    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                SELECT content_enc, filename, created_by, status, created_at, file_size_bytes
                FROM uploaded_files
                WHERE id = :id
            """),
            {"id": file_id}
        )
        row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    content_enc, filename, file_owner, file_status, created_at, file_size = row

    # Security: Only allow owner to retry
    if file_owner != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to retry this file"
        )

    # Check if file is eligible for retry
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    file_age = now - created_at

    if file_status == 'ready':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is already indexed successfully"
        )

    if file_status == 'processing' and file_age < timedelta(minutes=10):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is still processing. Please wait at least 10 minutes before retrying."
        )

    # Decrypt content
    vault_key_id = mapping["vault_key_id"]
    content = await decrypt_text(vault_key_id, content_enc)

    # Check if should use direct context
    use_direct_context = file_size <= 50000

    # Reset status to processing
    async with member_session(schema) as s:
        await s.execute(
            text("UPDATE uploaded_files SET status = 'processing', error_message = NULL WHERE id = :id"),
            {"id": file_id}
        )
        await s.commit()

    # Try indexing again
    chunk_count = 0
    if not use_direct_context:
        try:
            rag_service = get_rag_service()
            upload_result = await rag_service.upload_document(
                file_id=file_id,
                content=content,
                org_id=org_id,
                user_id=user_id,
                filename=filename
            )
            chunk_count = upload_result.get("chunk_count", 0)
            log.info(f"Retry: Indexed {chunk_count} chunks for file {file_id}")
        except Exception as e:
            log.error(f"Retry indexing failed: {e}")
            error_msg = str(e)[:500]
            async with member_session(schema) as s:
                await s.execute(
                    text("UPDATE uploaded_files SET status = 'error', error_message = :msg WHERE id = :id"),
                    {"id": file_id, "msg": error_msg}
                )
                await s.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to re-index document: {str(e)}"
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

    return {
        "status": "success",
        "file_id": file_id,
        "chunk_count": chunk_count,
        "message": "File re-indexed successfully"
    }


@router.post("/cleanup-stuck-files")
async def cleanup_stuck_files(idn: Identity = Depends(get_identity)):
    """
    Cleanup task to mark files stuck in 'processing' state as 'error'.
    Files stuck for >10 minutes are marked as timed out.
    """
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]

    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                UPDATE uploaded_files
                SET status = 'error',
                    error_message = 'Indexing timeout - file stuck in processing for >10 minutes'
                WHERE status = 'processing'
                  AND created_at < NOW() - INTERVAL '10 minutes'
                RETURNING id, filename
            """)
        )
        stuck_files = result.all()
        await s.commit()

    cleaned_count = len(stuck_files)
    log.info(f"Cleaned up {cleaned_count} stuck files")

    return {
        "status": "success",
        "cleaned_count": cleaned_count,
        "files": [{"id": str(f[0]), "filename": f[1]} for f in stuck_files]
    }