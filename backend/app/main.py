"""
main.py
───────
FastAPI application entry point.

Routing lives in app/routers/. Business logic lives in app/services/.
This file's only job is to wire them together.
"""

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
