from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.database import check_db_connection

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    """
    Asynchronous health check endpoint that probes PostgreSQL connectivity.
    """
    is_connected, error_message = await check_db_connection()

    if is_connected:
        return {
            "status": "healthy",
            "database": "connected"
        }

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "unhealthy",
            "database": "disconnected",
            "error": error_message
        }
    )
