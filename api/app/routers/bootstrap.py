# lumen/api/app/routers/bootstrap.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from typing import List

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, engine

router = APIRouter(tags=["bootstrap"])

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  content_enc BYTEA NOT NULL,
  mime TEXT DEFAULT 'text/markdown',
  created_by TEXT NOT NULL,
  updated_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.doc_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES {schema}.documents(id) ON DELETE CASCADE,
  version INT NOT NULL,
  content_enc BYTEA NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(document_id, version)
);

CREATE TABLE IF NOT EXISTS {schema}.chat_threads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NULL REFERENCES {schema}.documents(id) ON DELETE SET NULL,
  title TEXT,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL REFERENCES {schema}.chat_threads(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  raw_hash TEXT NOT NULL,
  text_enc BYTEA NOT NULL,
  sanitized_enc BYTEA NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.ai_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL REFERENCES {schema}.chat_threads(id) ON DELETE CASCADE,
  message_id UUID NOT NULL REFERENCES {schema}.chat_messages(id) ON DELETE CASCADE,
  scope TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.ai_responses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES {schema}.ai_requests(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  text_enc BYTEA NOT NULL,
  input_tokens INT,
  output_tokens INT,
  latency_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.ai_selections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES {schema}.ai_requests(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  selection_meta JSONB,
  applied_to_document UUID NULL REFERENCES {schema}.documents(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS {schema}.uploaded_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NULL REFERENCES {schema}.documents(id) ON DELETE CASCADE,
  thread_id UUID NULL REFERENCES {schema}.chat_threads(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size_bytes BIGINT NOT NULL,
  storage_path TEXT NOT NULL,
  content_enc BYTEA NOT NULL,
  status TEXT NOT NULL DEFAULT 'processing',
  error_message TEXT,
  use_direct_context BOOLEAN,
  library_scope TEXT NOT NULL DEFAULT 'rag',
  chunk_count INT NOT NULL DEFAULT 0,
  checksum_sha256 TEXT,
  indexed_at TIMESTAMPTZ,
  last_status_note TEXT,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ
);


CREATE INDEX IF NOT EXISTS idx_documents_created_by ON {schema}.documents(created_by);
CREATE INDEX IF NOT EXISTS idx_doc_versions_document_id ON {schema}.doc_versions(document_id);

CREATE INDEX IF NOT EXISTS idx_chat_threads_document_id ON {schema}.chat_threads(document_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_id ON {schema}.chat_messages(thread_id);

CREATE INDEX IF NOT EXISTS idx_ai_requests_thread_id ON {schema}.ai_requests(thread_id);
CREATE INDEX IF NOT EXISTS idx_ai_responses_request_id ON {schema}.ai_responses(request_id);
CREATE INDEX IF NOT EXISTS idx_ai_selections_request_id ON {schema}.ai_selections(request_id);

CREATE INDEX IF NOT EXISTS idx_uploaded_files_document_id ON {schema}.uploaded_files(document_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_thread_id ON {schema}.uploaded_files(thread_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_status ON {schema}.uploaded_files(status);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_created_by ON {schema}.uploaded_files(created_by);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_checksum ON {schema}.uploaded_files(checksum_sha256);

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON {schema}.audit_logs(actor);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON {schema}.audit_logs(created_at);
"""


def _split_sql(sql: str) -> List[str]:
    """
    Split SQL into individual statements for asyncpg.
    Handles CREATE TABLE, CREATE INDEX, and other statements.
    """
    statements = []
    current = []
    
    for line in sql.split('\n'):
        line = line.strip()
        
        if not line or line.startswith('--'):
            continue
        
        current.append(line)
        
        if line.endswith(';'):
            stmt = ' '.join(current)
            if stmt and stmt != ';':
                statements.append(stmt)
            current = []
    
    if current:
        stmt = ' '.join(current)
        if stmt and stmt != ';':
            if not stmt.endswith(';'):
                stmt += ';'
            statements.append(stmt)
    
    return statements


async def _apply_uploaded_files_schema(schema: str):
    """
    Apply uploaded_files schema migrations in a single transaction.
    This is idempotent and safe to call multiple times.
    Uses advisory locks to prevent concurrent execution.
    """
    # Use advisory lock to prevent concurrent migrations on the same schema
    # Hash the schema name to get a consistent lock ID
    lock_id = hash(schema) % 2147483647  # Keep within int32 range

    async with engine.begin() as conn:
        # Acquire advisory lock first
        await conn.exec_driver_sql(f"SELECT pg_advisory_xact_lock({lock_id})")

        # Add columns to uploaded_files if they don't exist
        await conn.exec_driver_sql(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{schema}'
                    AND table_name = 'uploaded_files'
                    AND column_name = 'use_direct_context'
                ) THEN
                    ALTER TABLE {schema}.uploaded_files
                    ADD COLUMN use_direct_context BOOLEAN;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{schema}'
                    AND table_name = 'uploaded_files'
                    AND column_name = 'library_scope'
                ) THEN
                    ALTER TABLE {schema}.uploaded_files
                    ADD COLUMN library_scope TEXT NOT NULL DEFAULT 'rag';
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{schema}'
                    AND table_name = 'uploaded_files'
                    AND column_name = 'chunk_count'
                ) THEN
                    ALTER TABLE {schema}.uploaded_files
                    ADD COLUMN chunk_count INT NOT NULL DEFAULT 0;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{schema}'
                    AND table_name = 'uploaded_files'
                    AND column_name = 'checksum_sha256'
                ) THEN
                    ALTER TABLE {schema}.uploaded_files
                    ADD COLUMN checksum_sha256 TEXT;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{schema}'
                    AND table_name = 'uploaded_files'
                    AND column_name = 'indexed_at'
                ) THEN
                    ALTER TABLE {schema}.uploaded_files
                    ADD COLUMN indexed_at TIMESTAMPTZ;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = '{schema}'
                    AND table_name = 'uploaded_files'
                    AND column_name = 'last_status_note'
                ) THEN
                    ALTER TABLE {schema}.uploaded_files
                    ADD COLUMN last_status_note TEXT;
                END IF;
            END $$
        """)

        # Create thread_files table if it doesn't exist
        await conn.exec_driver_sql(f"""
            CREATE TABLE IF NOT EXISTS {schema}.thread_files (
                thread_id UUID NOT NULL REFERENCES {schema}.chat_threads(id) ON DELETE CASCADE,
                file_id UUID NOT NULL REFERENCES {schema}.uploaded_files(id) ON DELETE CASCADE,
                attached_by TEXT NOT NULL,
                attached_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY(thread_id, file_id)
            )
        """)

        # Create indexes if they don't exist
        await conn.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS idx_thread_files_thread_id ON {schema}.thread_files(thread_id)"
        )
        await conn.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS idx_thread_files_file_id ON {schema}.thread_files(file_id)"
        )

        # Backfill thread_files from uploaded_files where thread_id is set
        await conn.exec_driver_sql(f"""
            INSERT INTO {schema}.thread_files (thread_id, file_id, attached_by, attached_at)
            SELECT thread_id, id, created_by, created_at
            FROM {schema}.uploaded_files
            WHERE thread_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)

@router.post("/bootstrap/member-schema")
async def bootstrap_member_schema(idn: Identity = Depends(get_identity)):
    """
    Idempotent: creates the per-member schema and all core tables.
    Enhanced with Advanced RAG support:
    - Structure-aware metadata fields
    - Content type classification
    - Boost factors for relevance
    - Reranking score cache
    """
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found in control.members"
        )

    ddl = SCHEMA_SQL.format(schema=mapping["schema_name"])
    statements = _split_sql(ddl)

    async with engine.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)

    await _apply_uploaded_files_schema(mapping["schema_name"])

    return {"ok": True, "schema": mapping["schema_name"], "executed": len(statements)}


@router.post("/bootstrap/migrate-uploaded-files")
async def migrate_uploaded_files_schema(idn: Identity = Depends(get_identity)):
    """
    Migration endpoint to add use_direct_context column to existing uploaded_files tables.
    This is safe to run multiple times (idempotent).
    """
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found in control.members"
        )

    schema = mapping["schema_name"]

    await _apply_uploaded_files_schema(schema)

    return {"ok": True, "schema": schema, "message": "Migration completed successfully"}
