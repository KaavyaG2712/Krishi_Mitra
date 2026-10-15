from fastapi import APIRouter

from app.api.v1.endpoints.advisor import router as advisor_router
from app.api.v1.endpoints.soil import router as soil_router
from app.api.v1.endpoints.planning import router as planning_router
from app.api.v1.endpoints.speech import router as speech_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.crop_health import router as crop_health_router

router = APIRouter()
router.include_router(health_router, tags=["system"])
router.include_router(crop_health_router, tags=["crop health"])
router.include_router(advisor_router, tags=["advisor"])
router.include_router(soil_router, tags=["soil"])
router.include_router(planning_router, tags=["crop planning"])
router.include_router(speech_router, tags=["speech"])
