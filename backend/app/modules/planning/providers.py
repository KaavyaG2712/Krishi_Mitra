"""Read public data only. Unknown/nodata values never become measurements.

OpenLandMap v0.2: mapped predictions at 10 cm depth, nominal 250 m pixels.
Read COG windows via HTTP Range; never download a global raster per request.
"""
import copy
import json
import logging
import math
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from time import monotonic, sleep
from urllib.parse import urlsplit

import httpx
from app.core.config import get_settings
from app.modules.planning.dates import today_in_india

DATA = Path(__file__).parent / "data"
SOIL_URL = "https://s3.openlandmap.org/arco/"
SOIL_LAYERS = {
    "ph": ("ph.h2o_usda.4c1a2a", 0.1, "pH", 14),
    "organic_carbon": ("organic.carbon_usda.6a1c", 0.5, "%", 100),
    "sand": ("sand.wfraction_usda.3a1a1a", 1, "%", 100),
}
_NOMINATIM_LOCK = RLock()
_NOMINATIM_LAST_REQUEST = 0.0
_LOGGER = logging.getLogger("app")


class DataUnavailable(Exception):
    pass


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise DataUnavailable("The source returned incomplete or invalid measurements.")
    return float(value)


class Cache:
    def __init__(self, size=256):
        self.items, self.lock, self.size = OrderedDict(), RLock(), size
        self.pending = {}

    def get(self, key, ttl, operation, cache_if=lambda value: True):
        # Coalesce identical lookups without blocking unrelated providers/places.
        with self.lock:
            found = self.items.get(key)
            if found and monotonic() - found[0] < ttl:
                self.items.move_to_end(key)
                return copy.deepcopy(found[1])
            owner = key not in self.pending
            future = self.pending.setdefault(key, Future())
        if not owner:
            return copy.deepcopy(future.result())
        try:
            value = operation()
            with self.lock:
                if cache_if(value):
                    self.items[key] = (monotonic(), value)
                    self.items.move_to_end(key)
                    while len(self.items) > self.size:
                        self.items.popitem(last=False)
                future.set_result(value)
            return copy.deepcopy(value)
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.pending.pop(key, None)


