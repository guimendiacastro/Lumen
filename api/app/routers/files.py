# lumen/api/app/routers/files.py
"""
File upload and management with new RAG service
"""

from __future__ import annotations

import uuid
import logging
import hashlib
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    library_scope: str
    indexed: bool = False


class FileMetadata(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    use_direct_context: bool
    created_at: str
    library_scope: str
    indexed: bool = False  # Whether chunks exist in Azure AI Search
    chunk_count: int = 0  # Number of indexed chunks
    indexed_at: str | None = None
    attached_at: str | None = None
    attached_threads: int | None = None
    error_message: str | None = None  # Error details if status='error'
    last_status_note: str | None = None


class FileIndexingStatus(BaseModel):
    file_id: str
    filename: str
    upload_status: str  # Database status: processing, ready, error
    indexed: bool  # Whether chunks exist in Azure AI Search
    chunk_count: int  # Number of indexed chunks
    indexing_note: str  # Information about indexing process
    library_scope: str
    indexed_at: str | None = None


class AttachFilesRequest(BaseModel):
    file_ids: List[str]


async def _get_mapping_or_404(idn: Identity):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    return mapping


async def _ensure_thread_access(session: AsyncSession, thread_id: str, user_id: str):
    result = await session.execute(
        text("SELECT created_by FROM chat_threads WHERE id = :id"),
        {"id": thread_id}
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if row[0] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this thread")


async def _ensure_file_owner(session: AsyncSession, file_id: str, user_id: str):
    result = await session.execute(
        text("""
            SELECT id, filename, status, created_by, use_direct_context,
                   chunk_count, library_scope
            FROM uploaded_files
            WHERE id = :id
        """),
        {"id": file_id}
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if row[3] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this file")
    return row


def _library_scope(use_direct: bool | None) -> str:
    return "direct" if use_direct else "rag"


def _is_indexed(use_direct: bool | None, chunk_count: int) -> bool:
    return bool(use_direct) or chunk_count > 0


async def _attach_files_to_thread(schema: str, thread_id: str, user_id: str, file_ids: List[str]):
    if not file_ids:
        return

    async with member_session(schema) as session:
        await _ensure_thread_access(session, thread_id, user_id)

        for file_id in file_ids:
            row = await _ensure_file_owner(session, file_id, user_id)
            status = row[2]
            if status != "ready":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File is still processing and cannot be attached"
                )

            await session.execute(
                text("""
                    INSERT INTO thread_files (thread_id, file_id, attached_by)
                    VALUES (:thread_id, :file_id, :by)
                    ON CONFLICT DO NOTHING
                """),
                {"thread_id": thread_id, "file_id": file_id, "by": user_id}
            )

        await session.commit()


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

    filename = file.filename or "unnamed"
    mime_type = file.content_type or "application/octet-stream"
    library_scope = _library_scope(result.use_direct_context)
    checksum = hashlib.sha256(content).hexdigest()

    # Encrypt full text
    content_enc = await encrypt_text(key_id, result.full_text)

    # Store file record
    file_id = str(uuid.uuid4())

    async with member_session(schema) as s:
        await s.execute(
            text("""
                INSERT INTO uploaded_files
                (id, document_id, thread_id, filename, mime_type, file_size_bytes,
                 storage_path, content_enc, status, use_direct_context, library_scope,
                 chunk_count, checksum_sha256, created_by)
                VALUES (:id, :doc_id, :thread_id, :filename, :mime, :size,
                        :path, :content, :status, :use_direct, :scope,
                        :chunk_count, :checksum, :by)
            """),
            {
                "id": file_id,
                "doc_id": document_id,
                "thread_id": thread_id,
                "filename": filename,
                "mime": mime_type,
                "size": len(content),
                "path": f"local/{file_id}",
                "content": content_enc,
                "status": "processing",
                "use_direct": result.use_direct_context,
                "scope": library_scope,
                "chunk_count": 0,
                "checksum": checksum,
                "by": user_id
            }
        )
        await s.commit()

    # Index with RAG if needed
    chunk_count = 0
    indexing_note = "Stored for direct context"
    if not result.use_direct_context:
        try:
            rag_service = get_rag_service()
            log.info(f"Indexing file {file_id} with Azure AI Search")

            upload_result = await rag_service.upload_document(
                file_id=file_id,
                org_id=idn.org_id,
                user_id=user_id,
                content=result.full_text,
                filename=filename
            )

            # Get chunk count from upload result
            chunk_count = upload_result.get("chunk_count", 0)
            indexing_note = upload_result.get("note", "Indexed for RAG usage")
            log.info(f"Indexed {chunk_count} chunks for file {file_id}. {indexing_note}")
        except Exception as e:
            log.error(f"RAG indexing failed: {e}")
            error_msg = str(e)[:500]  # Limit to 500 chars
            # Mark as failed with error message
            async with member_session(schema) as s:
                await s.execute(
                    text("""
                        UPDATE uploaded_files
                        SET status = 'error', error_message = :msg, last_status_note = :note
                        WHERE id = :id
                    """),
                    {"id": file_id, "msg": error_msg, "note": "RAG indexing failed"}
                )
                await s.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to index document: {str(e)}"
            )

    # Mark as ready
    indexed = _is_indexed(result.use_direct_context, chunk_count)
    async with member_session(schema) as s:
        await s.execute(
            text("""
                UPDATE uploaded_files 
                SET status = 'ready', processed_at = now(),
                    chunk_count = :chunk_count,
                    last_status_note = :note,
                    indexed_at = CASE WHEN :indexed THEN now() ELSE indexed_at END
                WHERE id = :id
            """),
            {"id": file_id, "chunk_count": chunk_count, "note": indexing_note, "indexed": indexed}
        )
        await s.commit()

    if thread_id:
        await _attach_files_to_thread(schema, thread_id, user_id, [file_id])
    
    return FileUploadResponse(
        file_id=file_id,
        filename=filename,
        size_bytes=len(content),
        use_direct_context=result.use_direct_context,
        chunk_count=chunk_count,
        status="ready",
        library_scope=library_scope,
        indexed=indexed
    )


@router.post("/library/upload", response_model=FileUploadResponse)
async def upload_library_file(
    file: UploadFile = File(...),
    document_id: Optional[str] = Form(None),
    idn: Identity = Depends(get_identity)
):
    """Upload a file directly into the user's library (no thread attachment)."""
    return await upload_file(file=file, document_id=document_id, thread_id=None, idn=idn)


@router.get("/thread/{thread_id}", response_model=List[FileMetadata])
async def list_files_in_thread(
    thread_id: str,
    idn: Identity = Depends(get_identity)
):
    """List all files in a thread with indexing status"""
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    user_id = idn.user_id

    async with member_session(schema) as s:
        await _ensure_thread_access(s, thread_id, user_id)
        result = await s.execute(
            text("""
                SELECT f.id, f.filename, f.mime_type, f.file_size_bytes,
                       f.status, f.created_at, f.error_message, f.use_direct_context,
                       f.chunk_count, f.library_scope, f.indexed_at,
                       MAX(tf.attached_at) AS attached_at,
                       f.last_status_note
                FROM uploaded_files f
                LEFT JOIN thread_files tf
                  ON tf.file_id = f.id AND tf.thread_id = :tid
                WHERE tf.thread_id = :tid OR f.thread_id = :tid
                GROUP BY f.id, f.filename, f.mime_type, f.file_size_bytes,
                         f.status, f.created_at, f.error_message, f.use_direct_context,
                         f.chunk_count, f.library_scope, f.indexed_at, f.last_status_note
                ORDER BY COALESCE(MAX(tf.attached_at), f.created_at) DESC
            """),
            {"tid": thread_id}
        )

        files = []
        for row in result:
            file_id = str(row[0])
            computed_scope = row[9] or ("direct" if row[7] else "rag")
            use_direct = row[7] if row[7] is not None else (computed_scope == "direct")
            chunk_count = row[8] or 0
            library_scope = computed_scope
            indexed = _is_indexed(use_direct, chunk_count)
            indexed_at = row[10]
            attached_at = row[11]
            note = row[12]

            files.append(FileMetadata(
                id=file_id,
                filename=row[1],
                mime_type=row[2],
                size_bytes=row[3],
                status=row[4],
                use_direct_context=use_direct,
                created_at=row[5].isoformat(),
                library_scope=library_scope,
                indexed=indexed,
                chunk_count=chunk_count,
                indexed_at=indexed_at.isoformat() if indexed_at else None,
                attached_at=attached_at.isoformat() if attached_at else None,
                error_message=row[6],
                last_status_note=note
            ))

        return files


@router.get("/library", response_model=List[FileMetadata])
async def list_library_files(idn: Identity = Depends(get_identity)):
    """List all files uploaded by the current user (library view)."""
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]

    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                SELECT f.id, f.filename, f.mime_type, f.file_size_bytes,
                       f.status, f.created_at, f.error_message, f.use_direct_context,
                       f.chunk_count, f.library_scope, f.indexed_at, f.last_status_note,
                       COALESCE(tf_cnt.attachments, 0) AS attached_threads
                FROM uploaded_files f
                LEFT JOIN (
                    SELECT file_id, COUNT(*) AS attachments
                    FROM thread_files
                    GROUP BY file_id
                ) tf_cnt ON tf_cnt.file_id = f.id
                WHERE f.created_by = :user
                ORDER BY f.created_at DESC
            """),
            {"user": idn.user_id}
        )

        files = []
        for row in result:
            scope = row[9] or ("direct" if row[7] else "rag")
            use_direct = row[7] if row[7] is not None else (scope == "direct")
            chunk_count = row[8] or 0
            indexed = _is_indexed(use_direct, chunk_count)
            indexed_at = row[10]
            note = row[11]
            attachments = row[12]

            files.append(FileMetadata(
                id=str(row[0]),
                filename=row[1],
                mime_type=row[2],
                size_bytes=row[3],
                status=row[4],
                use_direct_context=use_direct,
                created_at=row[5].isoformat(),
                library_scope=scope,
                indexed=indexed,
                chunk_count=chunk_count,
                indexed_at=indexed_at.isoformat() if indexed_at else None,
                error_message=row[6],
                last_status_note=note,
                attached_threads=attachments,
                attached_at=None
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
    # Get file info from database
    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                SELECT filename, status, created_by, chunk_count,
                       use_direct_context, library_scope, last_status_note,
                       indexed_at
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

    filename = row[0]
    upload_status = row[1]
    file_owner = row[2]
    chunk_count = row[3] or 0
    use_direct = row[4]
    library_scope = row[5] or ("direct" if use_direct else "rag")
    indexing_note = row[6] or ""
    last_indexed = row[7]

    # Security: Only allow owner to check status
    if file_owner != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this file"
        )

    indexed = _is_indexed(use_direct, chunk_count)

    return FileIndexingStatus(
        file_id=file_id,
        filename=filename,
        upload_status=upload_status,
        indexed=indexed,
        chunk_count=chunk_count,
        indexing_note=indexing_note,
        library_scope=library_scope,
        indexed_at=last_indexed.isoformat() if last_indexed else None
    )


@router.post("/thread/{thread_id}/files")
async def attach_files_to_thread(
    thread_id: str,
    payload: AttachFilesRequest,
    idn: Identity = Depends(get_identity)
):
    if not payload.file_ids:
        return {"status": "no-op"}

    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]

    await _attach_files_to_thread(schema, thread_id, idn.user_id, payload.file_ids)
    return {"status": "attached", "file_ids": payload.file_ids}


@router.delete("/thread/{thread_id}/files/{file_id}")
async def detach_file_from_thread(
    thread_id: str,
    file_id: str,
    idn: Identity = Depends(get_identity)
):
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]

    async with member_session(schema) as session:
        await _ensure_thread_access(session, thread_id, idn.user_id)
        await session.execute(
            text("DELETE FROM thread_files WHERE thread_id = :tid AND file_id = :fid"),
            {"tid": thread_id, "fid": file_id}
        )
        await session.commit()

    return {"status": "detached", "file_id": file_id}


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
            text("SELECT created_by, use_direct_context, library_scope FROM uploaded_files WHERE id = :id"),
            {"id": file_id}
        )
        row = result.first()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )

        file_owner = row[0]
        use_direct = row[1]
        scope = row[2]
        if use_direct is None:
            use_direct = (scope == "direct")
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

    # Delete RAG index with security parameters if applicable
    if not use_direct:
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
                SELECT content_enc, filename, created_by, status, created_at, file_size_bytes, use_direct_context
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

    content_enc, filename, file_owner, file_status, created_at, file_size, use_direct_db = row

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

    # Get use_direct_context from database (or fallback to size-based check for old records)
    use_direct_context = use_direct_db if use_direct_db is not None else (file_size <= 50000)

    # Reset status to processing
    async with member_session(schema) as s:
        await s.execute(
            text("""
                UPDATE uploaded_files
                SET status = 'processing', error_message = NULL, last_status_note = 'Retrying indexing'
                WHERE id = :id
            """),
            {"id": file_id}
        )
        await s.commit()

    # Try indexing again
    chunk_count = 0
    indexing_note = "Stored for direct context"
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
            indexing_note = upload_result.get("note", "Indexed via retry")
            log.info(f"Retry: Indexed {chunk_count} chunks for file {file_id}")
        except Exception as e:
            log.error(f"Retry indexing failed: {e}")
            error_msg = str(e)[:500]
            async with member_session(schema) as s:
                await s.execute(
                    text("""
                        UPDATE uploaded_files
                        SET status = 'error', error_message = :msg, last_status_note = 'Retry failed'
                        WHERE id = :id
                    """),
                    {"id": file_id, "msg": error_msg}
                )
                await s.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to re-index document: {str(e)}"
            )

    # Mark as ready
    indexed = _is_indexed(use_direct_context, chunk_count)
    async with member_session(schema) as s:
        await s.execute(
            text("""
                UPDATE uploaded_files
                SET status = 'ready', processed_at = now(),
                    chunk_count = :chunk_count,
                    last_status_note = :note,
                    indexed_at = CASE WHEN :indexed THEN now() ELSE indexed_at END
                WHERE id = :id
            """),
            {"id": file_id, "chunk_count": chunk_count, "note": indexing_note, "indexed": indexed}
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
                    error_message = 'Indexing timeout - file stuck in processing for >10 minutes',
                    last_status_note = 'Indexing timeout'
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
