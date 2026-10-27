from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.endpoints.planning import get_planning_data
from app.modules.planning.models import PlanRequest
from app.modules.planning.providers import DataUnavailable, PlanningData, number
from app.modules.planning.service import catalog, economics, in_india, plan, rank_crops


def sowing(month=10):
    today = date.today()
    return date(today.year if today.month <= month else today.year+1, month, max(today.day, 1) if today.month == month else 1)


def request(**kwargs):
    return PlanRequest(latitude=17.97, longitude=79.59, sowing_date=sowing(), **kwargs)


def soil(ph=6.5):
    return {"status": "available", "measurements": {"ph": {"value": ph, "unit": "pH"}}}


def climate(temp=23, rain=800, monthly=60):
    return {"status": "available", "annual_rain_mm": rain, "monthly_temperature_c": {str(m): temp for m in range(1,13)},
            "monthly_rain_mm": {str(m): monthly for m in range(1,13)}}


class Provider:
    def soil(self, *args): return soil()
    def forecast(self, *args): return {"status": "unavailable"}
    def climate(self, *args): return climate()


def test_benchmark_profit_is_not_revenue_and_downside_holds_cost_fixed():
    wheat = next(c for c in catalog()["crops"] if c["id"] == "wheat")
    money = economics(wheat, 2, "rabi")
    assert money["yield_kg_ha"] == 3547
    assert money["surplus_inr_ha"] == round(35.47 * (2610-1264))
    assert money["surplus_for_area"] == round(35.47 * (2610-1264) * 2)
    assert money["downside_inr_ha"] == round(35.47 * 2610 * .75 * .8 - 35.47 * 1264 * 1.2)
    assert economics(wheat, 1, "kharif") is None


def test_top_three_sorted_by_surplus_after_filters():
    top, excluded, status = rank_crops(request(), soil(), climate(), {"status": "unavailable"})
    assert status == "provisional" and len(top) == 3
    assert [c["rank"] for c in top] == [1, 2, 3]
    assert [c["economics"]["surplus_inr_ha"] for c in top] == sorted([c["economics"]["surplus_inr_ha"] for c in top], reverse=True)
    assert "Soybean" in [c["crop"] for c in excluded]
    assert all("Water availability is unconfirmed" in c["cautions"] for c in top)


@pytest.mark.parametrize("ph", [0, 14])
def test_no_padding_with_unsuitable_crops(ph):
    assert rank_crops(request(), soil(ph), climate(), {})[2] == "no_match"


def test_missing_soil_or_climate_does_not_guess_or_rank():
    assert rank_crops(request(), {}, climate(), {}) == ([], [], "insufficient_data")
    assert rank_crops(request(), soil(), {}, {}) == ([], [], "insufficient_data")


def test_water_and_future_weather_are_not_assumed():
    assert rank_crops(request(irrigation="rainfed"), soil(), climate(monthly=0), {})[2] == "no_match"
    top, _, _ = rank_crops(request(irrigation="available"), soil(), climate(monthly=0), {})
    assert top and any("depends on adequate irrigation" in caution for c in top for caution in c["cautions"])


def test_each_month_checked_not_only_mean():
    weather = climate(); weather["monthly_temperature_c"]["10"] = 60
    assert rank_crops(request(), soil(), weather, {})[2] == "no_match"


def test_high_margin_crops_do_not_pass_on_survival_tolerance_alone():
    top, excluded, _ = rank_crops(request(irrigation="available"), soil(), climate(temp=18), {})
    assert "Groundnut" not in [c["name"] for c in top]
    assert any(c["crop"] == "Groundnut" and any("optimal temperature" in r for r in c["reasons"]) for c in excluded)
    _, excluded, _ = rank_crops(request(irrigation="available"), soil(), climate(temp=26), {})
    assert any(c["crop"] == "Wheat" and any("optimal temperature" in r for r in c["reasons"]) for c in excluded)


