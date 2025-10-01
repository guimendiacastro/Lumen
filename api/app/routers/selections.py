# lumen/api/app/routers/selections.py
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, member_session
from ..crypto.vault import encrypt_text, decrypt_text
from ..privacy.sanitize import sanitize
from .ai import _get_thread_summary, _set_thread_summary
import hashlib, difflib, json
from datetime import datetime
from .ai import _get_thread_summary, _set_thread_summary
from ..utils.diff import summarize_diff


router = APIRouter(prefix="/ai", tags=["ai"])

ApplyMode = Literal["append", "replace", "insert_at"]

class Range(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

class SelectionIn(BaseModel):
    request_id: str
    response_id: str
    provider: Literal["openai", "anthropic", "xai"]
    document_id: str
    mode: ApplyMode = "append"
    insert_index: Optional[int] = None
    replace_range: Optional[Range] = None
    selected_text_override: Optional[str] = None

class SelectionOut(BaseModel):
    selection_id: str
    document_id: str
    new_version: int

async def _mapping_or_404(idn: Identity):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Organization not found")
    return mapping

async def _get_response_text(schema: str, key_id: str, response_id: str) -> str:
    async with member_session(schema) as s:
        r = await s.execute(text("SELECT text_enc FROM ai_responses WHERE id = :rid"), {"rid": response_id})
        row = r.mappings().first()  # <-- use mappings()
        if not row:
            raise HTTPException(status_code=404, detail="AI response not found")
        return await decrypt_text(key_id, row["text_enc"])


async def _get_document(schema: str, key_id: str, doc_id: str) -> tuple[str, str]:
    async with member_session(schema) as s:
        r = await s.execute(text("SELECT title, content_enc FROM documents WHERE id = :id"), {"id": doc_id})
        row = r.mappings().first()  # <-- use mappings()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        content = await decrypt_text(key_id, row["content_enc"])
        return row["title"], content


def _merge_content(current: str, to_apply: str, mode: ApplyMode, insert_index: int | None, repl_range: Range | None) -> str:
    if mode == "append":
        joiner = "\n\n" if not current.endswith("\n") else "\n"
        return f"{current}{joiner}{to_apply}"
    if mode == "insert_at":
        idx = insert_index or 0
        idx = max(0, min(idx, len(current)))
        return current[:idx] + to_apply + current[idx:]
    if mode == "replace":
        if repl_range is None:
            return to_apply
        start = max(0, repl_range.start)
        end   = max(0, repl_range.end)
        if start > end:
            start, end = end, start
        start = min(start, len(current))
        end   = min(end,   len(current))
        return current[:start] + to_apply + current[end:]
    return current

async def _write_audit(schema: str, actor: str, action: str, target: str | None, details: dict):
    payload = json.dumps(details)  # proper JSON string
    async with member_session(schema) as s:
        await s.execute(
            text("""
                INSERT INTO audit_logs (actor, action, target, details)
                VALUES (:actor, :action, :target, CAST(:details AS JSONB))
            """),
            {"actor": actor, "action": action, "target": target, "details": payload},
        )
        await s.commit()

@router.post("/selection", response_model=SelectionOut)
async def create_selection_apply(body: SelectionIn, idn: Identity = Depends(get_identity)):
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    # 1) Resolve chosen text
    chosen_text = body.selected_text_override or await _get_response_text(schema, key_id, body.response_id)

    # 2) Save as assistant/system message (conversation memory)
    async with member_session(schema) as s:
        rq = await s.execute(text("SELECT thread_id FROM ai_requests WHERE id = :rid"), {"rid": body.request_id})
        rqrow = rq.first()
        if not rqrow:
            raise HTTPException(status_code=404, detail="AI request not found")
        thread_id = str(rqrow[0])

    sanitized = sanitize(chosen_text)
    raw_hash  = hashlib.sha256(chosen_text.encode("utf-8")).hexdigest()
    raw_enc   = await encrypt_text(key_id, chosen_text)
    san_enc   = await encrypt_text(key_id, sanitized)

    async with member_session(schema) as s:
        await s.execute(
            text("""
                INSERT INTO chat_messages (thread_id, role, raw_hash, text_enc, sanitized_enc)
                VALUES (:tid, 'system', :h, :t, :ts)
            """),
            {"tid": thread_id, "h": raw_hash, "t": raw_enc, "ts": san_enc},
        )
        await s.commit()

    # 3) Merge into document + version
    title, current = await _get_document(schema, key_id, body.document_id)
    new_text = _merge_content(current, chosen_text, body.mode, body.insert_index, body.replace_range)
    new_cipher = await encrypt_text(key_id, new_text)

        # Summarize WHAT changed (diff old->new)
    change_bullets = summarize_diff(current, new_text, max_bullets=5, max_chars=300)

    # Pull the user instruction that triggered this selection (from the request's message)
    async with member_session(schema) as s:
        r = await s.execute(text("""
            SELECT m.sanitized_enc
              FROM ai_requests r
              JOIN chat_messages m ON m.id = r.message_id
             WHERE r.id = :rid
        """), {"rid": body.request_id})
        row = r.first()
    user_intent = ""
    if row:
        from ..crypto.vault import decrypt_text
        user_intent = await decrypt_text(key_id, row[0])

    # Build a compact summary update
    last_summary = await _get_thread_summary(schema, key_id, thread_id)
    bullets_txt = "\n• " + "\n• ".join(change_bullets)
    delta = (
        "Decision:\n"
        f"- User intent: {user_intent[:300]}{'…' if len(user_intent)>300 else ''}\n"
        f"- Applied: provider={body.provider}, mode={body.mode}\n"
        "Change Log:" + bullets_txt
    )

    base = (last_summary or "Thread context:\n")
    # keep to ~1500 chars total
    new_summary = (base + "\n" + delta)[-1500:]
    await _set_thread_summary(schema, key_id, thread_id, new_summary, bump_version=True)


    async with member_session(schema) as s:
        up = await s.execute(
            text("""
                UPDATE documents
                   SET content_enc = :content, updated_by = :by, updated_at = now()
                 WHERE id = :id
                RETURNING id
            """),
            {"content": new_cipher, "by": idn.user_id, "id": body.document_id},
        )
        if not up.first():
            raise HTTPException(status_code=404, detail="Document not found (during update)")

        vres = await s.execute(
            text("SELECT COALESCE(MAX(version),0)+1 AS next_v FROM doc_versions WHERE document_id = :id"),
            {"id": body.document_id},
        )
        next_v = int(vres.first()[0])

        meta = {
            "mode": body.mode,
            "insert_index": body.insert_index,
            "replace_range": body.replace_range.model_dump() if body.replace_range else None,
            "override_used": body.selected_text_override is not None,
        }
        meta_json = json.dumps(meta)

        # selections row
        sel = await s.execute(
            text("""
                INSERT INTO ai_selections (request_id, provider, applied_to_document, selection_meta)
                VALUES (:req, :prov, :doc, CAST(:meta AS JSONB))
                RETURNING id
            """),
            {
                "req": body.request_id,
                "prov": body.provider,
                "doc": body.document_id,
                "meta": json.dumps({
                    "mode": body.mode,
                    "insert_index": body.insert_index,
                    "replace_range": body.replace_range.model_dump() if body.replace_range else None,
                    "override_used": body.selected_text_override is not None,
                }),
            },
        )
        selection_id = str(sel.first()[0])

        # version row
        await s.execute(
            text("""
                INSERT INTO doc_versions (document_id, version, content_enc)
                VALUES (:doc_id, :version, :content)
            """),
            {"doc_id": body.document_id, "version": next_v, "content": new_cipher},
        )
        await s.commit()

    # 4) Audit
    await _write_audit(
        schema=schema,
        actor=idn.user_id,
        action="apply_selection",
        target=body.document_id,
        details={"request_id": body.request_id, "response_id": body.response_id, "provider": body.provider, "mode": body.mode},
    )

        # === Update rolling summary (short, cheap) ===
    last_summary = await _get_thread_summary(schema, key_id, thread_id)
    snippet = (chosen_text[:300] + "…") if len(chosen_text) > 300 else chosen_text
    delta = (
        f"- Applied selection from provider={body.provider} mode={body.mode} "
        f"into document {body.document_id}. Preview:\n{snippet}"
    )
    base = last_summary or "Thread context:\n"
    new_summary = (base + "\n" + delta)[-1200:]  # keep ~1200 chars max
    await _set_thread_summary(schema, key_id, thread_id, new_summary, bump_version=True)


    return SelectionOut(selection_id=selection_id, document_id=body.document_id, new_version=next_v)
