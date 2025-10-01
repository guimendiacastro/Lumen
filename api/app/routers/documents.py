# lumen/api/app/routers/documents.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from ..security import get_identity, Identity
from ..db import fetch_member_mapping, member_session
from ..crypto.vault import encrypt_text, decrypt_text
from ..privacy.sanitize import sanitize

router = APIRouter(prefix="/documents", tags=["documents"])

# ===== Schemas =====

class DocCreate(BaseModel):
    title: str
    content: str

class DocUpdate(BaseModel):
    content: str

class DocOut(BaseModel):
    id: str
    title: str
    content: str
    mime: str = "text/markdown"

# ===== Helpers =====

async def _get_mapping_or_404(idn: Identity):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return mapping

# ===== Routes =====

@router.post("", response_model=dict)
async def create_document(payload: DocCreate, idn: Identity = Depends(get_identity)):
    """
    Create a document: encrypt content with the member's Transit key and store in mem_xx.documents.
    Also create version 1 in doc_versions.
    """
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    # OPTIONAL: sanitize & store sanitized copy somewhere if needed (not required for docs)
    # For now, we encrypt the raw content directly (sanitization is used before AI calls).
    cipher = await encrypt_text(key_id, payload.content)

    async with member_session(schema) as s:
        res = await s.execute(
            text("""
                INSERT INTO documents (title, content_enc, mime, created_by)
                VALUES (:title, :content, :mime, :by)
                RETURNING id
            """),
            {"title": payload.title, "content": cipher, "mime": "text/markdown", "by": idn.user_id},
        )
        doc_id = str(res.first()[0])
        # Create version 1
        await s.execute(
            text("""
                INSERT INTO doc_versions (document_id, version, content_enc)
                VALUES (:doc_id, 1, :content)
            """),
            {"doc_id": doc_id, "content": cipher},
        )
        await s.commit()
    return {"id": doc_id}

@router.get("/{doc_id}", response_model=DocOut)
async def get_document(doc_id: str, idn: Identity = Depends(get_identity)):
    """
    Read a document: decrypt before returning to client.
    """
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    async with member_session(schema) as s:
        res = await s.execute(
            text("SELECT id, title, content_enc, mime FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        row = res.mappings().first()  # <-- use mappings()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        content = await decrypt_text(key_id, row["content_enc"])
        return DocOut(id=str(row["id"]), title=row["title"], content=content, mime=row["mime"])


@router.put("/{doc_id}", response_model=dict)
async def update_document(doc_id: str, payload: DocUpdate, idn: Identity = Depends(get_identity)):
    """
    Update a document content (encrypt) and create next version automatically.
    """
    mapping = await _get_mapping_or_404(idn)
    schema = mapping["schema_name"]
    key_id = mapping["vault_key_id"]

    cipher = await encrypt_text(key_id, payload.content)

    async with member_session(schema) as s:
        # Update doc
        r = await s.execute(
            text("""
                UPDATE documents
                   SET content_enc = :content, updated_by = :by, updated_at = now()
                 WHERE id = :id
                RETURNING id
            """),
            {"content": cipher, "by": idn.user_id, "id": doc_id},
        )
        if not r.first():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

        # Next version number
        vres = await s.execute(
            text("SELECT COALESCE(MAX(version),0)+1 AS next_v FROM doc_versions WHERE document_id = :id"),
            {"id": doc_id},
        )
        next_v = int(vres.first()[0])
        await s.execute(
            text("""
                INSERT INTO doc_versions (document_id, version, content_enc)
                VALUES (:doc_id, :version, :content)
            """),
            {"doc_id": doc_id, "version": next_v, "content": cipher},
        )
        await s.commit()

    return {"ok": True, "version": next_v}

# ===== Privacy preview (handy for testing the sanitizer) =====

class SanitizeIn(BaseModel):
    text: str

class SanitizeOut(BaseModel):
    sanitized: str

@router.post("/_sanitize", response_model=SanitizeOut)
async def preview_sanitize(body: SanitizeIn):
    return SanitizeOut(sanitized=sanitize(body.text))
