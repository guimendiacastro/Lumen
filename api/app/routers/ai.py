# lumen/api/app/routers/ai.py
from __future__ import annotations

import os
import re
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, member_session
from ..crypto.vault import encrypt_text, decrypt_text
from ..llm.clients import fanout_with_history
from ..utils.debug import dump_messages, debug_enabled
from ..utils.document_processor import expand_unchanged_sections
from ..utils.edit_commands import generate_edit_system_prompt, apply_edits, EditPlan
from ..utils.validation import validate_completeness, format_validation_report


from ..services.rag_service import get_rag_service


log = logging.getLogger("lumen.ai")
router = APIRouter(prefix="/ai", tags=["ai"])

STRUCTURED_EDITS_ENABLED = os.getenv("STRUCTURED_EDITS", "true").lower() == "true"
MAX_DOC_CHARS = int(os.getenv("MAX_DOC_CHARS", "24000"))

# Tunables for improved recall
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "15"))
RAG_MIN_SIM = float(os.getenv("RAG_MIN_SIMILARITY", "0.7"))

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


async def _get_file_context(schema: str, key_id: str, thread_id: str) -> str:
    """
    Retrieve file context for the thread.
    For small files (direct context): include full content.
    """
    log.info(f"=== _get_file_context called for thread_id: {thread_id} ===")
    
    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                SELECT id, filename, content_enc
                FROM uploaded_files
                WHERE thread_id = :tid AND status = 'ready'
                ORDER BY created_at ASC
            """),
            {"tid": thread_id}
        )
        
        files = []
        total_chars = 0
        MAX_CONTEXT_CHARS = 20000
        
        rows = result.all()
        log.info(f"=== Found {len(rows)} uploaded files for thread ===")
        
        for row in rows:
            file_id = str(row[0])
            filename = row[1]
            content_enc = row[2]
            
            # Check if this file uses direct context (no chunks)
            chunk_result = await s.execute(
                text("SELECT COUNT(*) FROM file_chunks WHERE file_id = :fid"),
                {"fid": file_id}
            )
            chunk_count = chunk_result.first()[0]
            
            log.info(f"=== File {filename}: chunk_count={chunk_count} ===")
            
            if chunk_count == 0:
                # Direct context file
                content = await decrypt_text(key_id, content_enc)
                
                log.info(f"=== Decrypted content length: {len(content)} ===")
                log.info(f"=== Content preview: {content[:200]} ===")
                
                if total_chars + len(content) > MAX_CONTEXT_CHARS:
                    remaining = MAX_CONTEXT_CHARS - total_chars
                    content = content[:remaining] + "\n\n[Content truncated...]"
                
                files.append(f"<file name='{filename}'>\n{content}\n</file>")
                total_chars += len(content)
                
                if total_chars >= MAX_CONTEXT_CHARS:
                    break
    
    if not files:
        log.info("=== No files found for direct context ===")
        return ""
    
    result_str = f"\n\n<uploaded_files>\n{' '.join(files)}\n</uploaded_files>\n"
    log.info(f"=== Returning file context, length: {len(result_str)} ===")
    return result_str


async def _get_rag_context(
    schema: str,
    key_id: str,
    thread_id: str,
    query: str,
    top_k: int = 15,
    min_similarity: float = 0.5
) -> str:
    """
    Retrieve RAG context using new LlamaIndex service.
    """
    log.info(f"=== _get_rag_context CALLED (NEW) ===")
    log.info(f"thread_id: {thread_id}, query: {query[:100]}...")
    
    # Find files in this thread
    async with member_session(schema) as s:
        result = await s.execute(
            text("""
                SELECT id, filename
                FROM uploaded_files
                WHERE thread_id = :tid AND status = 'ready'
            """),
            {"tid": thread_id}
        )
        files = [(str(row[0]), row[1]) for row in result]
    
    if not files:
        log.info("=== No files found ===")
        return ""
    
    log.info(f"=== Found {len(files)} files ===")
    for file_id, filename in files:
        log.info(f"  - {filename} (id: {file_id})")
    
    # Retrieve from all files
    rag_service = get_rag_service()
    file_ids = [f[0] for f in files]
    
    try:
        chunks = await rag_service.retrieve_from_multiple_files(
            file_ids=file_ids,
            query=query,
            top_k_per_file=max(top_k // len(files), 3),  # Distribute across files
            min_score=min_similarity
        )
        
        if not chunks:
            log.warning("=== No relevant chunks found ===")
            return ""
        
        log.info(f"=== Retrieved {len(chunks)} chunks ===")
        
        # Format chunks for LLM
        rag_text = "<retrieved_context>\n"
        rag_text += "The following information was retrieved from uploaded documents:\n\n"
        
        for i, chunk in enumerate(chunks, 1):
            filename = chunk.metadata.get("filename", "unknown")
            rag_text += f"[Chunk {i} from {filename}] (relevance: {chunk.score:.2f})\n"
            rag_text += f"{chunk.text}\n\n"
        
        rag_text += "</retrieved_context>"
        
        return rag_text
        
    except Exception as e:
        log.error(f"RAG retrieval failed: {e}")
        return ""



@router.post("/compare", response_model=CompareOut)
async def compare(body: CompareIn, idn: Identity = Depends(get_identity)):
    """
    Build a prompt with:
      1. System preamble (task definition)
      2. Conversation history (all past user requests)
      3. Current document (if linked)
      4. Uploaded file context (direct context for small files)
      5. RAG context (relevant chunks for large files; IMPROVED)
      6. Latest user instruction

    Then fan-out to 3 AI providers and return 3 draft alternatives.
    """
    mapping = await _mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    # Decide structured-edits mode based on whether a real document exists
    async with member_session(schema) as s:
        r = await s.execute(
            text("SELECT document_id FROM chat_threads WHERE id=:tid"),
            {"tid": body.thread_id}
        )
        row = r.first()

    has_document = False
    if row and row[0] is not None:
        doc_id = str(row[0])
        async with member_session(schema) as s:
            r = await s.execute(
                text("SELECT content_enc FROM documents WHERE id=:id"),
                {"id": doc_id}
            )
            d = r.first()
        if d:
            content = await decrypt_text(key_id, d[0])
            stripped = content.strip()
            if len(stripped) > 50 and not stripped.startswith("# New Document"):
                has_document = True

    use_structured_edits = STRUCTURED_EDITS_ENABLED and has_document

    if use_structured_edits:
        system_preamble = generate_edit_system_prompt()
    else:
        system_preamble = (
            "You are a legal drafting assistant. "
            "Return exactly ONE draft inside <document>...</document> and nothing else.\n"
            "IMPORTANT: Always output the COMPLETE document. Never use placeholders like "
            "'[Sections remain unchanged]' or '[Previous content]'. Always include all sections in full."
        )

    if body.system:
        system_preamble = body.system.strip() + "\n\n" + system_preamble

    messages: list[dict] = [{"role": "system", "content": system_preamble}]

    # Conversation history (previous user turns only)
    all_user_msgs = await _load_all_user_messages(schema, key_id, body.thread_id)
    if all_user_msgs:
        history_msgs = all_user_msgs[:-1]
        if history_msgs:
            history_text = "Previous requests in this thread:\n"
            for i, msg in enumerate(history_msgs, 1):
                preview = msg[:200] + "..." if len(msg) > 200 else msg
                history_text += f'{i}. "{preview}"\n'
            messages.append({"role": "system", "content": history_text})

    # Current document (if any)
    doc_block = await _current_document_block(schema, key_id, body.thread_id)
    if doc_block:
        messages.append({"role": "system", "content": doc_block})

    # Include uploaded small-file context
    file_block = await _get_file_context(schema, key_id, body.thread_id)
    if file_block:
        messages.append({"role": "system", "content": file_block})

    # Load latest instruction now so we can query RAG with it
    latest_instruction = await _load_sanitized_message(schema, key_id, body.message_id)

    log.info(f"=== ABOUT TO CALL _get_rag_context ===")

    # IMPROVED RAG: expanded query, more chunks, lower threshold
    rag_block = await _get_rag_context(
        schema=schema,
        key_id=key_id,
        thread_id=body.thread_id,
        query=latest_instruction,
        top_k=RAG_TOP_K,
        min_similarity=RAG_MIN_SIM
    )

    log.info(f"=== RETURNED FROM _get_rag_context ===")
    log.info(f"=== RAG block length: {len(rag_block) if rag_block else 0} ===")
    log.info(f"=== RAG block preview: {rag_block[:200] if rag_block else 'EMPTY'} ===")
    
    if rag_block:
        log.info(f"=== ADDING RAG BLOCK TO MESSAGES ===")
        messages.append({"role": "system", "content": rag_block})
    else:
        log.warning(f"=== RAG BLOCK IS EMPTY, NOT ADDING TO MESSAGES ===")
    

    # Finally append the user's latest instruction
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

    # Fan-out to all providers (keeps your existing client abstraction)
    results = await fanout_with_history(messages)

    # If we had a current doc, try to expand placeholders / apply structured edits
    doc_content = None
    if doc_block:
        match = re.search(r'<current_document>\n(.*?)\n</current_document>', doc_block, re.DOTALL)
        if match:
            doc_content = match.group(1)

    provider_cards: list[ProviderCard] = []
    async with member_session(schema) as s:
        for res in results:
            response_text = res.get("text") or ""

            if debug_enabled():
                log.info("=== LLM RESPONSE (raw) :: provider=%s ===\n%s",
                         res.get("provider", "-"),
                         response_text)

            expanded_text = response_text

            if use_structured_edits and doc_content:
                try:
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                    json_str = json_match.group(1) if json_match else response_text
                    parsed_plan = EditPlan.model_validate_json(json_str)

                    if debug_enabled():
                        log.info("=== EDIT PLAN (parsed JSON) :: provider=%s ===\n%s",
                                 res.get("provider", "-"),
                                 json.dumps(parsed_plan.model_dump(), indent=2, ensure_ascii=False))

                    expanded_text = apply_edits(doc_content, parsed_plan)
                except Exception as e:
                    # Fall back to placeholder expansion
                    log.warning("Failed to parse edit commands for provider=%s: %s",
                                res.get("provider", "-"), str(e))
                    expanded_text = expand_unchanged_sections(response_text, doc_content)

            elif doc_content:
                # No structured edits mode → still expand placeholders
                expanded_text = expand_unchanged_sections(response_text, doc_content)

            # Validate completeness vs the source doc (if any)
            validation_issues = validate_completeness(expanded_text, doc_content)
            has_errors = any(issue.severity == "error" for issue in validation_issues)

            if debug_enabled():
                if validation_issues:
                    log.info("=== VALIDATION (%s) :: provider=%s ===\n%s",
                             "ERRORS" if has_errors else "WARNINGS",
                             res.get("provider", "-"),
                             format_validation_report(validation_issues))
                log.info("=== LLM RESPONSE (post-processed) :: provider=%s ===\n%s",
                         res.get("provider", "-"),
                         expanded_text)

            # Store encrypted response
            text_enc = await encrypt_text(key_id, expanded_text)
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
                    text=expanded_text,
                    latencyMs=res.get("latency_ms"),
                    ok=res.get("ok", True) and not has_errors,
                )
            )
        await s.commit()

    return CompareOut(request_id=request_id, providers=provider_cards)
