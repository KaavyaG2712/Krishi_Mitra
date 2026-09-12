from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """Lightweight check used before module endpoints are introduced."""
    return {"status": "ok", "service": "krishimitra-api"}
