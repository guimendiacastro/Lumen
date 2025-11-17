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
from ..utils.debug import debug_enabled
from ..utils.document_processor import expand_unchanged_sections, extract_clean_response
from ..utils.edit_commands import generate_edit_system_prompt, apply_edits, EditPlan
from ..utils.validation import validate_completeness, format_validation_report


from ..services.azure_rag_service import get_rag_service

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
    mode: str = "edit"  # "edit" or "qa"

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
    With Azure AI Search, we no longer include full file content.
    All file retrieval is handled by RAG (Azure chunks, embeds, and retrieves).
    This function is kept for backwards compatibility but returns empty string.
    """
    return ""


async def _get_rag_context(
    schema: str,
    key_id: str,
    thread_id: str,
    query: str,
    org_id: str,
    user_id: str,
    top_k: int = 15,
    min_similarity: float = 0.7
) -> str:
    """
    Retrieve RAG context using Azure AI Search with security filtering.
    """
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
        return ""

    rag_service = get_rag_service()
    file_ids = [f[0] for f in files]

    try:
        # Search across all files in the thread
        chunks = await rag_service.search_documents(
            query=query,
            org_id=org_id,
            user_id=user_id,
            file_ids=file_ids,
            top_k=top_k
        )

        if not chunks:
            return ""

        # Format chunks for LLM
        rag_text = "<retrieved_context>\n"
        rag_text += "The following information was retrieved from uploaded documents:\n\n"

        for i, chunk in enumerate(chunks, 1):
            filename = chunk.get("filename", "unknown")
            score = chunk.get("score", 0)
            content = chunk.get("content", "")
            rag_text += f"[Chunk {i} from {filename}] (relevance: {score:.2f})\n"
            rag_text += f"{content}\n\n"

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
    import time
    start_time = time.time()
    log.info(f"[/ai/compare] Starting request for thread_id={body.thread_id}, message_id={body.message_id}")

    mapping = await _mapping_or_404(idn)
    log.info(f"[/ai/compare] Mapping retrieved in {time.time() - start_time:.2f}s")
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

    # Different prompts based on interaction mode
    if body.mode == "qa":
        system_preamble = (
            "You are a helpful legal research assistant.\n\n"
            "The user is asking a question about their document or uploaded files.\n"
            "DO NOT suggest document edits or modifications.\n"
            "Instead, answer their question directly and clearly.\n\n"
            "RESPONSE GUIDELINES:\n"
            "- Answer the question based on the provided document and file context\n"
            "- Quote relevant sections from the document when helpful\n"
            "- Use clear, readable Markdown formatting\n"
            "- Be concise but thorough\n"
            "- If you reference specific content, cite where it comes from\n\n"
            "DO NOT:\n"
            "- Suggest changes to the document\n"
            "- Return the full document in your response\n"
            "- Use <document> tags or edit commands\n"
        )
    elif use_structured_edits:
        system_preamble = generate_edit_system_prompt()
    else:
        system_preamble = (
            "You are a legal drafting assistant.\n\n"
            "CRITICAL FORMAT REQUIREMENTS:\n"
            "- Your response MUST start with the opening <document> tag\n"
            "- Place the complete document content between <document>...</document> tags\n"
            "- Your response MUST end with the closing </document> tag\n"
            "- DO NOT include ANY text before <document> or after </document>\n"
            "- DO NOT add preamble text like 'Sure, here is...', 'Below is...', 'I have created...', etc.\n"
            "- The first character of your response must be '<' (the start of <document>)\n\n"
            "CONTENT REQUIREMENTS:\n"
            "- Always output the COMPLETE document with all sections\n"
            "- Never use placeholders like '[Sections remain unchanged]' or '[Previous content]'\n"
            "- Include all sections in full, even if unchanged\n"
            "- Use proper Markdown formatting for all content:\n"
            "  * Use # for main title, ## for sections, ### for subsections\n"
            "  * Use **bold** for emphasis on key terms\n"
            "  * Use numbered lists (1., 2., 3.) or bullet points (- item) where appropriate\n"
            "  * Use proper paragraph spacing with blank lines between sections\n\n"
            "Example correct format:\n"
            "<document>\n# Document Title\n\n## 1. Section Name\n\n1.1 **Key Term**: Description here.\n\n[Your complete document content in Markdown]\n</document>"
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
    log.info(f"[/ai/compare] Loading latest message...")
    latest_instruction = await _load_sanitized_message(schema, key_id, body.message_id)
    log.info(f"[/ai/compare] Message loaded in {time.time() - start_time:.2f}s")

    # IMPROVED RAG: expanded query, more chunks, lower threshold, with security
    log.info(f"[/ai/compare] Getting RAG context...")
    rag_start = time.time()
    rag_block = await _get_rag_context(
        schema=schema,
        key_id=key_id,
        thread_id=body.thread_id,
        query=latest_instruction,
        org_id=idn.org_id,
        user_id=idn.user_id,
        top_k=RAG_TOP_K,
        min_similarity=RAG_MIN_SIM
    )
    log.info(f"[/ai/compare] RAG context retrieved in {time.time() - rag_start:.2f}s")

    if rag_block:
        messages.append({"role": "system", "content": rag_block})


    # Finally append the user's latest instruction
    messages.append({"role": "user", "content": latest_instruction})

    # Record the request
    log.info(f"[/ai/compare] Recording AI request...")
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
    log.info(f"[/ai/compare] Request recorded in {time.time() - start_time:.2f}s")

    # Fan-out to all providers (keeps your existing client abstraction)
    log.info(f"[/ai/compare] Fanning out to AI providers...")
    fanout_start = time.time()
    results = await fanout_with_history(messages)
    log.info(f"[/ai/compare] AI providers responded in {time.time() - fanout_start:.2f}s")

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
            provider = res.get("provider", "-")

            # Clean the response to remove any preamble text
            cleaned_text = extract_clean_response(response_text)

            expanded_text = cleaned_text

            # In Q&A mode, skip all document processing
            if body.mode == "qa":
                expanded_text = cleaned_text
            elif use_structured_edits and doc_content:
                try:
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned_text, re.DOTALL)
                    json_str = json_match.group(1) if json_match else cleaned_text
                    parsed_plan = EditPlan.model_validate_json(json_str)

                    expanded_text = apply_edits(doc_content, parsed_plan)
                except Exception as e:
                    # Fall back to placeholder expansion
                    if provider == "openai":
                        log.warning("⚠️  Failed to parse edit commands: %s", str(e))
                    expanded_text = expand_unchanged_sections(cleaned_text, doc_content)

            elif doc_content:
                # No structured edits mode → still expand placeholders
                expanded_text = expand_unchanged_sections(cleaned_text, doc_content)

            # Validate completeness vs the source doc (if any)
            validation_issues = validate_completeness(expanded_text, doc_content)
            has_errors = any(issue.severity == "error" for issue in validation_issues)

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

    total_time = time.time() - start_time
    log.info(f"[/ai/compare] Request completed in {total_time:.2f}s total")
    return CompareOut(request_id=request_id, providers=provider_cards)
