"""Historical DLD yield estimates used by the optional Module 2 ML comparison."""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from app.modules.planning.dates import today_in_india
from app.modules.planning.providers import DataUnavailable

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATASET_PATH = PROJECT_ROOT / "data" / "raw" / "crop-yield-benchmark" / "crop_yield.csv"
CATALOG_PATH = PROJECT_ROOT / "backend" / "app" / "modules" / "planning" / "data" / "crops.json"
SOURCE_URL = "https://tci.cornell.edu/data/"
FEATURES_CATEGORICAL = ["state", "district", "crop"]
FEATURES_NUMERIC = ["year"]


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _pipeline(model, ColumnTransformer, OneHotEncoder, Pipeline) -> Pipeline:
    transform = ColumnTransformer([
        ("category", OneHotEncoder(handle_unknown="ignore"), FEATURES_CATEGORICAL),
        ("year", "passthrough", FEATURES_NUMERIC),
    ])
    return Pipeline([("features", transform), ("model", model)])


@lru_cache(maxsize=1)
def _trained_models():
    if not DATASET_PATH.is_file():
        raise DataUnavailable("The local ICRISAT crop-yield dataset is not installed; the ML engine is unavailable.")
    try:
        import numpy as np
        import pandas as pd
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder
        from xgboost import XGBRegressor
    except ImportError:
        raise DataUnavailable("Install the optional crop-benchmark backend dependencies to enable the ML engine.") from None
    try:
        frame = pd.read_csv(DATASET_PATH, usecols=["state", "district", "year", "crop", "yield"])
    except (OSError, ValueError, pd.errors.ParserError):
        raise DataUnavailable("The local crop-yield dataset could not be read; the ML engine is unavailable.") from None
    frame["crop"] = frame["crop"].astype(str).str.strip().str.upper()
    supported = {
        "WHEAT", "CHICKPEA", "RAPESEED AND MUSTARD", "MAIZE", "KHARIF SORGHUM",
        "RABI SORGHUM", "PEARL MILLET", "GROUNDNUT", "SOYABEAN", "SUNFLOWER",
    }
    frame = frame[frame["crop"].isin(supported)].copy()
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    frame["yield"] = pd.to_numeric(frame["yield"], errors="coerce")
    frame = frame.dropna(subset=["state", "district", "year", "yield"])
    frame = frame[np.isfinite(frame["yield"]) & (frame["yield"] > 0)]
    frame["year"] = frame["year"].astype(int)
    if len(frame) < 1000:
        raise DataUnavailable("The local crop-yield dataset has too few usable records for the ML engine.")
    district_coverage = sorted(
        ({"state": str(row.state), "district": str(row.district)}
         for row in frame[["state", "district"]].drop_duplicates().itertuples(index=False)),
        key=lambda item: (item["state"].casefold(), item["district"].casefold()),
    )
    # Sample within every state/district/crop group so the bounded training set
    # retains geographic coverage instead of randomly dropping most districts.
    frame = pd.concat(
        [group.sample(n=min(4, len(group)), random_state=42)
         for _, group in frame.groupby(["state", "district", "crop"], sort=True)],
        ignore_index=True,
    )
    x = frame[FEATURES_CATEGORICAL + FEATURES_NUMERIC]
    y = frame["yield"].astype(float)
    rf = _pipeline(RandomForestRegressor(n_estimators=60, min_samples_leaf=2, random_state=42, n_jobs=2), ColumnTransformer, OneHotEncoder, Pipeline)
    xgb = _pipeline(XGBRegressor(n_estimators=60, max_depth=4, learning_rate=0.05,
                                subsample=0.85, colsample_bytree=0.85,
                                objective="reg:squarederror", random_state=42,
                                n_jobs=2, tree_method="hist"), ColumnTransformer, OneHotEncoder, Pipeline)
    rf.fit(x, y)
    xgb.fit(x, y)
    return {"Random Forest": rf, "XGBoost": xgb,
            "first_year": int(frame["year"].min()), "last_year": int(frame["year"].max()),
            "rows": int(len(frame)), "districts": district_coverage}


