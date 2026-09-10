"""
embedding_service.py
─────────────────────
All vector embedding logic using sentence-transformers.
Model runs locally inside Docker — no API key needed.

Model: all-MiniLM-L6-v2 — 384-dim vectors, fast, good for semantic similarity.
Downloads once on first startup (~90MB), cached after that.
"""

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings

_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print("Loading embedding model (first time only)...")
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        print("Embedding model loaded.")
    return _model


def embed(text: str) -> list[float]:
    """Embed a single string → returns a 384-dim float list."""
    model = get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings at once (faster than one by one)."""
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    a = np.array(v1)
    b = np.array(v2)
    return float(np.dot(a, b))
