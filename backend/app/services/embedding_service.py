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


class EmbeddingServiceError(Exception):
    """Raised when the local embedding model fails to load or run, so
    callers can show one friendly message instead of a raw traceback."""


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        try:
            print("Loading embedding model (first time only)...")
            _model = SentenceTransformer(settings.EMBEDDING_MODEL)
            print("Embedding model loaded.")
        except Exception as e:
            raise EmbeddingServiceError(
                "The embedding service failed to start. Please try again shortly."
            ) from e
    return _model


def embed(text: str) -> list[float]:
    """Embed a single string → returns a 384-dim float list."""
    try:
        model = get_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except EmbeddingServiceError:
        raise
    except Exception as e:
        raise EmbeddingServiceError(
            "Could not process this text for search. Please try again."
        ) from e


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple strings at once (faster than one by one)."""
    if not texts:
        return []
    try:
        model = get_model()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()
    except EmbeddingServiceError:
        raise
    except Exception as e:
        raise EmbeddingServiceError(
            "Could not process this file's content for search. Please try again."
        ) from e


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    a = np.array(v1)
    b = np.array(v2)
    return float(np.dot(a, b))
