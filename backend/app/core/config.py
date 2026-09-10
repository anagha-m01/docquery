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
    LLM_MODEL: str = os.getenv("LLM_MODEL", "groq/compound-mini")

    # Embeddings
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = 384

    # Retrieval
    TOP_K_PDF: int = int(os.getenv("TOP_K_PDF", 4))
    TOP_K_EXCEL: int = int(os.getenv("TOP_K_EXCEL", 100))
    TOP_K_CHAT: int = int(os.getenv("TOP_K_CHAT", 5))

    # Uploads
    ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv"}
    TABULAR_TYPES = {"xlsx", "xls", "csv"}

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