def test_rainfed_check_includes_dry_months_after_sowing():
    data = climate(); data["monthly_rain_mm"]["12"] = 0
    assert rank_crops(request(irrigation="rainfed"), soil(), data, {})[2] == "no_match"


def test_season_specific_yield_and_acre_conversion():
    maize = next(c for c in catalog()["crops"] if c["id"] == "maize")
    assert economics(maize, 1, "kharif")["yield_kg_ha"] == 2847
    assert economics(maize, 1, "rabi")["yield_kg_ha"] == 5206
    a = economics(maize, 0.40468564224, "rabi")
    assert a["surplus_for_area"] == round(52.06 * (2410-1544) * .40468564224)


def test_mainland_coverage():
    assert in_india(17.97, 79.59)
    assert in_india(30.9, 75.85)
    assert not in_india(27.7, 85.3)  # Kathmandu is inside India's bounding box.
    assert not in_india(0, 0)


def test_partial_outage_is_explicit():
    class FailedSoil(Provider):
        def soil(self, *args): raise DataUnavailable("No soil data")
    result = plan(request(), FailedSoil())
    assert result["status"] == "insufficient_data" and result["top_crops"] == []
    assert result["soil"]["message"] == "No soil data"
    assert "Live weather is unavailable" in result["warnings"][0]


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True, -1, "4"])
def test_non_measurements_rejected(value):
    with pytest.raises(DataUnavailable): number(value, 0, 100)


def test_geocoding_filters_country_and_caches():
    calls = []
    def handle(req):
        calls.append(req)
        return httpx.Response(200, json={"results": [
            {"name": "Hyderabad", "country_code": "IN", "latitude": 17.38, "longitude": 78.48, "admin1": "Telangana"},
            {"name": "Hyderabad", "country_code": "PK", "latitude": 25.4, "longitude": 68.3}]})
    p = PlanningData(httpx.MockTransport(handle))
    assert len(p.places("Hyderabad")) == 1
    assert p.places("Hyderabad")[0]["name"] == "Hyderabad, Telangana"
    assert len(calls) == 1