class PlanningData:
    def __init__(self, transport=None):
        self.transport = transport
        self.cache = Cache()
        self.soil_cache = Cache()

    def json(self, url, params):
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                return self._json(url, params)
            except httpx.HTTPError as error:
                status_code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
                transient = isinstance(error, httpx.RequestError) or (
                    isinstance(error, httpx.HTTPStatusError) and status_code in {408, 429, 500, 502, 503, 504})
                _LOGGER.warning(
                    "planning_data_source_failed",
                    extra={"source": urlsplit(url).hostname or "unknown", "error_type": type(error).__name__,
                           "status_code": status_code, "attempt": attempt + 1},
                )
                if transient and attempt + 1 < max_attempts:
                    # Short backoff lets a transient upstream restart or network
                    # blip recover without holding the recommendation request
                    # for the much longer SDK default retry intervals.
                    retry_after = None
                    if isinstance(error, httpx.HTTPStatusError):
                        retry_after = error.response.headers.get("Retry-After")
                    try:
                        delay = min(float(retry_after), 2.0) if retry_after is not None else 0.5 * (attempt + 1)
                    except ValueError:
                        delay = 0.5 * (attempt + 1)
                    sleep(delay)
                    continue
                raise DataUnavailable("The data service could not be reached. Please retry.") from None

    def _json(self, url, params):
        try:
            with httpx.Client(timeout=httpx.Timeout(18, connect=5), transport=self.transport) as client:
                with client.stream("GET", url, params=params) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > 2_000_000:
                            raise DataUnavailable("The source response is too large.")
            value = json.loads(content)
            if not isinstance(value, dict) or value.get("error"):
                raise DataUnavailable("The source could not provide data for this location.")
            return value
        except ValueError:
            raise DataUnavailable("The data service could not be reached. Please retry.") from None

    def places(self, name):
        def fetch():
            payload = self.json("https://geocoding-api.open-meteo.com/v1/search", {"name": name, "count": 8, "countryCode": "IN", "language": "en", "format": "json"})
            rows = payload.get("results", [])
            if not isinstance(rows, list):
                raise DataUnavailable("Location search returned an invalid response.")
            result = []
            for r in rows:
                if not isinstance(r, dict) or r.get("country_code") != "IN":
                    continue
                lat, lon = number(r.get("latitude"), -90, 90), number(r.get("longitude"), -180, 180)
                result.append({"latitude": lat, "longitude": lon,
                               "name": ", ".join(str(r[k])[:80] for k in ["name", "admin2", "admin1"] if r.get(k))[:180],
                               "district": str(r.get("admin2") or "")[:100] or None,
                               "state": str(r.get("admin1") or "")[:100] or None})
            return result
        return self.cache.get(("places", name.casefold()), 86400, fetch)

    def administrative_area(self, lat, lon):
        """Resolve the district/state needed to match a GPS point to the DLD table."""
        def fetch():
            global _NOMINATIM_LAST_REQUEST
            try:
                with _NOMINATIM_LOCK:
                    wait = 1.1 - (monotonic() - _NOMINATIM_LAST_REQUEST)
                    if wait > 0:
                        sleep(wait)
                    _NOMINATIM_LAST_REQUEST = monotonic()
                    with httpx.Client(timeout=httpx.Timeout(12, connect=5),
                                       headers={"User-Agent": "KrishiMitra crop-yield research demo"},
                                       transport=self.transport) as client:
                        response = client.get("https://nominatim.openstreetmap.org/reverse", params={
                            "lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10, "addressdetails": 1,
                        })
                        response.raise_for_status()
                        payload = response.json()
            except (httpx.HTTPError, ValueError):
                raise DataUnavailable("Location could not be matched to a historical district. Search for the nearest town instead.") from None
            address = payload.get("address", {}) if isinstance(payload, dict) else {}
            district = address.get("state_district") or address.get("county") or address.get("district")
            state = address.get("state")
            if not isinstance(district, str) or not isinstance(state, str):
                raise DataUnavailable("Location lookup did not return a district and state. Search for the nearest town instead.")
            return {"district": district[:100], "state": state[:100]}
        return self.cache.get(("admin-area", round(lat, 3), round(lon, 3)), 86400, fetch)

    def soil(self, lat, lon):
        # Cache actual raster cells rather than assigning one city's soil to a district.
        key = (math.floor(lon * 480), math.floor(lat * 480))
        return self.soil_cache.get(key, 86400, lambda: self._soil(lat, lon),
                                   cache_if=lambda value: value["status"] == "available")

    def _soil(self, lat, lon):
        try:
            import rasterio
            from rasterio.windows import Window
        except ImportError:
            raise DataUnavailable("Automatic soil lookup needs the backend rasterio dependency. Reinstall backend dependencies.") from None

        def sample(item):
            key, (layer, scale, unit, upper) = item
            url = SOIL_URL + f"{layer}_m_250m_b10cm_19500101_20171231_go_epsg.4326_v0.2.tif"
            try:
                with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                                  GDAL_HTTP_CONNECTTIMEOUT="8", GDAL_HTTP_TIMEOUT="30", GDAL_HTTP_MAX_RETRY="3",
                                  GDAL_HTTP_RETRY_DELAY="1",
                                  VSI_CACHE=True, VSI_CACHE_SIZE=5_000_000):
                    with rasterio.open(url) as src:
                        if src.crs.to_epsg() != 4326:
                            raise DataUnavailable("Unexpected soil map coordinate system.")
                        row, col = src.index(lon, lat)
                        if not (0 <= row < src.height and 0 <= col < src.width):
                            return key, None
                        pixel = src.read(1, window=Window(col, row, 1, 1), masked=True)
                        if pixel.size != 1 or bool(pixel.mask.any()):
                            return key, None
                        value = number(float(pixel[0, 0]) * scale, 0, upper)
                        return key, {"value": round(value, 2), "unit": unit, "source_url": url}
            except (rasterio.errors.RasterioError, DataUnavailable, ValueError, OSError) as error:
                _LOGGER.warning(
                    "planning_soil_layer_failed",
                    extra={"source": "s3.openlandmap.org", "layer": key, "error_type": type(error).__name__},
                )
                return key, None
        with ThreadPoolExecutor(max_workers=3) as pool:
            measurements = {k: v for k, v in pool.map(sample, SOIL_LAYERS.items()) if v is not None}
        if not measurements:
            raise DataUnavailable("The soil map is unavailable or has no land data here. Retry or choose a nearby place; no soil values were guessed.")
        return {"status": "available" if len(measurements) == 3 else "partial", "measurements": measurements,
                "source": "OpenLandMap v0.2", "source_url": "https://docs.openlandmap.org/016-project.html",
                "resolution_m": 250, "depth_cm": 10, "reference_period": "1950–2017 input compilation; v0.2",
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "kind": "mapped_estimate",
                "note": "Predicted value for a map cell at 10 cm depth, not a village survey average or a current field test. N, P, K, EC and micronutrients are unavailable from these layers."}

    def forecast(self, lat, lon):
        def fetch():
            try:
                p = self.json("https://api.open-meteo.com/v1/forecast", {
                    "latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "forecast_days": 7,
                    "current": "temperature_2m,relative_humidity_2m", "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum"})
                daily, units, current = p["daily"], p["daily_units"], p["current"]
                if units["precipitation_sum"] != "mm" or units["temperature_2m_max"] != "°C" or units["temperature_2m_min"] != "°C" or p["current_units"]["temperature_2m"] != "°C":
                    raise ValueError()
                dates = daily["time"]
                today = today_in_india()
                if dates != [(today + timedelta(days=i)).isoformat() for i in range(7)]:
                    raise ValueError()
                for field in ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"]:
                    if len(daily[field]) != 7:
                        raise ValueError()
                days = [{"date": day, "high_c": number(daily["temperature_2m_max"][i], -90, 65),
                         "low_c": number(daily["temperature_2m_min"][i], -90, 65),
                         "rain_mm": number(daily["precipitation_sum"][i], 0, 1500)} for i, day in enumerate(dates)]
                if any(day["low_c"] > day["high_c"] for day in days):
                    raise ValueError()
                return {"status": "available", "temperature_c": number(current["temperature_2m"], -90, 65),
                        "observed_at": current["time"], "days": days,
                        "source": "Open-Meteo model weather", "source_url": "https://open-meteo.com/",
                        "retrieved_at": datetime.now(timezone.utc).isoformat()}
            except (DataUnavailable, KeyError, TypeError, ValueError, IndexError):
                key = get_settings().weatherapi_key
                if not key:
                    raise DataUnavailable("Live weather is unavailable from the primary provider. Add WEATHERAPI_KEY to the backend environment to enable the backup forecast.") from None
                try:
                    p = self.json("https://api.weatherapi.com/v1/forecast.json", {
                        "key": key, "q": f"{lat},{lon}", "days": 3, "aqi": "no", "alerts": "no"})
                    current = p["current"]
                    rows = p["forecast"]["forecastday"]
                    today = today_in_india()
                    expected_dates = [(today + timedelta(days=i)).isoformat() for i in range(3)]
                    if [row["date"] for row in rows] != expected_dates:
                        raise ValueError()
                    days = [{"date": row["date"], "high_c": number(row["day"]["maxtemp_c"], -90, 65),
                             "low_c": number(row["day"]["mintemp_c"], -90, 65),
                             "rain_mm": number(row["day"]["totalprecip_mm"], 0, 1500)} for row in rows]
                    if any(day["low_c"] > day["high_c"] for day in days):
                        raise ValueError()
                    return {"status": "available", "temperature_c": number(current["temp_c"], -90, 65),
                            "observed_at": current["last_updated"], "days": days,
                            "source": "WeatherAPI.com live weather", "source_url": "https://www.weatherapi.com/",
                            "retrieved_at": datetime.now(timezone.utc).isoformat()}
                except (DataUnavailable, KeyError, TypeError, ValueError, IndexError):
                    raise DataUnavailable("Live weather providers are unavailable or returned incomplete data. Please retry later.") from None
        return self.cache.get(("forecast", round(lat, 2), round(lon, 2), today_in_india().isoformat()), 1800, fetch)

    def climate(self, lat, lon):
        # Ten complete past calendar years. Keep annual rainfall and monthly
        # temperatures separate from the seven-day forecast.
        end = today_in_india().year - 1
        def fetch():
            p = self.json("https://archive-api.open-meteo.com/v1/archive", {
                "latitude": lat, "longitude": lon, "start_date": f"{end-9}-01-01", "end_date": f"{end}-12-31",
                "daily": "temperature_2m_mean,precipitation_sum", "timezone": "Asia/Kolkata", "models": "era5"})
            try:
                d, units = p["daily"], p["daily_units"]
                if units["temperature_2m_mean"] != "°C" or units["precipitation_sum"] != "mm":
                    raise ValueError()
                first, last = date(end-9, 1, 1), date(end, 12, 31)
                expected = [(first + timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
                if d["time"] != expected or len(d["temperature_2m_mean"]) != len(expected) or len(d["precipitation_sum"]) != len(expected):
                    raise ValueError()
                months = {m: [] for m in range(1, 13)}
                rain = {m: 0.0 for m in range(1, 13)}
                for day, temp, precip in zip(d["time"], d["temperature_2m_mean"], d["precipitation_sum"]):
                    m = int(day[5:7]); months[m].append(number(temp, -90, 65)); rain[m] += number(precip, 0, 1500)
                return {"status": "available", "period": f"{end-9}–{end}", "annual_rain_mm": round(sum(rain.values()) / 10, 1),
                        "monthly_temperature_c": {str(m): round(sum(v)/len(v), 1) for m, v in months.items()},
                        "monthly_rain_mm": {str(m): round(v/10, 1) for m, v in rain.items()},
                        "source": "Open-Meteo / ERA5 ten-year climate baseline", "source_url": "https://open-meteo.com/en/docs/historical-weather-api"}
            except (KeyError, TypeError, ValueError):
                raise DataUnavailable("Historical weather is incomplete; crop climate screening cannot be completed.") from None
        return self.cache.get(("climate", round(lat, 2), round(lon, 2), end), 86400, fetch)
