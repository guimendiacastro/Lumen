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
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
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

-- ========= MEMORY TABLES =========

-- Rolling short-term summary per thread (encrypted)
CREATE TABLE IF NOT EXISTS {schema}.thread_summaries (
  thread_id UUID PRIMARY KEY REFERENCES {schema}.chat_threads(id) ON DELETE CASCADE,
  summary_enc BYTEA NOT NULL,
  version INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Long-term durable facts, deduped by hash, per member
CREATE TABLE IF NOT EXISTS {schema}.memory_facts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  fact_hash TEXT NOT NULL UNIQUE,
  fact_enc BYTEA NOT NULL,
  source TEXT NOT NULL,           -- e.g. 'thread:<id>', 'doc:<id>'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _split_sql(sql: str) -> List[str]:
    """
    Naive splitter: splits on ';' and keeps non-empty statements.
    Good enough for our simple DDL (no PL/pgSQL blocks).
    """
    stmts = []
    for part in sql.split(';'):
        s = part.strip()
        if not s:
            continue
        # put the semicolon back for clarity (optional)
        if not s.endswith(';'):
            s = s + ';'
        stmts.append(s)
    return stmts

@router.post("/bootstrap/member-schema")
async def bootstrap_member_schema(idn: Identity = Depends(get_identity)):
    """
    Idempotent: creates (or verifies) the per-member schema and all core tables.
    Executes each DDL statement separately to satisfy asyncpg (no multi-statement prepare).
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
            # exec_driver_sql avoids some SQLAlchemy parsing overhead and is fine for raw DDL
            await conn.exec_driver_sql(stmt)

    return {"ok": True, "schema": mapping["schema_name"], "executed": len(statements)}
