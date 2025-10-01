# lumen/api/app/security.py
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

load_dotenv()

reusable_bearer = HTTPBearer(auto_error=False)

DEV_FAKE_AUTH = os.getenv("DEV_FAKE_AUTH", "false").lower() == "true"
DEV_FAKE_USER_ID = os.getenv("DEV_FAKE_USER_ID", "user_dev")
DEV_FAKE_ORG_ID = os.getenv("DEV_FAKE_ORG_ID", "org_dev_01")


@dataclass
class Identity:
    user_id: str
    org_id: str


def get_identity(token: HTTPAuthorizationCredentials | None = Depends(reusable_bearer)) -> Identity:
    """
    DEV mode: ignore the bearer token and return a fixed user/org.
    Later we will replace with Clerk JWT verification and extract org_id.
    """
    if DEV_FAKE_AUTH:
        return Identity(user_id=DEV_FAKE_USER_ID, org_id=DEV_FAKE_ORG_ID)

    # If you switch off DEV_FAKE_AUTH without wiring Clerk yet, block access.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Auth not configured. Set DEV_FAKE_AUTH=true or implement Clerk verification.",
    )
