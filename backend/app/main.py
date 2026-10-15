from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.middleware import RequestLimits, EventFormatter
import logging

from app.api.router import router
from app.core.config import get_settings

settings = get_settings()
if settings.environment != "development" and (not settings.signing_secret or len(settings.signing_secret) < 32):
    raise RuntimeError("Set a random SIGNING_SECRET of at least 32 characters before deployment.")
if "*" in settings.cors_origins:
    raise RuntimeError("FRONTEND_ORIGINS must contain explicit trusted origins.")
handler = logging.StreamHandler()
handler.setFormatter(EventFormatter())
app_logger = logging.getLogger("app")
app_logger.handlers = [handler]
app_logger.setLevel(logging.INFO)
app_logger.propagate = False

app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(RequestLimits)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(Exception)
async def unexpected_error(request, error):
    app_logger.error("request_failed")
    return JSONResponse({"detail": {"code": "internal_error", "message": "The service could not finish this request. Please retry."}}, status_code=500)


app.include_router(router)
