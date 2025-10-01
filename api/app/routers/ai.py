# lumen/api/app/routers/ai.py
from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from typing import List, Dict, Any

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, member_session
from ..crypto.vault import encrypt_text, decrypt_text
from ..privacy.sanitize import sanitize
from ..llm.clients import fanout_with_history
# Optional prompt logging (DEV only; controlled by DEBUG_LOG_PROMPTS env)
try:
    from ..utils.debug import dump_messages
except Exception:  # if utils.debug not present, make a no-op
    def dump_messages(*args, **kwargs):
        return
        

router = APIRouter(prefix="/ai", tags=["ai"])

# Keep very large documents in check when embedding as <current_document>
MAX_DOC_CHARS = int(os.getenv("MAX_DOC_CHARS", "24000"))

# ===================== Models =====================

class CompareIn(BaseModel):
    thread_id: str
    message_id: str                  # latest user message (already saved via POST /threads/:id/messages)
    system: str | None = None        # optional extra system preamble

class ProviderCard(BaseModel):
    id: str
    provider: str
    text: str
    latencyMs: int | None = None
    ok: bool | None = None

class CompareOut(BaseModel):
    request_id: str
    providers: list[ProviderCard]


async def _load_recent_user_messages(schema: str, key_id: str, thread_id: str, limit: int = 3) -> list[dict]:
    """
    Return last N user messages as [{role:'user', content:...}], oldest->newest.
    Uses sanitized text (decrypts).
    """
    async with member_session(schema) as s:
        r = await s.execute(text("""
            SELECT id, sanitized_enc
              FROM chat_messages
             WHERE thread_id = :tid AND role = 'user'
             ORDER BY created_at DESC, id DESC
             LIMIT :lim
        """), {"tid": thread_id, "lim": limit})
        rows = r.all()
    out = []
    for _, enc in reversed(rows):
        content = await decrypt_text(key_id, enc)
        out.append({"role": "user", "content": content})
    return out


# ===================== Helpers =====================

async def _mapping_or_404(idn: Identity):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Organization not found")
    return mapping

async def _load_sanitized_message(schema: str, key_id: str, message_id: str) -> str:
    """
    Load the *sanitized* version of a chat message (plaintext), by id.
    """
    async with member_session(schema) as s:
        r = await s.execute(
            text("SELECT sanitized_enc FROM chat_messages WHERE id = :mid"),
            {"mid": message_id},
        )
        row = r.first()
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    return await decrypt_text(key_id, row[0])

async def _current_document_block(schema: str, key_id: str, thread_id: str) -> str | None:
    """
    If the thread is linked to a document, return its current plaintext content wrapped as:
      <current_document> ... </current_document>
    The content is clipped to MAX_DOC_CHARS.
    """
    async with member_session(schema) as s:
        r = await s.execute(text("SELECT document_id FROM chat_threads WHERE id=:tid"), {"tid": thread_id})
        row = r.first()
    if not row or row[0] is None:
        return None

    doc_id = str(row[0])
    async with member_session(schema) as s:
        r = await s.execute(text("SELECT content_enc FROM documents WHERE id=:id"), {"id": doc_id})
        d = r.first()
    if not d:
        return None

    content = await decrypt_text(key_id, d[0])
    if len(content) > MAX_DOC_CHARS:
        content = content[-MAX_DOC_CHARS:]  # keep the tail; often more recent edits are near the end

    # (Optional) apply sanitize(content) if you want redaction here as well.
    return f"<current_document>\n{content}\n</current_document>"

# ---- Rolling thread summary helpers (stored in {schema}.thread_summaries) ----

async def _get_thread_summary(schema: str, key_id: str, thread_id: str) -> str | None:
    """
    Load the rolling summary from {schema}.thread_summaries for a thread.
    Returns plaintext or None if absent.
    """
    async with member_session(schema) as s:
        r = await s.execute(
            text("SELECT summary_enc FROM thread_summaries WHERE thread_id = :tid"),
            {"tid": thread_id},
        )
        row = r.first()
    if not row:
        return None
    return await decrypt_text(key_id, row[0])

