"""Application entrypoint: app factory, lifespan, and wiring."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.config import get_settings
from app.db.pool import create_pool
from app.exceptions import unhandled_exception_handler
from app.logging_config import configure_logging

logger = logging.getLogger(__name__)

API_DESCRIPTION = """\
AI knowledge base backend. Currently exposes the admin document ingestion
pipeline: upload a file (PDF/DOCX/XLSX/CSV), and the service extracts,
normalizes, chunks and embeds it asynchronously into PostgreSQL/pgvector.

Interactive docs live at `/docs`; full pipeline documentation is in
`docs/ingestion.en.md` (English) and `docs/ingestion.fa.md` (فارسی).
"""

OPENAPI_TAGS = [
    {"name": "documents", "description": "Admin document upload and ingestion status."},
    {"name": "health", "description": "Service and database liveness."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage process-lifetime resources.

    Startup: configure logging, then create and open the PostgreSQL pool.
    Shutdown: close the pool so database connections are released cleanly.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting %s (environment=%s)", settings.app_name, settings.environment)

    pool = create_pool(settings)
    await pool.open()  # non-blocking: connections are established lazily
    app.state.db_pool = pool

    yield

    logger.info("Shutting down: closing PostgreSQL connection pool")
    await pool.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    return app


app = create_app()
