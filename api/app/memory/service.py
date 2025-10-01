from __future__ import annotations
import hashlib
from typing import List, Tuple
from sqlalchemy import text
from ..db import member_session
from ..crypto.vault import encrypt_text, decrypt_text

# Config knobs
SUMMARY_EVERY_N_MESSAGES = 5
MAX_RECENT_MESSAGES = 6
MAX_FACTS = 20

async def get_last_messages(schema: str, key_id: str, thread_id: str, limit: int = MAX_RECENT_MESSAGES) -> List[Tuple[str,str]]:
    async with member_session(schema) as s:
        r = await s.execute(
            text("""
                SELECT role, sanitized_enc
                  FROM chat_messages
                 WHERE thread_id = :tid
              ORDER BY created_at DESC
                 LIMIT :lim
            """),
            {"tid": thread_id, "lim": limit},
        )
        rows = r.fetchall()
    out: List[Tuple[str,str]] = []
    for role, enc in reversed(rows):
        out.append((role, await decrypt_text(key_id, enc)))
    return out

async def get_thread_summary(schema: str, key_id: str, thread_id: str) -> Tuple[str,int] | None:
    async with member_session(schema) as s:
        r = await s.execute(
            text("SELECT summary_enc, version FROM thread_summaries WHERE thread_id = :tid"),
            {"tid": thread_id},
        )
        row = r.first()
    if not row:
        return None
    return (await decrypt_text(key_id, row[0]), int(row[1]))

async def set_thread_summary(schema: str, key_id: str, thread_id: str, summary_text: str, version: int) -> None:
    enc = await encrypt_text(key_id, summary_text)
    async with member_session(schema) as s:
        await s.execute(
            text("""
                INSERT INTO thread_summaries (thread_id, summary_enc, version, updated_at)
                VALUES (:tid, :sum, :v, now())
                ON CONFLICT (thread_id) DO UPDATE
                SET summary_enc = EXCLUDED.summary_enc,
                    version = EXCLUDED.version,
                    updated_at = now()
            """),
            {"tid": thread_id, "sum": enc, "v": version},
        )
        await s.commit()

async def list_recent_facts(schema: str, key_id: str, limit: int = MAX_FACTS) -> List[str]:
    async with member_session(schema) as s:
        r = await s.execute(
            text("SELECT fact_enc FROM memory_facts ORDER BY created_at DESC LIMIT :lim"),
            {"lim": limit},
        )
        rows = r.fetchall()
    return [await decrypt_text(key_id, enc) for (enc,) in rows]

def _quick_fact_candidates(plain_text: str) -> list[str]:
    import re
    sents = re.split(r'(?<=[.!?])\s+', plain_text.strip())
    cands: list[str] = []
    for s in sents:
        s2 = s.strip()
        if 8 <= len(s2) <= 220 and (s2[:1].isalnum() or s2[:1].isalpha()):
            cands.append(s2)
    return cands[:5]

async def add_facts(schema: str, key_id: str, source: str, plain_text: str) -> int:
    cands = _quick_fact_candidates(plain_text)
    if not cands:
        return 0
    async with member_session(schema) as s:
        for c in cands:
            h = hashlib.sha256(c.encode("utf-8")).hexdigest()
            enc = await encrypt_text(key_id, c)
            await s.execute(
                text("""
                    INSERT INTO memory_facts (fact_hash, fact_enc, source)
                    VALUES (:h, :e, :src)
                    ON CONFLICT (fact_hash) DO NOTHING
                """),
                {"h": h, "e": enc, "src": source},
            )
        await s.commit()
    return len(cands)

async def maybe_update_summary(schema: str, key_id: str, thread_id: str) -> None:
    async with member_session(schema) as s:
        r = await s.execute(
            text("SELECT COUNT(*) FROM chat_messages WHERE thread_id = :tid"),
            {"tid": thread_id},
        )
        count = int(r.first()[0])

    if count % SUMMARY_EVERY_N_MESSAGES != 0:
        return

    msgs = await get_last_messages(schema, key_id, thread_id, limit=MAX_RECENT_MESSAGES)
    joined = []
    for role, m in msgs:
        joined.append(f"{role.upper()}: {m}")
    base = "\n".join(joined)
    summary_text = base[-3000:]  # keep last ~3k chars

    prev = await get_thread_summary(schema, key_id, thread_id)
    new_version = (prev[1] + 1) if prev else 1
    await set_thread_summary(schema, key_id, thread_id, summary_text, new_version)

async def build_context(schema: str, key_id: str, thread_id: str) -> str:
    parts: list[str] = []
    ts = await get_thread_summary(schema, key_id, thread_id)
    if ts:
        parts.append("## Thread summary (rolling)\n" + ts[0])

    facts = await list_recent_facts(schema, key_id, limit=MAX_FACTS)
    if facts:
        parts.append("## Known durable facts\n- " + "\n- ".join(facts))

    msgs = await get_last_messages(schema, key_id, thread_id, limit=MAX_RECENT_MESSAGES)
    if msgs:
        buf = []
        for role, t in msgs:
            buf.append(f"{role}: {t}")
        parts.append("## Recent messages\n" + "\n".join(buf))

    return "\n\n".join(parts) if parts else ""
