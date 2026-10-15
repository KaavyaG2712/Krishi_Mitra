from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.config import get_settings
from app.core.security import sign
from app.modules.soil.models import PARAMETERS, SoilInput, SoilLookup, SoilProfile, SourceType
from app.modules.soil.recommendations import recommend
from app.modules.soil.service import SoilHealthService, SoilServiceError

router = APIRouter(prefix="/soil")


@lru_cache
def get_soil_service():
    return SoilHealthService(get_settings())


def soil_result(profile: SoilProfile, cached=False):
    return {"profile": profile, "recommendation": recommend(profile), "cached": cached,
            "profile_token": sign(profile.model_dump(mode="json"), "soil")}


@router.get("/parameters")
def parameters():
    return [{"key": key, "label": label, "units": units} for key, (label, units) in PARAMETERS.items()]


@router.post("/manual")
def manual(request: SoilInput):
    return soil_result(SoilProfile(**request.model_dump(), source="Farmer's soil-test report", source_type=SourceType.USER_ENTERED))


@router.post("/lookup")
def lookup(request: SoilLookup, service: SoilHealthService = Depends(get_soil_service)):
    try:
        profile, cached = service.lookup(request)
        if profile is None:
            return {"profile": None, "cached": cached, "message": "We could not find soil test information for this location. Enter your soil-test values or contact a soil-testing laboratory."}
        return soil_result(profile, cached)
    except SoilServiceError as error:
        raise HTTPException(error.status, {"code": error.code, "message": error.message}) from None


@router.get("/locations/{level}")
def locations(level: Literal["states", "districts", "blocks", "villages"], state: str = Query("", max_length=80), district: str = Query("", max_length=80), block: str = Query("", max_length=80), service: SoilHealthService = Depends(get_soil_service)):
    try:
        return service.locations(level, state, district, block)
    except SoilServiceError as error:
        raise HTTPException(error.status, {"code": error.code, "message": error.message}) from None


@router.get("/demo")
def demo():
    settings = get_settings()
    if settings.environment != "development" or not settings.soil_health_demo:
        raise HTTPException(404, "Not found")
    # Explicit fixture, never a fallback for a real government request.
    return soil_result(SoilProfile(parameters={"ph": {"value": 7.1, "unit": "pH"}}, source="Synthetic development fixture — not a soil test", source_type=SourceType.USER_ENTERED, is_demo=True))
