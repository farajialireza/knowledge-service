"""Global exception handlers — internal errors are never leaked to clients."""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for errors not handled by route code.

    Logs the full traceback server-side and returns a generic 500 body so
    stack traces, SQL errors, or connection details cannot leak to clients.
    """
    logger.exception(
        "Unhandled error while processing %s %s", request.method, request.url.path
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
