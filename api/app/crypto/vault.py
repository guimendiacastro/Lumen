# lumen/api/app/crypto/vault.py
from __future__ import annotations

import os
import base64
from typing import Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

VAULT_ADDR = os.getenv("VAULT_ADDR")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
TRANSIT_MOUNT = os.getenv("VAULT_TRANSIT_MOUNT", "transit")

if not VAULT_ADDR or not VAULT_TOKEN:
    raise RuntimeError("VAULT_ADDR and VAULT_TOKEN must be set in .env")

_HEADERS = {
    "X-Vault-Token": VAULT_TOKEN,
    "Content-Type": "application/json",
}

def _enc_path(key_name: str) -> str:
    # POST /v1/transit/encrypt/<key>
    return f"{VAULT_ADDR}/v1/{TRANSIT_MOUNT}/encrypt/{key_name}"

def _dec_path(key_name: str) -> str:
    # POST /v1/transit/decrypt/<key>
    return f"{VAULT_ADDR}/v1/{TRANSIT_MOUNT}/decrypt/{key_name}"

def _key_name_from_path(key_path: str) -> str:
    # Accepts 'transit/keys/dev_member' or just 'dev_member'
    return key_path.split("/")[-1]

async def encrypt_text(key_path: str, plaintext: str, context: Optional[str] = None) -> bytes:
    """
    Encrypt plaintext using Vault Transit (Base64 in/out).
    Returns UTF-8 bytes of the Vault ciphertext (e.g., b'vault:v1:...') ready to store in BYTEA.
    """
    key_name = _key_name_from_path(key_path)
    pt_b64 = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    body = {"plaintext": pt_b64}
    if context:
        body["context"] = base64.b64encode(context.encode("utf-8")).decode("ascii")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_enc_path(key_name), headers=_HEADERS, json=body)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Help debugging: include Vault error body
            raise RuntimeError(f"Vault encrypt failed: {e.response.status_code} {e.response.text}") from e
        data = resp.json()
        cipher = data["data"]["ciphertext"]  # e.g. 'vault:v1:...'
        return cipher.encode("utf-8")

async def decrypt_text(key_path: str, ciphertext_bytes: bytes, context: Optional[str] = None) -> str:
    """
    Decrypt Vault ciphertext (stored as BYTEA) back to plaintext string.
    """
    key_name = _key_name_from_path(key_path)
    cipher = ciphertext_bytes.decode("utf-8")
    body = {"ciphertext": cipher}
    if context:
        body["context"] = base64.b64encode(context.encode("utf-8")).decode("ascii")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_dec_path(key_name), headers=_HEADERS, json=body)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Vault decrypt failed: {e.response.status_code} {e.response.text}") from e
        data = resp.json()
        pt_b64 = data["data"]["plaintext"]
        return base64.b64decode(pt_b64.encode("ascii")).decode("utf-8")
