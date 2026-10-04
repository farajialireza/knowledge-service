"""Lightweight liveness probe for PostgreSQL."""
import logging

from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

# Keep the probe short: a health endpoint must fail fast, not hang clients.
HEALTH_CHECK_TIMEOUT = 2.0


async def is_database_available(pool: AsyncConnectionPool) -> bool:
    """Return True if a trivial query succeeds, False otherwise.

    Every failure is logged here with a full traceback and swallowed, so
    callers can translate it into a generic, non-revealing API response.
    """
    try:
        async with pool.connection(timeout=HEALTH_CHECK_TIMEOUT) as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:
        logger.exception("PostgreSQL health check failed")
        return False
