"""Compare yield regression models on a latest-years holdout."""
from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

REQUIRED = {"state", "district", "year", "crop", "yield"}
PROJECT_CROPS = {"wheat", "chickpea", "maize", "groundnut", "soybean", "soyabean",
                 "sunflower", "pearl millet", "rapeseed and mustard",
                 "kharif sorghum", "rabi sorghum"}


def make_pipeline(model, categorical: list[str], numeric: list[str]) -> Pipeline:
    prep = ColumnTransformer([
        ("categorical", Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                                  ("encode", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ("numeric", SimpleImputer(strategy="median", add_indicator=True), numeric),
    ])
    return Pipeline([("preprocess", prep), ("model", model)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Normalized CSV: state,district,year,crop,yield")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--holdout-years", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    frame = pd.read_csv(args.input)
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise SystemExit(f"Missing required columns: {', '.join(sorted(missing))}")
    frame = frame[list(REQUIRED)].copy()
    frame["crop"] = frame["crop"].astype(str).str.strip()
    frame = frame[frame["crop"].str.casefold().isin(PROJECT_CROPS)]
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    frame["yield"] = pd.to_numeric(frame["yield"], errors="coerce")
    frame = frame.dropna(subset=["year", "yield", "crop", "state", "district"])
    # The portal table is a complete district/year grid; zero indicates no
    # reported crop yield for that cell, so it is not a harvest observation.
    frame = frame[np.isfinite(frame["yield"]) & (frame["yield"] > 0)]
    frame["year"] = frame["year"].astype(int)
    years = sorted(frame["year"].unique())
    if len(years) <= args.holdout_years or frame["district"].nunique() < 2:
        raise SystemExit("Need more years than the holdout and at least two districts.")
    test_years = years[-args.holdout_years:]
    train = frame[~frame.year.isin(test_years)]
    test = frame[frame.year.isin(test_years)]
    district_overlap = set(train.district.astype(str)) & set(test.district.astype(str))
    # Geography and year are encoded as categoricals; no post-harvest production
    # or target-derived feature is included.
    features = ["state", "district", "year", "crop"]
    x_train, x_test = train[features], test[features]
    y_train, y_test = train["yield"], test["yield"]
    categorical = features
    numeric: list[str] = []
    models = {
        "mean_baseline": DummyRegressor(strategy="mean"),
        "random_forest": RandomForestRegressor(n_estimators=120, min_samples_leaf=2,
                                               random_state=args.seed, n_jobs=-1),
        "xgboost": XGBRegressor(n_estimators=120, max_depth=4, learning_rate=0.05,
                                subsample=0.85, colsample_bytree=0.85,
                                objective="reg:squarederror", random_state=args.seed,
                                n_jobs=-1, tree_method="hist"),
    }
    rows = []
    for name, model in models.items():
        pipeline = make_pipeline(model, categorical, numeric)
        pipeline.fit(x_train, y_train)
        pred = pipeline.predict(x_test)
        rows.append({"model": name, "mae": mean_absolute_error(y_test, pred),
                     "rmse": float(np.sqrt(mean_squared_error(y_test, pred))),
                     "r2": r2_score(y_test, pred), "test_rows": len(test)})
    args.output.mkdir(parents=True, exist_ok=False)
    pd.DataFrame(rows).to_csv(args.output / "metrics.csv", index=False)
    metadata = {
        "task": "district crop yield regression",
        "target": "yield (kg/ha, as labelled by ICRISAT DLD API)",
        "features": features,
        "crop_filter": "Module 2 catalogue crops; DLD provides Kharif and Rabi sorghum separately and the evaluation keeps those labels distinct.",
        "excluded": ["production (target leakage)", "area (not needed for yield target)",
                     "zero-yield cells (treated as no reported crop observation)",
                     "soil nutrients (not joined; no verified matching records yet)"],
        "validation": "chronological holdout of latest years; same observations for all models; not a held-out-district test",
        "train_years": [int(train.year.min()), int(train.year.max())],
        "test_years": [int(y) for y in test_years],
        "train_rows": len(train), "test_rows": len(test),
        "districts_train": int(train.district.nunique()), "districts_test": int(test.district.nunique()),
        "districts_in_both_train_and_test": len(district_overlap),
        "dataset_sha256": __import__("hashlib").sha256(args.input.read_bytes()).hexdigest(),
        "models": rows,
        "runtime": {"python": platform.python_version(), "pandas": pd.__version__,
                    "scikit_learn": sklearn.__version__, "xgboost": xgboost.__version__},
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "limitations": ["Historical yield prediction is not crop recommendation or profit prediction.",
                        "District and crop identity may let models learn historical averages; this does not prove new-district generalization.",
                        "No soil nutrient or weather merge is included; features are crop, district, state and year only.",
                        "This is an apportioned DLD table; verify the source's apportionment methodology before interpreting as observed district measurements.",
                        "Hyperparameters are fixed for this initial comparison and were not tuned.",
                        "Published studies are comparable only when target, data, split, features and metric match."],
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "metrics": rows}, indent=2))


if __name__ == "__main__":
    main()