async def _set_thread_summary(schema: str, key_id: str, thread_id: str, summary_text: str, bump_version: bool = True):
    """
    Upsert sanitized+encrypted summary into {schema}.thread_summaries.
    Bumps a version counter when bump_version=True.
    """
    safe = sanitize(summary_text)
    enc  = await encrypt_text(key_id, safe)
    async with member_session(schema) as s:
        if bump_version:
            sql = """
              INSERT INTO thread_summaries (thread_id, summary_enc, version)
              VALUES (:tid, :enc, 1)
              ON CONFLICT (thread_id) DO UPDATE
              SET summary_enc = EXCLUDED.summary_enc,
                  version = thread_summaries.version + 1,
                  updated_at = now()
            """
        else:
            sql = """
              INSERT INTO thread_summaries (thread_id, summary_enc)
              VALUES (:tid, :enc)
              ON CONFLICT (thread_id) DO UPDATE
              SET summary_enc = EXCLUDED.summary_enc,
                  updated_at = now()
            """
        await s.execute(text(sql), {"tid": thread_id, "enc": enc})
        await s.commit()

# ===================== Endpoint =====================

@router.post("/compare", response_model=CompareOut)
async def compare(body: CompareIn, idn: Identity = Depends(get_identity)):
    """
    Build a compact prompt with:
      - strict system format: return *only* <document>…</document>
      - Thread Summary (if present)
      - <current_document>…</current_document> (if the thread has a linked doc)
      - latest user instruction (sanitized)
    Then fan-out to 3 AIs, store encrypted responses, and return 3 cards (one draft each).
    """
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    summary = await _get_thread_summary(schema, key_id, body.thread_id)

    system_preamble = (
        "You are a legal drafting assistant. "
        "Return exactly ONE draft inside <document>...</document> and nothing else.\n"
        "Use Thread Memory (Decisions/Goals + Change Log) to stay consistent. "
        "If <current_document> exists, rewrite/extend THAT document."
    )
    if body.system:
        system_preamble = body.system.strip() + "\n\n" + system_preamble

    messages: list[dict] = [{"role": "system", "content": system_preamble}]

    if summary:
        messages.append({"role": "system", "content": f"Thread Memory:\n{summary}"})

    doc_block = await _current_document_block(schema, key_id, body.thread_id)
    if doc_block:
        messages.append({"role": "system", "content": doc_block})

    # NEW: include last 3 user intents (sanitized), oldest->newest
    recent_user = await _load_recent_user_messages(schema, key_id, body.thread_id, limit=3)
    messages.extend(recent_user)

    # latest instruction (the new message)
    instruction = await _load_sanitized_message(schema, key_id, body.message_id)
    messages.append({"role": "user", "content": instruction})


    # DEV: log the assembled prompt (one log for all providers)
    dump_messages(label="compare", provider=None, model=None, messages=messages)

    # Record the request
    async with member_session(schema) as s:
        rq = await s.execute(
            text("""
                INSERT INTO ai_requests (thread_id, message_id, scope)
                VALUES (:tid, :mid, :scope)
                RETURNING id
            """),
            {"tid": body.thread_id, "mid": body.message_id, "scope": "full"},
        )
        request_id = str(rq.first()[0])
        await s.commit()

    # Fan-out with SAME messages to all providers
    results = await fanout_with_history(messages)

    # Store encrypted responses and return cards
    provider_cards: list[ProviderCard] = []
    async with member_session(schema) as s:
        for res in results:
            text_enc = await encrypt_text(key_id, res["text"])
            ins = await s.execute(
                text("""
                    INSERT INTO ai_responses (request_id, provider, text_enc, input_tokens, output_tokens, latency_ms)
                    VALUES (:rid, :prov, :txt, :in_tok, :out_tok, :lat)
                    RETURNING id
                """),
                {
                    "rid": request_id,
                    "prov": res["provider"],
                    "txt": text_enc,
                    "in_tok": res.get("input_tokens"),
                    "out_tok": res.get("output_tokens"),
                    "lat": res.get("latency_ms"),
                },
            )
            resp_id = str(ins.first()[0])
            provider_cards.append(
                ProviderCard(
                    id=resp_id,
                    provider=res["provider"],
                    text=res["text"],
                    latencyMs=res.get("latency_ms"),
                    ok=res.get("ok", True),
                )
            )
        await s.commit()

    return CompareOut(request_id=request_id, providers=provider_cards)
