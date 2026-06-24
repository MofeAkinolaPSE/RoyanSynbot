import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
STAGING_DB_PATH: str = os.environ.get("STAGING_DB_PATH", "staging/hope_staging.db")

# Pipeline v2 settings
REDIS_URL: str = os.environ.get("REDIS_URL", "")
PIPELINE_MAX_WORKERS: int = int(os.environ.get("PIPELINE_MAX_WORKERS", "4"))
PIPELINE_MODE: str = os.environ.get("PIPELINE_MODE", "full")
LOG_FORMAT: str = os.environ.get("LOG_FORMAT", "console")

if not DATABASE_URL:
    raise EnvironmentError(
        "DATABASE_URL is not set.\n"
        "Copy .env.example to .env and fill in your PostgreSQL connection string.\n"
        "Example: postgresql://postgres:password@localhost:5432/postgres"
    )
