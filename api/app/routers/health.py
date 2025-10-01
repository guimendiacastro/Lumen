# lumen/api/app/routers/health.py
from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/healthz")
async def healthz():
    return {"ok": True}
