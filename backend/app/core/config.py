"""
config.py
─────────
Central place for all environment-driven settings.
Nothing else in the app should call os.getenv() directly — import from here.
"""

import os


class Settings:
    # Postgres
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "db")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", 5432))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "docquery_db")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")

    # Groq LLM
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    LLM_ANSWER_MAX_TOKENS: int = int(os.getenv("LLM_ANSWER_MAX_TOKENS", 2048))
    LLM_EXTRACT_MAX_TOKENS: int = int(os.getenv("LLM_EXTRACT_MAX_TOKENS", 4096))

    # Embeddings
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = 384

    # Retrieval
    # Baseline top-k for a normal, specific chat question.
    TOP_K_PDF: int = int(os.getenv("TOP_K_PDF", 4))
    TOP_K_EXCEL: int = int(os.getenv("TOP_K_EXCEL", 100))
    TOP_K_CHAT: int = int(os.getenv("TOP_K_CHAT", 5))
    # Wider top-k used when the question looks like "list all" / "summarize
    # everything" / "show all records" — i.e. it needs broad coverage
    # rather than a handful of the closest-matching chunks/rows.
    TOP_K_CHAT_BROAD: int = int(os.getenv("TOP_K_CHAT_BROAD", 40))
    # Hard cap on rows pulled into a pandas DataFrame for an aggregation
    # question (count/sum/average/filter), so a huge sheet can't blow up
    # memory or the request.
    MAX_ROWS_FOR_PANDAS: int = int(os.getenv("MAX_ROWS_FOR_PANDAS", 50000))

    # Uploads
    ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}
    TABULAR_TYPES = {"xlsx", "xls", "csv"}
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))  # 25 MB

    # Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", 60 * 24 * 7))  # 7 days

    @property
    def db_config(self) -> dict:
        return {
            "host": self.POSTGRES_HOST,
            "port": self.POSTGRES_PORT,
            "dbname": self.POSTGRES_DB,
            "user": self.POSTGRES_USER,
            "password": self.POSTGRES_PASSWORD,
        }


settings = Settings()