def test_historical_null_precipitation_is_not_zero():
    end = date.today().year-1; first=date(end-9,1,1); last=date(end,12,31)
    dates=[(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
    payload = {"daily_units": {"temperature_2m_mean": "°C", "precipitation_sum": "mm"},
               "daily": {"time": dates, "temperature_2m_mean": [25]*len(dates), "precipitation_sum": [None]*len(dates)}}
    p = PlanningData(httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    with pytest.raises(DataUnavailable): p.climate(17,78)
    payload["daily"]["precipitation_sum"] = [1]*len(dates)
    result = p.climate(17,78)
    assert result["annual_rain_mm"] == round(len(dates)/10,1)
    payload["daily"]["time"][1] = dates[0]
    with pytest.raises(DataUnavailable): p.climate(18,78)


def test_api_validation_and_no_client_soil_override():
    app.dependency_overrides[get_planning_data] = lambda: Provider()
    try:
        client = TestClient(app)
        data = request().model_dump(mode="json")
        assert client.post("/api/v1/planning/recommend", json=data).status_code == 200
        assert client.post("/api/v1/planning/recommend", json={**data, "latitude": 91}).status_code == 422
        assert client.post("/api/v1/planning/recommend", json={**data, "area_ha": 0}).status_code == 422
        assert client.post("/api/v1/planning/recommend", json={**data, "soil": {"ph": 7}}).status_code == 422
        assert client.post("/api/v1/planning/recommend", json={**data, "sowing_date": "2000-01-01"}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_planning_data)


def test_partial_soil_can_recover_on_retry(monkeypatch):
    p = PlanningData()
    results = iter([{"status": "partial", "measurements": {}}, soil()])
    monkeypatch.setattr(p, "_soil", lambda *args: next(results))
    assert p.soil(17.97, 79.59)["status"] == "partial"
    assert p.soil(17.97, 79.59)["status"] == "available"
    assert p.soil(17.97, 79.59)["measurements"]["ph"]["value"] == 6.5


def test_cache_does_not_serialize_different_providers():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.modules.planning.providers import Cache
    cache, barrier = Cache(), Barrier(2)
    def fetch():
        barrier.wait(timeout=3)
        return {"data": [1]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(cache.get, "weather", 60, fetch)
        b = pool.submit(cache.get, "climate", 60, fetch)
        first = a.result(); assert b.result() == first
    first["data"].append(2)
    assert cache.get("weather", 60, lambda: None) == {"data": [1]}


def test_raster_scaling_and_nodata(tmp_path, monkeypatch):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from app.modules.planning.providers import SOIL_LAYERS
    original_open = rasterio.open
    paths = {}
    for key, (layer, *_) in SOIL_LAYERS.items():
        path = tmp_path / f"{key}.tif"
        with original_open(path, "w", driver="GTiff", height=1, width=2, count=1,
                           dtype="uint8", crs="EPSG:4326", transform=from_origin(79, 19, 1, 1), nodata=255) as dst:
            dst.write(np.array([[{"ph": 67, "organic_carbon": 2, "sand": 40}[key], 255]], dtype="uint8"), 1)
        paths[layer] = path
    def mapped_open(url):
        return original_open(next(path for layer, path in paths.items() if layer in url))
    monkeypatch.setattr(rasterio, "open", mapped_open)
    p = PlanningData()
    values = p.soil(18.5, 79.5)["measurements"]
    assert [values[k]["value"] for k in ["ph", "organic_carbon", "sand"]] == [6.7, 1, 40]
    with pytest.raises(DataUnavailable): p.soil(18.5, 80.5)


def test_forecast_rejects_duplicate_dates_and_inverted_temperatures():
    from app.modules.planning.dates import today_in_india
    dates = [(today_in_india()+timedelta(days=i)).isoformat() for i in range(7)]
    data = {"daily_units": {"precipitation_sum": "mm", "temperature_2m_max": "°C", "temperature_2m_min": "°C"},
            "current_units": {"temperature_2m": "°C"}, "current": {"temperature_2m": 25, "time": dates[0]+"T12:00"},
            "daily": {"time": dates, "temperature_2m_max": [30]*7, "temperature_2m_min": [20]*7, "precipitation_sum": [0]*7}}
    p = PlanningData(httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    assert len(p.forecast(17, 78)["days"]) == 7
    data["daily"]["time"][1] = dates[0]
    with pytest.raises(DataUnavailable): p.forecast(18, 78)
    data["daily"]["time"][1] = (today_in_india()+timedelta(days=1)).isoformat()
    data["daily"]["temperature_2m_min"][0] = 40
    with pytest.raises(DataUnavailable): p.forecast(19, 78)


def test_boolean_coordinates_and_area_rejected():
    from pydantic import ValidationError
    for key in ["latitude", "longitude", "area_ha"]:
        data = request().model_dump()
        data[key] = True
        with pytest.raises(ValidationError): PlanRequest(**data)


def test_provider_retries_transient_failure_but_not_quota_errors():
    calls = []
    def recover(req):
        calls.append(req)
        return httpx.Response(503 if len(calls) == 1 else 200, json={"results": []})
    assert PlanningData(httpx.MockTransport(recover)).places("Warangal") == []
    assert len(calls) == 2
    calls.clear()
    def quota(req):
        calls.append(req)
        return httpx.Response(429, json={})
    with pytest.raises(DataUnavailable): PlanningData(httpx.MockTransport(quota)).places("Warangal")
    assert len(calls) == 1


def test_provider_recovers_after_two_transient_failures():
    calls = []
    def recover(req):
        calls.append(req)
        return httpx.Response(503 if len(calls) < 3 else 200, json={"results": []})
    assert PlanningData(httpx.MockTransport(recover)).places("Delhi") == []
    assert len(calls) == 3
