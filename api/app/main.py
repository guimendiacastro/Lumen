# lumen/api/app/main.py
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import (
    bootstrap,
    documents,
    threads,
    ai,
    selections,
    files,
    me,
    onboarding,
    health,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

# Suppress verbose Azure SDK logging
logging.getLogger("azure").setLevel(logging.ERROR)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = FastAPI(title="LUMEN API", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    """Initialize Azure AI Search index on startup"""
    try:
        from .services.azure_rag_service import get_rag_service
        rag_service = get_rag_service()
        # Index is automatically initialized in __init__
        logger.info("Azure AI Search RAG service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Azure AI Search RAG service: {e}")
        # Don't fail the app startup, just log the error

# CORS for dev (adjust origins for prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)     
app.include_router(onboarding.router)
app.include_router(bootstrap.router)
app.include_router(documents.router)
app.include_router(threads.router)
app.include_router(ai.router)
app.include_router(selections.router)
app.include_router(files.router)
app.include_router(me.router)

@app.get("/")
def root():
    return {"message": "LUMEN API is running"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)