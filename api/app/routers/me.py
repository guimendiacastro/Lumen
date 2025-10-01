# lumen/api/app/routers/me.py
from fastapi import APIRouter, Depends, HTTPException, status
from ..security import get_identity, Identity
from ..db import fetch_member_mapping

router = APIRouter(tags=["me"])

@router.get("/me")
async def me(idn: Identity = Depends(get_identity)):
    mapping = await fetch_member_mapping(idn.org_id)
    if not mapping:
        # You inserted org_dev_01 earlier; if you changed the IDs, update .env or the DB row.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found in control.members")
    return {
        "user_id": idn.user_id,
        "org_id": idn.org_id,
        "schema_name": mapping["schema_name"],
        "vault_key_id": mapping["vault_key_id"],
    }
