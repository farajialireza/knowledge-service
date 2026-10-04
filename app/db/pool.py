"""PostgreSQL connection pool lifecycle (psycopg 3, async)."""
import logging

from psycopg_pool import AsyncConnectionPool

from app.config import Settings

logger = logging.getLogger(__name__)


def create_pool(settings: Settings) -> AsyncConnectionPool:
    """Build the connection pool without opening it.

    `open=False` defers connection establishment to the pool's background
    workers, so application startup does not fail when PostgreSQL is
    temporarily unreachable — `/health` reports the outage instead.
    """
    logger.info(
        "Creating PostgreSQL pool (host=%s port=%s dbname=%s min=%d max=%d)",
        settings.db_host,
        settings.db_port,
        settings.db_name,
        settings.db_pool_min_size,
        settings.db_pool_max_size,
    )
    return AsyncConnectionPool(
        conninfo="",
        kwargs=settings.db_connect_kwargs,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        open=False,
    )
