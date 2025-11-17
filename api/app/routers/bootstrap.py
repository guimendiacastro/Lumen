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

    return {"ok": True, "schema": mapping["schema_name"], "executed": len(statements)}