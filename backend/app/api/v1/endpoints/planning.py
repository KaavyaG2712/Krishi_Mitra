from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from app.modules.planning.models import PlanRequest
from app.modules.planning.providers import DataUnavailable, PlanningData
from app.modules.planning.service import plan
from app.modules.crop_yield.service import compare_yield_models

router = APIRouter(prefix="/planning")


@lru_cache
def get_planning_data():
    return PlanningData()


@router.get("/locations")
def locations(q: str = Query(min_length=2, max_length=100), provider: PlanningData = Depends(get_planning_data)):
    try:
        return provider.places(q.strip())
    except DataUnavailable as error:
        raise HTTPException(503, str(error)) from None


@router.post("/recommend")
def recommend(request: PlanRequest, provider: PlanningData = Depends(get_planning_data)):
    try:
        return plan(request, provider)
    except DataUnavailable as error:
        raise HTTPException(422, str(error)) from None


@router.post("/compare")
def compare(request: PlanRequest, provider: PlanningData = Depends(get_planning_data)):
    """Return the existing simple shortlist and a separate historical ML ranking."""
    try:
        all_candidates = plan(request, provider, candidate_limit=None)
    except DataUnavailable as error:
        raise HTTPException(422, str(error)) from None
    simple = {**all_candidates, "top_crops": all_candidates["top_crops"][:3]}
    try:
        ml = compare_yield_models(all_candidates)
    except DataUnavailable as error:
        ml = {"status": "unavailable", "models": [], "message": str(error)}
    return {"simple": simple, "ml": ml}


@router.get("/admin-area")
def administrative_area(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
                        provider: PlanningData = Depends(get_planning_data)):
    try:
        return provider.administrative_area(latitude, longitude)
    except DataUnavailable as error:
        raise HTTPException(503, str(error)) from None
