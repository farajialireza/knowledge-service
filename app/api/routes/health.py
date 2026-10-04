"""GET /health — service and database liveness."""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.schemas import HealthResponse
from app.db.health import is_database_available

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service and database liveness",
    responses={
        200: {"description": "PostgreSQL is reachable."},
        503: {"description": "PostgreSQL is unreachable; the service itself is up."},
    },
)
async def health(request: Request) -> JSONResponse:
    """Report service liveness and PostgreSQL reachability.

    Returns 200 when the database answers a trivial query, 503 otherwise.
    The response body is intentionally generic — underlying errors are logged
    server-side (see app.db.health) and never exposed to clients.
    """
    db_ok = await is_database_available(request.app.state.db_pool)
    payload = {
        "status": "ok" if db_ok else "degraded",
        "database": "up" if db_ok else "down",
    }
    return JSONResponse(payload, status_code=200 if db_ok else 503)
