# lumen/api/app/main.py
from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .routers import health, me, bootstrap, documents, threads, ai, selections, files

load_dotenv()

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

app = FastAPI(title="LUMEN API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(health.router)
app.include_router(me.router)
app.include_router(bootstrap.router)
app.include_router(documents.router)
app.include_router(threads.router)
app.include_router(ai.router)
app.include_router(selections.router)
app.include_router(files.router)


def run():
    import uvicorn
    uvicorn.run("app.main:app", host=API_HOST, port=API_PORT, reload=True)


if __name__ == "__main__":
    run()