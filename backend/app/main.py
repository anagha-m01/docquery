"""
main.py
───────
FastAPI application entry point.

Routing lives in app/routers/. Business logic lives in app/services/.
This file's only job is to wire them together.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.database import init_db
from app.routers import extract, reextract, extractions, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="DocQuery API", lifespan=lifespan)

# Deployed frontend + local dev by default. Override/extend via the
# ALLOWED_ORIGINS env var (comma-separated) without touching code, e.g.
# ALLOWED_ORIGINS=https://docquery-weld.vercel.app,https://docquery.vercel.app
_default_origins = [
    "https://docquery-weld.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
]
_env_origins = os.getenv("ALLOWED_ORIGINS", "")
allowed_origins = (
    [origin.strip() for origin in _env_origins.split(",") if origin.strip()]
    or _default_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(extract.router)
app.include_router(reextract.router)
app.include_router(extractions.router)
app.include_router(chat.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "DocQuery API"}