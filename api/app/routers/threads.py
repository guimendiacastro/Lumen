# lumen/api/app/routers/threads.py
from __future__ import annotations

import hashlib
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import text

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, member_session
from ..crypto.vault import encrypt_text, decrypt_text
from ..privacy.sanitize import sanitize

router = APIRouter(prefix="/threads", tags=["threads"])

# ---------- Models ----------

class ThreadCreate(BaseModel):
    title: str | None = None
    document_id: str | None = None

class ThreadUpdate(BaseModel):
    title: str

class ThreadOut(BaseModel):
    id: str
    title: str | None = None
    document_id: str | None = None

class MessageCreate(BaseModel):
    text: str
    role: str = "user"
    scope: str | None = None

class MessageOut(BaseModel):
    id: str
    thread_id: str
    role: str
    text: str

class ThreadListItem(BaseModel):
    id: str
    title: str | None = None
    document_id: str | None = None
    created_at: str
    updated_at: str

class ThreadWithMessages(BaseModel):
    id: str
    title: str | None = None
    document_id: str | None = None
    created_at: str
    updated_at: str
    messages: List[dict]  # [{id, role, sanitized, ts}]

# ---------- Helpers ----------

def _as_str_or_none(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, UUID):
        return str(val)
    return str(val)

async def _mapping_or_404(idn: Identity):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return mapping

# ---------- Create Thread ----------

@router.post("", response_model=ThreadOut)
async def create_thread(payload: ThreadCreate, idn: Identity = Depends(get_identity)):
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]

    async with member_session(schema) as s:
        res = await s.execute(
            text("""
                INSERT INTO chat_threads (document_id, title, created_by, created_at, updated_at)
                VALUES (:doc, :title, :by, now(), now())
                RETURNING id, document_id, title
            """),
            {"doc": payload.document_id, "title": payload.title, "by": idn.user_id},
        )
        row = res.first()
        await s.commit()
        return ThreadOut(
            id=str(row[0]),
            document_id=_as_str_or_none(row[1]),
            title=row[2],
        )

# ---------- Update Thread ----------

@router.put("/{thread_id}", response_model=ThreadOut)
async def update_thread(thread_id: str, payload: ThreadUpdate, idn: Identity = Depends(get_identity)):
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]

    async with member_session(schema) as s:
        # Check if thread exists
        chk = await s.execute(
            text("SELECT id, document_id FROM chat_threads WHERE id = :id"),
            {"id": thread_id}
        )
        row = chk.first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

        # Update the title
        await s.execute(
            text("""
                UPDATE chat_threads
                SET title = :title
                WHERE id = :id
            """),
            {"id": thread_id, "title": payload.title}
        )
        await s.commit()

        return ThreadOut(
            id=str(row[0]),
            document_id=_as_str_or_none(row[1]),
            title=payload.title,
        )

# ---------- Post Message ----------

@router.post("/{thread_id}/messages", response_model=MessageOut)
async def post_message(thread_id: str, payload: MessageCreate, idn: Identity = Depends(get_identity)):
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    raw = payload.text
    sanitized_text = sanitize(raw)
    raw_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    raw_enc = await encrypt_text(key_id, raw)
    sanitized_enc = await encrypt_text(key_id, sanitized_text)

    async with member_session(schema) as s:
        # Ensure thread exists
        chk = await s.execute(text("SELECT 1 FROM chat_threads WHERE id = :id"), {"id": thread_id})
        if not chk.first():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

        res = await s.execute(
            text("""
            INSERT INTO chat_messages (thread_id, role, raw_hash, text_enc, sanitized_enc)
            VALUES (:tid, :role, :h, :t, :ts)
            RETURNING id
            """),
            {"tid": thread_id, "role": payload.role, "h": raw_hash, "t": raw_enc, "ts": sanitized_enc},
        )
        mid = str(res.first()[0])

        # Update thread's updated_at timestamp
        await s.execute(
            text("UPDATE chat_threads SET updated_at = now() WHERE id = :id"),
            {"id": thread_id}
        )

        await s.commit()



    return MessageOut(id=mid, thread_id=thread_id, role=payload.role, text=raw)

# ---------- List Threads (paginated) ----------

@router.get("", response_model=list[ThreadListItem])
async def list_threads(
    idn: Identity = Depends(get_identity),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Return threads for the current member (no messages, for a lightweight list).
    """
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]

    async with member_session(schema) as s:
        r = await s.execute(
            text("""
                SELECT id, title, document_id, created_at, updated_at
                  FROM chat_threads
                 ORDER BY updated_at DESC, id DESC
                 LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        )
        rows = r.all()

    return [
        ThreadListItem(
            id=str(row[0]),
            title=row[1],
            document_id=_as_str_or_none(row[2]),   # <-- cast UUID to str|None
            created_at=row[3].isoformat(),
            updated_at=row[4].isoformat(),
        )
        for row in rows
    ]

# ---------- Get Single Thread + Full Messages ----------

@router.get("/{thread_id}", response_model=ThreadWithMessages)
async def get_thread_with_messages(thread_id: str, idn: Identity = Depends(get_identity)):
    """
    Full thread with decrypted *sanitized* messages (user + assistant/system), ordered oldest -> newest.
    """
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    # Fetch thread
    async with member_session(schema) as s:
        t = await s.execute(
            text("SELECT id, title, document_id, created_at, updated_at FROM chat_threads WHERE id = :id"),
            {"id": thread_id},
        )
        row = t.first()
        if not row:
            raise HTTPException(status_code=404, detail="Thread not found")

    # Fetch messages
    async with member_session(schema) as s:
        r = await s.execute(
            text("""
                SELECT id, role, sanitized_enc, created_at
                  FROM chat_messages
                 WHERE thread_id = :tid
                 ORDER BY created_at ASC, id ASC
            """),
            {"tid": thread_id},
        )
        msgs = r.all()

    items = []
    for mid, role, san_enc, ts in msgs:
        content = await decrypt_text(key_id, san_enc)
        items.append({
            "id": str(mid),
            "role": "assistant" if role == "system" else role,  # normalize for UI/LLMs
            "sanitized": content,
            "ts": ts.isoformat(),
        })

    return ThreadWithMessages(
        id=str(row[0]),
        title=row[1],
        document_id=_as_str_or_none(row[2]),       # <-- cast here too
        created_at=row[3].isoformat(),
        updated_at=row[4].isoformat(),
        messages=items,
    )

# ---------- (Optional) Raw messages-only endpoint (debug) ----------

@router.get("/{thread_id}/messages")
async def list_messages(thread_id: str, idn: Identity = Depends(get_identity)):
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    out = []
    async with member_session(schema) as s:
        r = await s.execute(
            text("""
                SELECT id, role, sanitized_enc, created_at
                  FROM chat_messages
                 WHERE thread_id=:tid
                 ORDER BY created_at ASC, id ASC
            """),
            {"tid": thread_id}
        )
        rows = r.all()
    for i, role, san_enc, ts in rows:
        out.append({
            "id": str(i),
            "role": "assistant" if role == "system" else role,
            "sanitized": await decrypt_text(key_id, san_enc),
            "ts": ts.isoformat()
        })
    return {"items": out}
