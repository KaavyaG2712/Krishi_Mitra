"""SHC v1.35, read-only GraphQL adapter. No scraping or guessed GPS endpoint.

The official JSON results schema/units require validation with the issued access.
Reject ambiguous units instead of silently treating area-level samples as field tests.
"""
import hashlib
import json
import logging
from datetime import date
from threading import RLock
from time import monotonic
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.modules.soil.models import Location, Measurement, SoilLookup, SoilProfile, SourceType

logger = logging.getLogger(__name__)
RESULT_KEYS = {"n": "nitrogen", "p": "phosphorus", "k": "potassium", "S": "sulphur", "Zn": "zinc", "Fe": "iron", "Cu": "copper", "Mn": "manganese", "B": "boron", "pH": "ph", "EC": "electricalConductivity", "OC": "organicCarbon"}
CARD_QUERY = """query SoilCards($state: String, $district: String) {
  getTestForAuthUser(state: $state, district: $district) {
    village sampleDate results
  }
}"""


class SoilServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class SoilHealthService:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.transport = transport
        self.token = settings.soil_health_api_token or None
        self.refresh_token = settings.soil_health_refresh_token or None
        self.cache: dict[str, tuple[float, object]] = {}
        self.lock = RLock()

    def _post(self, query: str, variables: dict, *, refreshing=False):
        if not self.token and not (refreshing and self.refresh_token):
            raise SoilServiceError("not_configured", "Government soil access is not connected yet. Enter your soil-test values manually.")
        parsed = urlparse(self.settings.soil_health_api_url)
        if parsed.scheme != "https" or parsed.hostname != "soilhealth4.dac.gov.in" or parsed.username or parsed.password:
            raise SoilServiceError("configuration", "The government soil connection needs administrator attention.")
        headers = {"Authorization": f"Bearer {self.token}", "token": self.token} if self.token else {}
        try:
            with httpx.Client(timeout=self.settings.soil_health_timeout_seconds, transport=self.transport, follow_redirects=False) as client:
                with client.stream("POST", self.settings.soil_health_api_url, json={"query": query, "variables": variables}, headers=headers) as response:
                    if response.status_code in {401, 403}:
                        raise SoilServiceError("authentication", "Government soil access has expired. Please try manual entry.")
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 2_000_000:
                            raise SoilServiceError("invalid_response", "The soil service returned too much data. Please try manual entry.", 502)
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError()
            if payload.get("errors"):
                errors = payload["errors"]
                if any(e.get("extensions", {}).get("code") in {"UNAUTHENTICATED", "FORBIDDEN"} for e in errors if isinstance(e, dict)):
                    raise SoilServiceError("authentication", "Government soil access needs renewal.")
                raise ValueError()
            if not isinstance(payload.get("data"), dict):
                raise ValueError()
            return payload["data"]
        except httpx.TimeoutException:
            raise SoilServiceError("timeout", "The government soil service took too long. Retry or enter values manually.", 504) from None
        except httpx.HTTPError:
            raise SoilServiceError("unavailable", "Government soil information is temporarily unavailable. Retry or enter values manually.") from None
        except (ValueError, TypeError, AttributeError):
            raise SoilServiceError("invalid_response", "We could not verify the soil service response. Please use your soil-test report.", 502) from None

    def _request(self, query: str, variables: dict):
        if not self.token and self.refresh_token:
            self._refresh()
        try:
            return self._post(query, variables)
        except SoilServiceError as error:
            if error.code != "authentication" or not self.refresh_token:
                raise
            self._refresh()
            return self._post(query, variables)

    def _refresh(self):
        data = self._post("query Token($refreshToken: String!) { generateAccessToken(refreshToken: $refreshToken) }", {"refreshToken": self.refresh_token}, refreshing=True)
        value = data.get("generateAccessToken")
        if not isinstance(value, dict) or not isinstance(value.get("token"), str) or not value["token"]:
            raise SoilServiceError("authentication", "Government soil access needs renewal.")
        self.token = value["token"]
        if isinstance(value.get("refreshToken"), str) and value["refreshToken"]:
            self.refresh_token = value["refreshToken"]
        logger.info("soil_token_refreshed")

    def _cached(self, key: str, operation):
        # Single-flight lock prevents simultaneous identical upstream requests.
        with self.lock:
            now = monotonic()
            self.cache = {k: v for k, v in self.cache.items() if v[0] > now}
            if key in self.cache:
                return self.cache[key][1], True
            started = monotonic()
            try:
                value = operation()
            except SoilServiceError as error:
                logger.warning("soil_request_failed", extra={"error_code": error.code})
                raise
            if len(self.cache) >= 256:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = (monotonic() + self.settings.soil_health_cache_seconds, value)
            logger.info("soil_request_completed", extra={"duration_ms": round((monotonic() - started) * 1000)})
            return value, False

    def locations(self, level: str, state: str = "", district: str = "", block: str = ""):
        if level == "states":
            query, variables, field = "query { getState }", {}, "getState"
        elif level in {"districts", "blocks"}:
            if not state or (level == "blocks" and not district):
                raise SoilServiceError("location_required", "Select the parent location first.", 422)
            query = "query Directory($state: ID, $subdistrict: Boolean) { getdistrictAndSubdistrictBystate(state: $state, subdistrict: $subdistrict) }"
            variables, field = {"state": state, "subdistrict": level == "blocks"}, "getdistrictAndSubdistrictBystate"
        else:
            if not district or not block:
                raise SoilServiceError("location_required", "Select district and block first.", 422)
            query = "query Villages($district: ID!, $subdistrict: String) { getVillageBydistrict(district: $district, subdistrict: $subdistrict) }"
            variables, field = {"district": district, "subdistrict": block}, "getVillageBydistrict"

        def fetch():
            raw = self._request(query, variables).get(field)
            if not isinstance(raw, list):
                raise SoilServiceError("invalid_response", "The location directory is unavailable. Please enter your soil values manually.", 502)
            items = []
            for item in raw:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("id", item.get("_id")), str):
                    raise SoilServiceError("invalid_response", "The location directory could not be verified.", 502)
                # Never guess a block's district when the provider omits it.
                if level == "blocks":
                    parent = item.get("district", item.get("district_id"))
                    if isinstance(parent, dict):
                        parent = parent.get("id", parent.get("_id"))
                    if parent is None:
                        raise SoilServiceError("invalid_response", "The provider has not supplied district links for blocks.", 502)
                    if parent != district:
                        continue
                items.append({"id": item.get("id", item.get("_id")), "name": item["name"]})
            return items
        return self._cached(json.dumps([level, variables, district], sort_keys=True), fetch)[0]

    def lookup(self, request: SoilLookup):
        if request.latitude is not None:
            raise SoilServiceError("gps_lookup_unavailable", "GPS was received once, but the official API does not offer coordinate lookup. Select your location manually; coordinates have not been saved.", 422)
        if not self.settings.soil_health_area_access:
            raise SoilServiceError("area_access_unavailable", "Government soil information for an area is not connected yet. Enter your soil-test values manually.")
        key = hashlib.sha256(request.model_dump_json().encode()).hexdigest()

        def fetch():
            # Resolve display names from authoritative directory responses and
            # verify each parent relationship instead of signing browser labels.
            location = request.location.model_copy()
            for level, id_field, name_field in [("states", "state_id", "state"), ("districts", "district_id", "district"), ("blocks", "block_id", "block"), ("villages", "village_id", "village")]:
                options = self.locations(level, location.state_id, location.district_id, location.block_id)
                match = next((item for item in options if item["id"] == getattr(location, id_field)), None)
                if match is None:
                    raise SoilServiceError("invalid_location", "The selected location is no longer in the directory. Select it again.", 422)
                setattr(location, name_field, match["name"])
            raw = self._request(CARD_QUERY, {"state": location.state_id, "district": location.district_id}).get("getTestForAuthUser")
            if not isinstance(raw, list):
                raise SoilServiceError("invalid_response", "The government soil response could not be verified.", 502)
            candidates = []
            for record in raw:
                if not isinstance(record, dict):
                    raise SoilServiceError("invalid_response", "The government soil response could not be verified.", 502)
                village = record.get("village")
                if isinstance(village, dict):
                    village = village.get("id", village.get("_id"))
                if village == location.village_id:
                    candidates.append(self.normalize(record, location))
            if not candidates:
                return None
            return max(candidates, key=lambda p: p.sample_date or date.min)
        return self._cached(key, fetch)

    def normalize(self, record: dict, location: Location) -> SoilProfile:
        try:
            results = record["results"]
            units = json.loads(self.settings.soil_health_units_json)
            if not isinstance(results, dict) or not isinstance(units, dict):
                raise ValueError()
            parameters = {}
            for source_key, target_key in RESULT_KEYS.items():
                value = results.get(source_key)
                if value is None:
                    continue
                if isinstance(value, dict):
                    parameters[target_key] = Measurement.model_validate(value)
                else:
                    if source_key not in units:
                        raise ValueError("Unit not documented")
                    parameters[target_key] = Measurement(value=value, unit=units[source_key])
            sample_date = record.get("sampleDate")
            if sample_date is not None:
                sample_date = date.fromisoformat(sample_date[:10])
            return SoilProfile(parameters=parameters, location=location, sample_date=sample_date,
                               source="Government of India Soil Health Card", source_type=SourceType.GOVERNMENT_VERIFIED,
                               coverage="area_sample")
        except (ValueError, KeyError, TypeError, ValidationError):
            raise SoilServiceError("invalid_response", "The soil values or their units could not be verified. Please use your laboratory report.", 502) from None
