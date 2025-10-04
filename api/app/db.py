# lumen/api/app/db.py
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from dotenv import load_dotenv

import re



load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def fetch_member_mapping(org_id: str) -> dict | None:
    """
    Look up schema_name and (later) vault key id from control.members.
    """
    async with engine.begin() as conn:
        res = await conn.execute(
            text(
                """
                SELECT schema_name, vault_key_id
                FROM control.members
                WHERE org_id = :org_id
                """
            ),
            {"org_id": org_id},
        )
        row = res.first()
        if row:
            return {"schema_name": row[0], "vault_key_id": row[1]}
        return None


_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
@asynccontextmanager
async def member_session(schema_name: str) -> AsyncIterator[AsyncSession]:
    """
    Open a session with per-request search_path set to the member's schema.
    IMPORTANT: Always include 'public' for extensions like pgvector.
    """
    if not _SCHEMA_RE.match(schema_name):
        raise ValueError(f"Invalid schema name: {schema_name!r}")

    async with SessionLocal() as session:
        # Include public in search path for extensions (vector, uuid-ossp, etc.)
        await session.execute(text(f"SET LOCAL search_path TO {schema_name}, public"))
        yield session