@lru_cache(maxsize=1)
def _catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _match_district(state: str | None, district: str | None, rows: list[dict]) -> tuple[str, str, str]:
    if not state:
        return "__NATIONAL_LEVEL__", "__NATIONAL_LEVEL__", "national"
    states = sorted({str(row["state"]) for row in rows})
    state_norm = normalize(state)
    state_norm = {"odisha": "orissa"}.get(state_norm, state_norm)
    state_match = next((item for item in states if normalize(item) == state_norm), None)
    if state_match is None:
        ranked_states = sorted(((SequenceMatcher(None, state_norm, normalize(item)).ratio(), item) for item in states), reverse=True)
        if not ranked_states or ranked_states[0][0] < 0.82 or (len(ranked_states) > 1 and ranked_states[0][0] - ranked_states[1][0] < 0.04):
            # Locations outside the historical dataset still receive a
            # transparent national crop/year estimate instead of a hard error.
            return "__NATIONAL_LEVEL__", "__NATIONAL_LEVEL__", "national"
        state_match = ranked_states[0][1]
    if not district:
        return state_match, "__STATE_LEVEL__", "state"
    districts = sorted({str(row["district"]) for row in rows if row["state"] == state_match})
    district_norm = normalize(district)
    district_match = next((item for item in districts if normalize(item) == district_norm), None)
    if district_match is None:
        ranked_districts = sorted(((SequenceMatcher(None, district_norm, normalize(item)).ratio(), item) for item in districts), reverse=True)
        if ranked_districts and ranked_districts[0][0] >= 0.82 and (len(ranked_districts) == 1 or ranked_districts[0][0] - ranked_districts[1][0] >= 0.04):
            district_match = ranked_districts[0][1]
        else:
            # DLD predates recent district splits. Use state/crop/year signals
            # instead of failing or silently borrowing another district's data.
            return state_match, "__STATE_LEVEL__", "state"
    return state_match, district_match, "district"


def _dld_crop(crop_id: str, month: int) -> str | None:
    names = {
        "wheat": "WHEAT", "gram": "CHICKPEA", "mustard": "RAPESEED AND MUSTARD",
        "maize": "MAIZE", "bajra": "PEARL MILLET", "groundnut": "GROUNDNUT",
        "soybean": "SOYABEAN", "sunflower": "SUNFLOWER",
    }
    if crop_id == "jowar":
        if month in {9, 10, 11, 12, 1}:
            return "RABI SORGHUM"
        return "KHARIF SORGHUM"
    return names.get(crop_id)


def compare_yield_models(plan_result: dict) -> dict:
    try:
        import pandas as pd
    except ImportError:
        raise DataUnavailable("Install the optional crop-benchmark backend dependencies to enable the ML engine.") from None
    candidates = plan_result.get("top_crops", [])
    if not candidates:
        trained = _trained_models()
        return {"status": "no_candidates", "models": [], "district_coverage": trained["districts"],
                "message": "No crops passed the suitability checks for this location and sowing date."}
    trained = _trained_models()
    request = plan_result["request"]
    state, district, match_level = _match_district(request.get("state"), request.get("district"), trained["districts"])
    month = int(str(request["sowing_date"])[5:7])
    target_year = int(str(request["sowing_date"])[:4])
    area_ha = float(request["area_ha"])
    catalogue = {crop["id"]: crop for crop in _catalog()["crops"]}
    output = []
    for model_name in ["Random Forest", "XGBoost"]:
        items = []
        for candidate in candidates:
            dld_crop = _dld_crop(candidate["id"], month)
            if dld_crop is None:
                continue
            row = pd.DataFrame([{"state": state, "district": district, "crop": dld_crop, "year": target_year}])
            predicted_yield = max(0.0, float(trained[model_name].predict(row)[0]))
            crop = catalogue[candidate["id"]]
            price = float(crop["price_inr_quintal"])
            cost = float(crop["cost_inr_quintal"])
            surplus_ha = predicted_yield / 100 * (price - cost)
            items.append({"id": candidate["id"], "name": candidate["name"],
                          "predicted_yield_kg_ha": round(predicted_yield, 1),
                          "predicted_surplus_inr_ha": round(surplus_ha),
                          "predicted_surplus_for_area": round(surplus_ha * area_ha),
                          "benchmark_price_inr_quintal": round(price),
                          "benchmark_cost_inr_quintal": round(cost)})
        items.sort(key=lambda item: (-item["predicted_surplus_inr_ha"], item["name"]))
        for index, item in enumerate(items, start=1):
            item["rank"] = index
        output.append({"name": model_name, "crops": items[:3]})
    return {"status": "available", "location_match": {"state": state, "district": request.get("district") if match_level == "state" else district,
                                                           "requested_state": request.get("state"), "requested_district": request.get("district"),
                                                           "match_level": match_level},
            "dataset": {"name": "ICRISAT–TCI District-Level Database", "source_url": SOURCE_URL,
                        "first_year": trained["first_year"], "last_year": trained["last_year"],
                        "training_rows": trained["rows"]},
            "target_year": target_year, "models": output,
            "district_coverage": trained["districts"],
            "limitations": [
                "This experimental model predicts district-level historical yield patterns from crop, district, state and year only. Soil nutrients and weather are not model features.",
                "The dataset ends in 2017. A requested future year is outside the observed training period; tree models cannot reliably extrapolate long-term climate, technology or market change.",
            "If a district is not covered or cannot be matched confidently, estimates fall back to state/crop/year patterns; if the state is also outside the historical data, estimates fall back to crop/year patterns. These fallbacks are not district-specific.",
                "The simple planner's location, mapped soil, sowing window and water screen determines which crops enter the ML comparison; ML ranks only those screened candidates.",
                "Surplus uses the planner's national price and cost benchmarks. It is not a farm-specific profit prediction or a guaranteed crop recommendation.",
                "District boundary changes and historical district-name matching can affect local relevance; verify the mapped district before interpreting results.",
            ]}
