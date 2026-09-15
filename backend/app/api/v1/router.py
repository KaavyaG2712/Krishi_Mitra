from fastapi import APIRouter

from app.api.v1.endpoints.advisor import router as advisor_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.crop_health import router as crop_health_router

router = APIRouter()
router.include_router(health_router, tags=["system"])
router.include_router(crop_health_router, tags=["crop health"])
router.include_router(advisor_router, tags=["advisor"])
