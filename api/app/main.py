# lumen/api/app/main.py
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

app = FastAPI(title="LUMEN API", version="1.0.0")

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