# lumen/api/app/routers/files.py
"""
Enhanced file upload and management API with Advanced RAG support
"""

from __future__ import annotations

import json
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import text

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, member_session
from ..crypto.vault import encrypt_text, decrypt_text
from ..services.file_processor import (
    FileProcessor, 
    EmbeddingService, 
    RAGRetriever,
    FileProcessingResult,
    ProcessedChunk
)

router = APIRouter(prefix="/files", tags=["files"])

MAX_FILE_SIZE = 30 * 1024 * 1024

# ===== Models =====

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
    chunk_count: int
    created_at: str

class RetrievalRequest(BaseModel):
    query: str
    file_ids: List[str]
    top_k: int = 5

class RetrievalResponse(BaseModel):
    chunks: List[dict]


# ===== Helper Functions =====

async def _get_mapping_or_404(idn: Identity):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    return mapping


async def _store_file_record(
    schema: str,
    key_id: str,
    user_id: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
    content: bytes,
    document_id: Optional[str],
    thread_id: Optional[str],
    result: FileProcessingResult
) -> str:
    """Store file metadata and return file_id"""
    
    # Encrypt full content
    content_enc = await encrypt_text(key_id, content.decode('utf-8', errors='ignore'))
    
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
                "filename": filename,
                "mime": mime_type,
                "size": size_bytes,
                "path": f"local/{file_id}",
                "content": content_enc,
                "status": "processing",
                "by": user_id
            }
        )
        await s.commit()
    
    return file_id


async def _process_and_store_chunks(
    schema: str,
    key_id: str,
    file_id: str,
    result: FileProcessingResult
) -> int:
    """Process chunks with enhanced metadata and store embeddings"""
    
    if result.use_direct_context or not result.chunks:
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
        return 0
    
    # Store chunks with enhanced metadata
    chunk_texts = []
    async with member_session(schema) as s:
        for i, chunk in enumerate(result.chunks):
            chunk_id = str(uuid.uuid4())
            
            # Encrypt chunk text
            chunk_enc = await encrypt_text(key_id, chunk.text)
            
            # Prepare metadata
            metadata_dict = chunk.metadata.__dict__ if hasattr(chunk.metadata, '__dict__') else {}
            
            await s.execute(
                text("""
                    INSERT INTO file_chunks
                    (id, file_id, chunk_index, chunk_text_enc, chunk_type, 
                     token_count, metadata, page_number, section_title, 
                     content_type, has_table, is_particulars, boost_factor)
                    VALUES (:id, :file_id, :idx, :text, :type, :tokens, 
                            CAST(:meta AS JSONB), :page, :section, :content_type,
                            :has_table, :is_particulars, :boost)
                """),
                {
                    "id": chunk_id,
                    "file_id": file_id,
                    "idx": i,
                    "text": chunk_enc,
                    "type": chunk.chunk_type,
                    "tokens": chunk.token_count,
                    "meta": json.dumps(metadata_dict),
                    "page": getattr(chunk.metadata, 'page_number', None),
                    "section": getattr(chunk.metadata, 'section_title', None),
                    "content_type": getattr(chunk.metadata, 'content_type', 'text'),
                    "has_table": getattr(chunk.metadata, 'has_table', False),
                    "is_particulars": getattr(chunk.metadata, 'is_particulars', False),
                    "boost": float(getattr(chunk.metadata, 'boost_factor', 1.0))
                }
            )
            
            chunk_texts.append((chunk_id, chunk.text))
        
        await s.commit()
    
    # Generate embeddings
    embedding_service = EmbeddingService()
    texts = [text for _, text in chunk_texts]
    embeddings = await embedding_service.generate_embeddings(texts)
    
    # Store embeddings
    async with member_session(schema) as s:
        for (chunk_id, _), embedding in zip(chunk_texts, embeddings):
            await s.execute(
                text("""
                    INSERT INTO chunk_embeddings
                    (chunk_id, embedding_model, embedding_vector)
                    VALUES (:chunk_id, :model, :vector)
                """),
                {
                    "chunk_id": chunk_id,
                    "model": embedding_service.model,
                    "vector": embedding
                }
            )
        
        # Update file status
        await s.execute(
            text("""
                UPDATE uploaded_files 
                SET status = 'ready', processed_at = now()
                WHERE id = :id
            """),
            {"id": file_id}
        )
        
        await s.commit()
    
    return len(result.chunks)


