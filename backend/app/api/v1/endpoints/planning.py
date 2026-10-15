from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from app.modules.planning.models import PlanRequest
from app.modules.planning.providers import DataUnavailable, PlanningData
from app.modules.planning.service import plan

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
