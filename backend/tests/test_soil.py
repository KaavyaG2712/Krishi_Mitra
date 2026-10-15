import json
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import verify
from app.main import app
from app.api.v1.endpoints.soil import get_soil_service
from app.modules.soil.models import Location, SoilInput, SoilLookup
from app.modules.soil.service import SoilHealthService, SoilServiceError

LOCATION = Location(state_id="s", district_id="d", block_id="b", village_id="v", state="State", district="District", block="Block", village="Village")


def service(handler, **kwargs):
    def with_directory(request):
        query = json.loads(request.content)["query"]
        variables = json.loads(request.content)["variables"]
        if query == "query { getState }":
            return httpx.Response(200, json={"data": {"getState": [{"id": "s", "name": "State"}]}})
        if "getdistrictAndSubdistrictBystate" in query:
            if variables["subdistrict"]:
                return httpx.Response(200, json={"data": {"getdistrictAndSubdistrictBystate": [{"id": "b", "name": "Block", "district": "d"}]}})
            return httpx.Response(200, json={"data": {"getdistrictAndSubdistrictBystate": [{"id": "d", "name": "District"}]}})
        if "getVillageBydistrict" in query:
            return httpx.Response(200, json={"data": {"getVillageBydistrict": [{"id": "v", "name": "Village"}]}})
        return handler(request)
    return SoilHealthService(Settings(_env_file=None, soil_health_api_token="test-token", soil_health_area_access=True, **kwargs), httpx.MockTransport(with_directory))


def response(records):
    return httpx.Response(200, json={"data": {"getTestForAuthUser": records}})


@pytest.mark.parametrize("measurement", [{"value": -1, "unit": "pH"}, {"value": 14.1, "unit": "pH"}, {"value": "7", "unit": "pH"}, {"value": True, "unit": "pH"}, {"value": float("nan"), "unit": "pH"}, {"value": 7, "unit": "kg/ha"}])
def test_impossible_or_ambiguous_values_rejected(measurement):
    with pytest.raises(ValidationError):
        SoilInput(parameters={"ph": measurement})


def test_manual_profile_and_token():
    result = TestClient(app).post("/api/v1/soil/manual", json={"parameters": {"ph": {"value": 7.1, "unit": "pH"}, "nitrogen": {"value": 0, "unit": "mg/kg"}}})
    assert result.status_code == 200
    payload = result.json()
    assert payload["profile"]["source_type"] == "USER_ENTERED"
    assert payload["profile"]["parameters"]["nitrogen"]["value"] == 0
    assert "potassium" not in payload["profile"]["parameters"]
    assert payload["recommendation"]["fertilizer_dosages"] == []
    assert verify(payload["profile_token"], "soil")["parameters"]["ph"]["value"] == 7.1


@pytest.mark.parametrize("payload", [{"parameters": {}}, {"parameters": {"organicCarbon": {"value": 101, "unit": "%"}}}, {"parameters": {"ph": {"value": 7, "unit": "pH"}}, "source_type": "GOVERNMENT_VERIFIED"}, {"parameters": {"ph": {"value": 7, "unit": "pH"}}, "sample_date": str(date.today() + timedelta(days=1))}])
def test_manual_invalid_api_requests(payload):
    assert TestClient(app).post("/api/v1/soil/manual", json=payload).status_code == 422


def test_government_success_latest_record_units_and_cache():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer test-token"
        assert "farmer" not in json.loads(request.content)["query"]
        return response([
            {"village": "other", "results": {"n": 999}},
            {"village": "v", "sampleDate": "2020-01-01", "results": {"pH": {"value": 6, "unit": "pH"}}},
            {"village": "v", "sampleDate": "2024-01-01", "results": {"pH": {"value": 7.1, "unit": "pH"}}},
        ])
    provider = service(handler)
    profile, cached = provider.lookup(SoilLookup(location=LOCATION))
    assert not cached and profile.parameters["ph"].value == 7.1
    assert profile.source_type == "GOVERNMENT_VERIFIED" and profile.coverage == "area_sample"
    assert provider.lookup(SoilLookup(location=LOCATION))[1]
    assert len(calls) == 1


def test_missing_government_data():
    provider = service(lambda _: response([]))
    app.dependency_overrides[get_soil_service] = lambda: provider
    try:
        result = TestClient(app).post("/api/v1/soil/lookup", json={"location": LOCATION.model_dump()})
    finally:
        app.dependency_overrides.clear()
    assert result.status_code == 200 and result.json()["profile"] is None
    assert "profile_token" not in result.json()


@pytest.mark.parametrize("record", [{"village": "v", "results": {"n": 100}}, {"village": "v", "results": {}}, {"village": "v", "results": {"pH": {"value": 99, "unit": "pH"}}}, {"village": "v", "sampleDate": "bad", "results": {"pH": {"value": 7, "unit": "pH"}}}])
def test_invalid_provider_data_fails_closed(record):
    with pytest.raises(SoilServiceError, match="could not be verified"):
        service(lambda _: response([record])).lookup(SoilLookup(location=LOCATION))


def test_timeout_not_cached():
    def handler(request):
        raise httpx.ReadTimeout("private provider details", request=request)
    provider = service(handler)
    with pytest.raises(SoilServiceError) as error:
        provider.lookup(SoilLookup(location=LOCATION))
    assert error.value.code == "timeout"
    assert not any(isinstance(value[1], type(None)) for value in provider.cache.values())
    assert "private" not in error.value.message


def test_expired_access_token_refreshes_once():
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        if "generateAccessToken" in calls[-1]["query"]:
            return httpx.Response(200, json={"data": {"generateAccessToken": {"token": "new-token", "refreshToken": "new-refresh"}}})
        if request.headers["token"] == "test-token":
            return httpx.Response(401)
        return response([])
    provider = service(handler, soil_health_refresh_token="refresh")
    assert provider.lookup(SoilLookup(location=LOCATION))[0] is None
    assert len(calls) == 3 and provider.refresh_token == "new-refresh"


def test_directory_hierarchy_and_gps_fallback():
    provider = SoilHealthService(Settings(_env_file=None, soil_health_api_token="test-token"), httpx.MockTransport(lambda _: httpx.Response(200, json={"data": {"getdistrictAndSubdistrictBystate": [{"id": "b", "name": "Block", "district": "d"}, {"id": "x", "name": "Other", "district": "elsewhere"}]}})))
    assert provider.locations("blocks", "s", "d") == [{"id": "b", "name": "Block"}]
    with pytest.raises(SoilServiceError) as error:
        provider.lookup(SoilLookup(latitude=11, longitude=78))
    assert error.value.code == "gps_lookup_unavailable"


def test_demo_is_disabled_by_default_and_real_lookup_never_uses_demo():
    assert TestClient(app).get("/api/v1/soil/demo").status_code == 404
    provider = SoilHealthService(Settings(_env_file=None, soil_health_demo=True))
    with pytest.raises(SoilServiceError):
        provider.lookup(SoilLookup(location=LOCATION))


def test_authoritative_units_are_preserved_without_conversion():
    provider = service(lambda _: response([{"village": "v", "results": {"n": {"value": 70.5, "unit": "kg/acre"}}}]))
    profile, _ = provider.lookup(SoilLookup(location=LOCATION))
    assert profile.parameters["nitrogen"].unit == "kg/acre"
    assert profile.parameters["nitrogen"].value == 70.5