# ===== Routes =====

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    document_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
    idn: Identity = Depends(get_identity)
):
    """
    Upload a file and process it with advanced RAG:
    - PDF/DOCX support
    - Structure-aware chunking
    - Metadata extraction
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
    
    # Process file with advanced RAG
    try:
        result = FileProcessor.process_file(content, file.content_type or "application/octet-stream")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process file: {str(e)}"
        )
    
    # Store file record
    file_id = await _store_file_record(
        schema, key_id, user_id,
        file.filename or "unnamed",
        file.content_type or "application/octet-stream",
        len(content),
        content,
        document_id,
        thread_id,
        result
    )
    
    # Process and store chunks
    chunk_count = await _process_and_store_chunks(schema, key_id, file_id, result)
    
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
                    f.id, f.filename, f.mime_type, f.file_size_bytes, 
                    f.status, f.created_at,
                    COUNT(c.id) as chunk_count
                FROM uploaded_files f
                LEFT JOIN file_chunks c ON c.file_id = f.id
                WHERE f.thread_id = :thread_id
                GROUP BY f.id, f.filename, f.mime_type, f.file_size_bytes, 
                         f.status, f.created_at
                ORDER BY f.created_at DESC
            """),
            {"thread_id": thread_id}
        )
        
        files = []
        for row in result:
            files.append(FileMetadata(
                id=str(row[0]),
                filename=row[1],
                mime_type=row[2],
                size_bytes=row[3],
                status=row[4],
                use_direct_context=row[6] == 0,
                chunk_count=row[6],
                created_at=str(row[5])
            ))
        
        return files


@router.post("/retrieve", response_model=RetrievalResponse)
async def retrieve_relevant_chunks(
    body: RetrievalRequest,
    idn: Identity = Depends(get_identity)
):
    """
    Retrieve relevant chunks using advanced RAG:
    - Hybrid search (BM25 + Vector)
    - Cross-encoder reranking
    - Metadata boosting
    """
    
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]
    
    # Fetch all chunks with metadata and embeddings
    chunk_data = []
    async with member_session(schema) as s:
        for file_id in body.file_ids:
            result = await s.execute(
                text("""
                    SELECT 
                        c.chunk_text_enc, 
                        e.embedding_vector, 
                        c.id, 
                        f.filename,
                        c.page_number,
                        c.section_title,
                        c.content_type,
                        c.is_particulars,
                        c.boost_factor,
                        c.metadata
                    FROM file_chunks c
                    JOIN chunk_embeddings e ON e.chunk_id = c.id
                    JOIN uploaded_files f ON f.id = c.file_id
                    WHERE c.file_id = :file_id
                    ORDER BY c.chunk_index
                """),
                {"file_id": file_id}
            )
            
            for row in result:
                chunk_text = await decrypt_text(key_id, row[0])
                embedding = row[1]
                chunk_id = str(row[2])
                filename = row[3]
                page_number = row[4]
                section_title = row[5]
                content_type = row[6]
                is_particulars = row[7]
                boost_factor = float(row[8])
                metadata = row[9]
                
                chunk_data.append({
                    'text': chunk_text,
                    'embedding': embedding,
                    'chunk_id': chunk_id,
                    'filename': filename,
                    'page_number': page_number,
                    'section_title': section_title,
                    'content_type': content_type,
                    'is_particulars': is_particulars,
                    'boost': boost_factor,
                    'metadata': metadata
                })
    
    if not chunk_data:
        return RetrievalResponse(chunks=[])
    
    # Use advanced RAG retriever
    embedding_service = EmbeddingService()
    retriever = RAGRetriever(embedding_service)
    
    # Prepare chunk embeddings for retrieval
    chunk_embeddings = [(c['text'], c['embedding']) for c in chunk_data]
    
    # Retrieve with hybrid search + reranking
    relevant = await retriever.retrieve_relevant_chunks(
        body.query,
        chunk_embeddings,
        top_k=body.top_k
    )
    
    # Match back to metadata
    chunks = []
    for relevant_text, similarity in relevant:
        for chunk in chunk_data:
            if chunk['text'] == relevant_text:
                chunks.append({
                    "chunk_id": chunk['chunk_id'],
                    "filename": chunk['filename'],
                    "page_number": chunk['page_number'],
                    "section_title": chunk['section_title'],
                    "content_type": chunk['content_type'],
                    "is_particulars": chunk['is_particulars'],
                    "text": chunk['text'][:500] + "..." if len(chunk['text']) > 500 else chunk['text'],
                    "relevance_score": round(similarity, 4)
                })
                break
    
    return RetrievalResponse(chunks=chunks)


@router.get("/{file_id}/content")
async def get_file_content(
    file_id: str,
    idn: Identity = Depends(get_identity)
):
    """Get decrypted file content"""
    
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]
    
    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                SELECT content_enc, filename, mime_type 
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
    
    content = await decrypt_text(key_id, row[0])
    
    return {
        "content": content,
        "filename": row[1],
        "mime_type": row[2]
    }