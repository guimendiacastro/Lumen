# lumen/api/app/routers/ai.py
from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from typing import List

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, member_session
from ..crypto.vault import encrypt_text, decrypt_text
from ..llm.clients import fanout_with_history
from ..utils.debug import dump_messages

router = APIRouter(prefix="/ai", tags=["ai"])

MAX_DOC_CHARS = int(os.getenv("MAX_DOC_CHARS", "24000"))

class CompareIn(BaseModel):
    thread_id: str
    message_id: str
    system: str | None = None

class ProviderCard(BaseModel):
    id: str
    provider: str
    text: str
    latencyMs: int | None = None
    ok: bool | None = None

class CompareOut(BaseModel):
    request_id: str
    providers: list[ProviderCard]


async def _mapping_or_404(idn: Identity):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Organization not found")
    return mapping


async def _load_all_user_messages(schema: str, key_id: str, thread_id: str) -> list[str]:
    """Load all user messages for this thread, oldest to newest, sanitized."""
    async with member_session(schema) as s:
        r = await s.execute(text("""
            SELECT sanitized_enc
              FROM chat_messages
             WHERE thread_id = :tid AND role = 'user'
             ORDER BY created_at ASC, id ASC
        """), {"tid": thread_id})
        rows = r.all()
    
    out = []
    for (enc,) in rows:
        content = await decrypt_text(key_id, enc)
        out.append(content)
    return out


async def _load_sanitized_message(schema: str, key_id: str, message_id: str) -> str:
    """Load the sanitized version of a specific message."""
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
    If the thread is linked to a document, return its current plaintext content 
    wrapped in <current_document>...</current_document> tags.
    Content is clipped to MAX_DOC_CHARS from the end.
    """
    async with member_session(schema) as s:
        r = await s.execute(
            text("SELECT document_id FROM chat_threads WHERE id=:tid"), 
            {"tid": thread_id}
        )
        row = r.first()
    if not row or row[0] is None:
        return None

    doc_id = str(row[0])
    async with member_session(schema) as s:
        r = await s.execute(
            text("SELECT content_enc FROM documents WHERE id=:id"), 
            {"id": doc_id}
        )
        d = r.first()
    if not d:
        return None

    content = await decrypt_text(key_id, d[0])
    if len(content) > MAX_DOC_CHARS:
        content = content[-MAX_DOC_CHARS:]

    return f"<current_document>\n{content}\n</current_document>"


@router.post("/compare", response_model=CompareOut)
async def compare(body: CompareIn, idn: Identity = Depends(get_identity)):
    """
    Build a prompt with:
      1. System preamble (task definition)
      2. Conversation history (all past user requests)
      3. Current document (if linked)
      4. Latest user instruction
    
    Then fan-out to 3 AI providers and return 3 draft alternatives.
    """
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    system_preamble = (
        "You are a legal drafting assistant. "
        "Return exactly ONE draft inside <document>...</document> and nothing else.\n"
        "If <current_document> exists, modify/extend THAT document based on the user's request."
    )
    if body.system:
        system_preamble = body.system.strip() + "\n\n" + system_preamble

    messages: list[dict] = [{"role": "system", "content": system_preamble}]

    # Load all past user messages (conversation memory)
    all_user_msgs = await _load_all_user_messages(schema, key_id, body.thread_id)
    
    # Exclude the latest message (we'll add it separately at the end)
    if all_user_msgs:
        history_msgs = all_user_msgs[:-1]
        if history_msgs:
            history_text = "Previous requests in this thread:\n"
            for i, msg in enumerate(history_msgs, 1):
                preview = msg[:200] + "..." if len(msg) > 200 else msg
                history_text += f'{i}. "{preview}"\n'
            messages.append({"role": "system", "content": history_text})

    # Add current document if linked
    doc_block = await _current_document_block(schema, key_id, body.thread_id)
    if doc_block:
        messages.append({"role": "system", "content": doc_block})

    # Add the latest user instruction
    latest_instruction = await _load_sanitized_message(schema, key_id, body.message_id)
    messages.append({"role": "user", "content": latest_instruction})

    # Log what we're sending to the LLM
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

    # Fan-out to all providers
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