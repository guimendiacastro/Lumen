# lumen/api/app/routers/onboarding.py
from __future__ import annotations

import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from dotenv import load_dotenv

from ..security import get_identity, Identity
from ..db import engine, fetch_member_mapping

load_dotenv()

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

VAULT_ADDR = os.getenv("VAULT_ADDR")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
TRANSIT_MOUNT = os.getenv("VAULT_TRANSIT_MOUNT", "transit")

if not VAULT_ADDR or not VAULT_TOKEN:
    raise RuntimeError("VAULT_ADDR and VAULT_TOKEN must be set")

_HEADERS = {
    "X-Vault-Token": VAULT_TOKEN,
    "Content-Type": "application/json",
}


async def _create_vault_key(key_name: str) -> bool:
    """Create a new Transit encryption key in Vault."""
    url = f"{VAULT_ADDR}/v1/{TRANSIT_MOUNT}/keys/{key_name}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Check if key exists first
        check_resp = await client.get(url, headers=_HEADERS)
        if check_resp.status_code == 200:
            return True  # Key already exists
        
        # Create the key
        resp = await client.post(url, headers=_HEADERS, json={})
        try:
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Failed to create Vault key: {e.response.status_code} {e.response.text}") from e


async def _get_next_member_number() -> int:
    """Get the next available member schema number."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT schema_name FROM control.members 
                WHERE schema_name ~ '^mem_[0-9]+$'
                ORDER BY schema_name DESC 
                LIMIT 1
            """)
        )
        row = result.first()
        
        if not row:
            return 1
        
        # Extract number from 'mem_XX'
        last_schema = row[0]
        last_num = int(last_schema.split('_')[1])
        return last_num + 1


async def _create_member_entry(org_id: str, schema_name: str, vault_key_id: str, name: str, specialization: str):
    """Insert new member into control.members table."""
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO control.members (org_id, name, specialization, schema_name, vault_key_id)
                VALUES (:org_id, :name, :spec, :schema, :key)
                ON CONFLICT (org_id) DO NOTHING
            """),
            {
                "org_id": org_id,
                "name": name,
                "spec": specialization,
                "schema": schema_name,
                "key": vault_key_id
            }
        )


async def _create_user_entry(clerk_user_id: str, org_id: str, role: str = "admin"):
    """Insert new user into control.users table."""
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO control.users (clerk_user_id, org_id, role)
                VALUES (:user_id, :org_id, :role)
                ON CONFLICT (clerk_user_id) DO NOTHING
            """),
            {
                "user_id": clerk_user_id,
                "org_id": org_id,
                "role": role
            }
        )


async def _bootstrap_schema(schema_name: str):
    """Create the member schema with all tables. (Simplified inline DDL)"""
    from .bootstrap import SCHEMA_SQL, _split_sql
    
    ddl = SCHEMA_SQL.format(schema=schema_name)
    statements = _split_sql(ddl)
    
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)


@router.post("/register")
async def register_new_member(idn: Identity = Depends(get_identity)):
    """
    Automatically register a new member/organization:
    1. Check if member already exists
    2. Get next available member number
    3. Create Vault transit key
    4. Insert into control.members
    5. Insert into control.users
    6. Bootstrap member schema
    
    This should be called automatically when a new user signs in.
    """
    # Check if already registered
    existing = await fetch_member_mapping(idn.org_id)
    if existing:
        return {
            "ok": True,
            "message": "Member already registered",
            "schema_name": existing["schema_name"],
            "vault_key_id": existing["vault_key_id"]
        }
    
    # Get next member number
    next_num = await _get_next_member_number()
    schema_name = f"mem_{next_num:02d}"
    vault_key_name = f"member_{next_num:02d}"
    vault_key_id = f"transit/keys/{vault_key_name}"
    
    # Create Vault encryption key
    await _create_vault_key(vault_key_name)
    
    # Create member entry
    # You can customize name and specialization later via profile
    await _create_member_entry(
        org_id=idn.org_id,
        schema_name=schema_name,
        vault_key_id=vault_key_id,
        name=f"Member {next_num}",
        specialization="General Practice"
    )
    
    # Create user entry
    await _create_user_entry(
        clerk_user_id=idn.user_id,
        org_id=idn.org_id,
        role="admin"
    )
    
    # Bootstrap the schema
    await _bootstrap_schema(schema_name)
    
    return {
        "ok": True,
        "message": "Member registered successfully",
        "schema_name": schema_name,
        "vault_key_id": vault_key_id,
        "member_number": next_num
    }


@router.get("/status")
async def check_onboarding_status(idn: Identity = Depends(get_identity)):
    """Check if the current user's organization is registered."""
    mapping = await fetch_member_mapping(idn.org_id)
    return {
        "registered": mapping is not None,
        "org_id": idn.org_id,
        "schema_name": mapping["schema_name"] if mapping else None,
        "vault_key_id": mapping["vault_key_id"] if mapping else None
    }