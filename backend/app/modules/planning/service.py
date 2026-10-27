"""A transparent planning comparison, not a trained profit prediction model."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from functools import lru_cache

from app.modules.planning.models import PlanRequest
from app.modules.planning.dates import today_in_india
from app.modules.planning.providers import DATA, DataUnavailable, PlanningData


@lru_cache
def catalog():
    return json.loads((DATA / "crops.json").read_text(encoding="utf-8"))


def in_ring(lon, lat, ring):
    inside = False
    for i, (x, y) in enumerate(ring):
        previous_x, previous_y = ring[i-1]
        if (y > lat) != (previous_y > lat) and lon < (previous_x-x)*(lat-y)/(previous_y-y)+x:
            inside = not inside
    return inside


def in_india(lat, lon):
    geometry = json.loads((DATA / "india.geojson").read_text())
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return any(in_ring(lon, lat, p[0]) and not any(in_ring(lon, lat, hole) for hole in p[1:]) for p in polygons)


def season_for(month):
    return "rabi" if month in [9, 10, 11, 12] else "summer" if month in [1, 2, 3, 4, 5] else "kharif"


def economics(crop, area, season):
    yields = crop["yields_kg_ha"]
    # Only use a documented season, otherwise an explicitly annual benchmark.
    yield_kg = yields.get(season, yields.get("annual"))
    if yield_kg is None:
        return None
    quintals = yield_kg / 100
    revenue = quintals * crop["price_inr_quintal"]
    costs = quintals * crop["cost_inr_quintal"]
    margin = revenue - costs
    return {"yield_kg_ha": yield_kg, "yield_scope": "National annual average" if "annual" in yields else f"National {season} average",
            "price_inr_quintal": crop["price_inr_quintal"], "cost_inr_quintal": crop["cost_inr_quintal"],
            "marketing_season": crop["marketing_season"], "price_kind": crop["price_kind"], "cost_basis": crop["cost_basis"],
            "revenue_inr_ha": round(revenue), "cost_inr_ha": round(costs), "surplus_inr_ha": round(margin),
            "surplus_for_area": round(margin * area),
            # Fixed benchmark cultivation cost stays fixed when yield falls.
            "downside_inr_ha": round(revenue * 0.75 * 0.8 - costs * 1.2),
            "break_even_price_inr_quintal": crop["cost_inr_quintal"],
            "source_url": crop["economics_source"]}


def rank_crops(request, soil, climate, forecast, candidate_limit=3):
    ph = soil.get("measurements", {}).get("ph", {}).get("value")
    if ph is None or climate.get("status") != "available":
        return [], [], "insufficient_data"
    month = request.sowing_date.month
    months = [str((month+i-1) % 12+1) for i in range(4)]
    temperatures = [climate["monthly_temperature_c"][m] for m in months]
    mean_temp = sum(temperatures) / len(temperatures)
    annual_rain = climate["annual_rain_mm"]
    growing_rain = [climate["monthly_rain_mm"][m] for m in months]
    eligible, excluded = [], []
    for crop in catalog()["crops"]:
        reasons, cautions, failures = [], [], []
        req = crop["requirements"]
        if month not in crop["sowing_months"]:
            failures.append("Outside the catalogue's indicative sowing window")
        if not req["ph"]["min"] <= ph <= req["ph"]["max"]:
            failures.append("Mapped pH is outside the FAO absolute range")
        else:
            reasons.append(f"Area pH {ph:g} is within the published range {req['ph']['min']:g}–{req['ph']['max']:g}")
            if not req["ph"]["optimal_min"] <= ph <= req["ph"]["optimal_max"]:
                cautions.append("Mapped pH is outside the FAO optimal range")
        if any(not req["temperature"]["min"] <= t <= req["temperature"]["max"] for t in temperatures):
            cautions.append("Historical temperatures extend beyond the published broad crop range; verify local variety and season guidance")
        else:
            reasons.append(f"Four-month historical mean temperature {mean_temp:.1f} °C; monthly means are within the broad published range")
        if not req["temperature"]["optimal_min"] <= mean_temp <= req["temperature"]["optimal_max"]:
            cautions.append("Four-month historical mean is outside the published optimal temperature range")
        dry = annual_rain < req["annual_rain"]["min"] or any(r < 30 for r in growing_rain)
        if annual_rain > req["annual_rain"]["max"]:
            cautions.append("Annual rainfall exceeds the FAO range; drainage and local seasonal conditions need review")
        if dry and request.irrigation == "rainfed":
            failures.append("Dry climate or a growing month below the application's 30 mm rainfall screening threshold; irrigation or verified stored moisture is needed")
        elif dry:
            cautions.append("This option depends on adequate irrigation or verified stored soil moisture; rainfall alone is insufficient in this screen")
        if request.irrigation == "unknown":
            cautions.append("Water availability is unconfirmed")
        if (request.sowing_date - today_in_india()).days <= 6 and forecast.get("status") == "available":
            relevant = [d for d in forecast["days"] if d["date"] >= request.sowing_date.isoformat()]
            if any(d["high_c"] > req["temperature"]["max"] or d["low_c"] < req["temperature"]["min"] for d in relevant):
                cautions.append("Near-term forecast temperatures extend outside the crop range; review sowing timing")
            if any(d["rain_mm"] >= 50 for d in relevant):
                cautions.append("Heavy rain is forecast near sowing; check field drainage and timing")
        money = economics(crop, request.area_ha, season_for(month))
        if money is None:
            failures.append("No matching yield benchmark for this season")
        if failures:
            excluded.append({"crop": crop["name"], "reasons": failures})
            continue
        eligible.append({"id": crop["id"], "name": crop["name"], "reasons": reasons, "cautions": cautions,
                         "economics": money, "requirements_source": crop["requirements_source"],
                         "status": "provisional", "sowing_months": crop["sowing_months"]})
    eligible.sort(key=lambda c: (-c["economics"]["surplus_inr_ha"], c["name"]))
    for i, crop in enumerate(eligible):
        crop["rank"] = i+1
    return (eligible if candidate_limit is None else eligible[:candidate_limit]), excluded, "provisional" if eligible else "no_match"


def plan(request: PlanRequest, provider: PlanningData, candidate_limit=3):
    if not in_india(request.latitude, request.longitude):
        raise DataUnavailable("This crop catalogue covers mainland India. Choose a location within that coverage; island and border coverage is not yet supported.")
    def read(name):
        try:
            return getattr(provider, name)(request.latitude, request.longitude)
        except DataUnavailable as error:
            return {"status": "unavailable", "message": str(error)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        soil, forecast, climate = list(pool.map(read, ["soil", "forecast", "climate"]))
    top, excluded, status = rank_crops(request, soil, climate, forecast, candidate_limit)
    warnings = [
        "Ranks compare only the nine crops in this catalogue that pass the screening rules. They do not establish the most profitable crops in your village.",
        "Income figures are benchmark surplus over A2+FL costs, not full net profit. They exclude the full opportunity cost of owned land/capital and are not a farm-specific budget.",
        "MSP is a reference scenario, not a current mandi price or guaranteed selling price. Confirm buyer, procurement eligibility, transport and local costs before planting.",
        "Sowing windows and the four-month climate screen are indicative. Local varieties, crop duration, drainage, nutrients, salinity, irrigation and market access still require review.",
        "The downside scenario assumes 25% less yield, 20% lower selling price and 20% higher cultivation cost. It is a stress test, not a statistical confidence interval.",
    ]
    if forecast["status"] == "unavailable":
        warnings.insert(0, "Live weather is unavailable. The shortlist uses historical climate only; retry before deciding when to sow.")
    if (request.sowing_date - today_in_india()).days > 6:
        warnings.insert(0, "The available live forecast covers only the near term; it does not forecast the selected future sowing date.")
    return {"status": status, "request": request.model_dump(mode="json"), "generated_at": datetime.now(timezone.utc).isoformat(),
            "soil": soil, "forecast": forecast, "climate": climate, "top_crops": top, "excluded": excluded,
            "warnings": warnings, "catalog_version": catalog()["version"], "yield_source": catalog()["yield_source"],
            "yield_period": catalog()["yield_period"], "ranking_basis": "Descending benchmark surplus per hectare after soil, temperature, sowing-window and water screening"}
