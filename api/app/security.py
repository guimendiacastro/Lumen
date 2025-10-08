# lumen/api/app/security.py
from __future__ import annotations

import os
import jwt
import requests
from dataclasses import dataclass
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import lru_cache

load_dotenv()

reusable_bearer = HTTPBearer(auto_error=False)

DEV_FAKE_AUTH = os.getenv("DEV_FAKE_AUTH", "false").lower() == "true"
DEV_FAKE_USER_ID = os.getenv("DEV_FAKE_USER_ID", "user_dev")
DEV_FAKE_ORG_ID = os.getenv("DEV_FAKE_ORG_ID", "org_dev_01")

# Clerk configuration
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY")
CLERK_JWKS_URL = None

# Extract domain from publishable key to construct JWKS URL
if CLERK_PUBLISHABLE_KEY:
    # Publishable key format: pk_test_xxxxx or pk_live_xxxxx
    # Extract the instance domain from Clerk dashboard or construct from key
    # For now, we'll need the user to provide the full domain
    CLERK_FRONTEND_API = os.getenv("CLERK_FRONTEND_API")
    if CLERK_FRONTEND_API:
        # Strip any protocol prefix if user included it
        domain = CLERK_FRONTEND_API.replace("https://", "").replace("http://", "").strip().rstrip("/")
        CLERK_JWKS_URL = f"https://{domain}/.well-known/jwks.json"


@dataclass
class Identity:
    user_id: str
    org_id: str


@lru_cache(maxsize=1)
def get_clerk_jwks():
    """Fetch and cache Clerk's JWKS (public keys for JWT verification)."""
    if not CLERK_JWKS_URL:
        raise ValueError("CLERK_JWKS_URL not configured")
    
    response = requests.get(CLERK_JWKS_URL, timeout=10)
    response.raise_for_status()
    return response.json()


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk JWT token and return the decoded payload."""
    try:
        # Get JWKS
        jwks = get_clerk_jwks()
        
        # Decode the token header to get the key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        # Find the matching key
        signing_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                break
        
        if not signing_key:
            raise ValueError("Unable to find matching signing key")
        
        # Verify and decode the token
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            options={"verify_aud": False}  # Clerk doesn't always set audience
        )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}"
        )


async def get_identity(token: HTTPAuthorizationCredentials | None = Depends(reusable_bearer)) -> Identity:
    """
    Extract identity from Clerk JWT token or use fake auth in dev mode.
    """
    if DEV_FAKE_AUTH:
        return Identity(user_id=DEV_FAKE_USER_ID, org_id=DEV_FAKE_ORG_ID)

    # Real Clerk authentication
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    
    if not CLERK_JWKS_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clerk authentication not configured. Set CLERK_FRONTEND_API in .env",
        )

    try:
        # Verify the token
        payload = verify_clerk_token(token.credentials)
        
        # Extract user_id and org_id from payload
        user_id = payload.get("sub")  # Subject is the user ID
        org_id = payload.get("org_id")  # Organization ID if user is in an org
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No user_id in token",
            )
        
        # For personal workspaces, use user_id as org_id
        if not org_id:
            org_id = f"user_{user_id}"
        
        return Identity(user_id=user_id, org_id=org_id)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        ) from e