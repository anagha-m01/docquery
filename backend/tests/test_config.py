"""
Settings values are computed once, at import time (Settings is a plain
class, not a dynamically-reloading BaseSettings), so these assert against
the already-imported `settings` singleton rather than re-instantiating
with monkeypatched env vars — re-instantiating wouldn't pick up new env
values anyway. This assumes no POSTGRES_*/LLM_MODEL overrides are set in
the shell running these tests, which holds for a clean CI runner.
"""

from app.core.config import settings


def test_default_settings_have_sane_fallbacks():
    assert settings.POSTGRES_HOST == "db"
    assert settings.POSTGRES_PORT == 5432
    assert settings.POSTGRES_DB == "docquery_db"
    assert settings.LLM_MODEL == "groq/compound-mini"
    assert settings.EMBEDDING_MODEL == "all-MiniLM-L6-v2"
    assert settings.EMBEDDING_DIM == 384


def test_allowed_extensions_cover_supported_file_types():
    assert settings.ALLOWED_EXTENSIONS == {".pdf", ".xlsx", ".xls", ".csv"}
    assert settings.TABULAR_TYPES == {"xlsx", "xls", "csv"}


def test_db_config_property_shape():
    config = settings.db_config
    assert config == {
        "host": settings.POSTGRES_HOST,
        "port": settings.POSTGRES_PORT,
        "dbname": settings.POSTGRES_DB,
        "user": settings.POSTGRES_USER,
        "password": settings.POSTGRES_PASSWORD,
    }

