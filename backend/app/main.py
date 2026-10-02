"""
main.py
───────
FastAPI application entry point.

Routing lives in app/routers/. Business logic lives in app/services/.
This file's only job is to wire them together.
"""

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.core.database import init_db, DatabaseError
from app.routers import extract, reextract, extractions, chat, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except DatabaseError as e:
        # Don't crash the whole process on startup if the DB is briefly
        # unavailable (e.g. container ordering) — individual requests will
        # still surface a clear 503 via the handler below.
        print(f"WARNING: database not ready at startup: {e}")
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


@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(auth.router)
app.include_router(extract.router)
app.include_router(reextract.router)
app.include_router(extractions.router)
app.include_router(chat.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "DocQuery API"}
