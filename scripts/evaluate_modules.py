"""Run reproducible offline evaluations for KrishiMitra's ML/retrieval modules.

Run from the repository root with backend/.venv's Python. The script never
trains on the disease holdout and never writes to the application database.
Module 2 Random Forest and XGBoost share one temporal holdout.
"""
from __future__ import annotations

import argparse
import csv
import csv
import importlib.util
import json
import math
import statistics
import sys
import time
import textwrap
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_disease() -> dict:
    metrics_path = ROOT / "models/checkpoints/mobilenetv2-10class-v1/metrics.json"
    split_path = ROOT / "data/splits/plantvillage_10class.csv"
    image_roots = [ROOT / "data/raw/plantvillage", ROOT / "data/processed/plantvillage_10class"]
    result = {"module": "Crop health (Module 1)", "engine": "MobileNetV2", "status": "unavailable_for_rerun"}
    if metrics_path.exists():
        saved = load_json(metrics_path)
        test = saved.get("test", {})
        result.update({
            "recorded_metrics": {key: test.get(key) for key in
                                  ("accuracy", "macro_precision", "macro_recall", "macro_f1")},
            "recorded_test_samples": round(test.get("classification_report", {}).get("macro avg", {}).get("support", 0)),
            "recorded_latency_ms": test.get("cpu_or_device_latency_ms"),
            "metrics_source": str(metrics_path.relative_to(ROOT)),
        })
    available = any(path.exists() and any(path.rglob("*.jpg")) for path in image_roots)
    result["test_images_available"] = available
    result["split_manifest_available"] = split_path.exists()
    if available:
        result["status"] = "images_present_manual_re_evaluation_not_implemented"
        result["note"] = "Saved metrics are provided; this runner does not independently re-score the image model."
    else:
        result["note"] = ("Saved holdout metrics are reported for reference only; image files are absent, "
                           "so this run could not independently recompute disease accuracy.")
    return result


def evaluate_yield(data_path: Path, output_dir: Path, holdout_years: int, seed: int) -> dict:
    evaluator_path = ROOT / "experiments/crop-yield-benchmark/evaluate.py"
    spec = importlib.util.spec_from_file_location("crop_yield_evaluator", evaluator_path)
    evaluator = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(evaluator)
    import pandas as pd
    import numpy as np
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import RandomForestRegressor
    from xgboost import XGBRegressor

    frame = pd.read_csv(data_path)
    missing = evaluator.REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"Yield dataset missing fields: {sorted(missing)}")
    frame = frame[list(evaluator.REQUIRED)].copy()
    frame["crop"] = frame["crop"].astype(str).str.strip()
    frame = frame[frame["crop"].str.casefold().isin(evaluator.PROJECT_CROPS)]
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    frame["yield"] = pd.to_numeric(frame["yield"], errors="coerce")
    frame = frame.dropna(subset=["year", "yield", "crop", "state", "district"])
    frame = frame[np.isfinite(frame["yield"]) & (frame["yield"] > 0)]
    frame["year"] = frame["year"].astype(int)
    years = sorted(frame["year"].unique())
    test_years = years[-holdout_years:]
    train, test = frame[~frame.year.isin(test_years)], frame[frame.year.isin(test_years)]
    features = ["state", "district", "year", "crop"]
    x_train, x_test = train[features], test[features]
    y_train, y_test = train["yield"], test["yield"]
    models = {
        "mean_baseline": DummyRegressor(strategy="mean"),
        "random_forest": RandomForestRegressor(n_estimators=120, min_samples_leaf=2,
                                                random_state=seed, n_jobs=-1),
        "xgboost": XGBRegressor(n_estimators=120, max_depth=4, learning_rate=0.05,
                                subsample=0.85, colsample_bytree=0.85,
                                objective="reg:squarederror", random_state=seed,
                                n_jobs=-1, tree_method="hist"),
    }
    rows = []
    for name, model in models.items():
        pipe = evaluator.make_pipeline(model, features, [])
        start = time.perf_counter()
        pipe.fit(x_train, y_train)
        fit_seconds = time.perf_counter() - start
        start = time.perf_counter()
        prediction = pipe.predict(x_test)
        predict_seconds = time.perf_counter() - start
        rows.append({"model": name,
                     "mae_kg_ha": float(mean_absolute_error(y_test, prediction)),
                     "rmse_kg_ha": float(np.sqrt(mean_squared_error(y_test, prediction))),
                     "r2": float(r2_score(y_test, prediction)),
                     "test_rows": int(len(test)), "fit_seconds": round(fit_seconds, 3),
                     "predict_seconds": round(predict_seconds, 3)})
    output_dir.mkdir(parents=True, exist_ok=False)
    pd.DataFrame(rows).to_csv(output_dir / "module2_yield_metrics.csv", index=False)
    metadata = {
        "task": "district-level crop yield regression (not farm-level profit or a direct recommendation)",
        "dataset": str(data_path.relative_to(ROOT)),
        "features": features,
        "target": "yield, kg/ha",
        "split": {"type": "latest-years chronological holdout", "train_years": [int(train.year.min()), int(train.year.max())],
                  "test_years": [int(y) for y in test_years], "train_rows": int(len(train)),
                  "test_rows": int(len(test)), "districts_in_both": len(set(train.district.astype(str)) & set(test.district.astype(str)))},
        "same_test_rows_for_all_models": True,
        "models": rows,
        "limitations": ["Predictive yield evaluation does not evaluate crop choice utility or profit.",
                        "Districts overlap train and test; this is not a new-district generalization test.",
                        "Soil nutrients and weather are not joined as matched historical features.",
                        "A crop's realized yield is not the same as its profitability or suitability.",
                        "Model hyperparameters are fixed and not tuned."]
    }
    (output_dir / "module2_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def evaluate_advisor() -> dict:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.db.database import SessionLocal
    from app.db.models import KnowledgeChunk, KnowledgeDocument
    from app.modules.advisor.service import retrieve_passages, is_sensitive_query

    # Each query has an expected title grounded in the six-entry seed library.
    cases = [
        ("tomato leaf early blight management", "Tomato field demonstrations and blight context"),
        ("potato late blight symptoms on leaves", "Potato late blight and its management"),
        ("maize rust disease management", "ICAR Kharif Agro-Advisories for Farmers 2025"),
        ("grape black rot leaf spots sanitation", "DAESI Study Material, Volume I"),
        ("wheat irrigation water management", "ICAR irrigation advisory for wheat"),
        ("soil organic carbon fertilizer management", "Soil health and nutrient management reference"),
    ]
    session = SessionLocal()
    started = time.perf_counter()
    try:
        doc_count = session.query(KnowledgeDocument).count()
        chunk_count = session.query(KnowledgeChunk).count()
        query_times, ranks, reciprocal_ranks = [], [], []
        for query, expected in cases:
            start = time.perf_counter()
            hits = retrieve_passages(session, query)
            query_times.append((time.perf_counter() - start) * 1000)
            hit_titles = [hit.title for hit in hits]
            rank = hit_titles.index(expected) + 1 if expected in hit_titles else None
            ranks.append(rank)
            reciprocal_ranks.append(1 / rank if rank else 0.0)
        sensitive_blocked = is_sensitive_query("What pesticide dose should I spray on tomato?")
        off_topic = retrieve_passages(session, "tell me a movie review")
        elapsed = time.perf_counter() - started
        found = sum(rank is not None for rank in ranks)
        return {"module": "Local agronomy advisor (Module 3)", "engine": "PostgreSQL full-text retrieval + rules",
                "status": "evaluated" if doc_count and chunk_count else "empty_knowledge_library",
                "documents": doc_count, "passages": chunk_count, "test_queries": len(cases),
                "expected_source_found_rate": found / len(cases),
                "hit_at_1": sum(rank == 1 for rank in ranks) / len(cases),
                "hit_at_3": found / len(cases), "mrr": statistics.mean(reciprocal_ranks),
                "mean_query_latency_ms": statistics.mean(query_times),
                "sensitive_query_blocked": sensitive_blocked,
                "off_topic_abstained": len(off_topic) == 0,
                "case_results": [{"question": q, "expected_source": exp, "rank": rank} for (q, exp), rank in zip(cases, ranks)],
                "note": "Small, hand-authored smoke benchmark over expected sources; not a statistically representative user-query benchmark."}
    finally:
        session.close()


def write_matrix(out: Path, report: dict) -> None:
    """Flatten comparable reported metrics into one CSV and a readable summary."""
    rows = []
    health = report.get("crop_health") or {}
    if health.get("recorded_metrics"):
        row = {"module": "Crop health (Module 1)", "engine": "MobileNetV2 (saved holdout)",
               "status": health.get("status"), "samples": health.get("recorded_test_samples"),
               "dataset_or_split": "PlantVillage 10-class saved test metrics; images absent for rerun"}
        row.update(health["recorded_metrics"])
        row["latency_p95_ms"] = (health.get("recorded_latency_ms") or {}).get("p95")
        rows.append(row)
    module2 = report.get("module2") or {}
    for model in module2.get("models", []):
        rows.append({"module": "Crop yield benchmark (Module 2 experiment)", "engine": model["model"],
                     "status": "evaluated", "samples": model.get("test_rows"),
                     "dataset_or_split": ", ".join(map(str, module2["split"]["test_years"])),
                     "mae_kg_ha": model.get("mae_kg_ha"), "rmse_kg_ha": model.get("rmse_kg_ha"),
                     "r2": model.get("r2"), "fit_seconds": model.get("fit_seconds"),
                     "predict_seconds": model.get("predict_seconds")})
    advisor = report.get("module3") or {}
    rows.append({"module": "Local agronomy advisor (Module 3)", "engine": advisor.get("engine", "PostgreSQL full-text retrieval"),
                 "status": advisor.get("status", "not_run"), "samples": advisor.get("test_queries"),
                 "dataset_or_split": "Local seeded knowledge passages",
                 "hit_at_1": advisor.get("hit_at_1"), "hit_at_3": advisor.get("hit_at_3"),
                 "mrr": advisor.get("mrr"), "mean_query_latency_ms": advisor.get("mean_query_latency_ms")})
    columns = ["module", "engine", "status", "samples", "dataset_or_split", "accuracy", "macro_precision",
               "macro_recall", "macro_f1", "mae_kg_ha", "rmse_kg_ha", "r2", "fit_seconds",
               "predict_seconds", "hit_at_1", "hit_at_3", "mrr", "latency_p95_ms", "mean_query_latency_ms"]
    with (out / "evaluation_matrix.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# KrishiMitra evaluation summary", "",
             "Metric values are task-specific; accuracy/F1, yield MAE/RMSE/R², and retrieval Hit@k are not directly comparable.", ""]
    for row in rows:
        lines.append(f"## {row['module']} — {row['engine']}")
        lines.append("")
        lines.append(f"Status: **{row['status']}**. Test size: {row.get('samples', 'not available')}.")
        details = [f"{key}={value:.4f}" if isinstance(value, float) else f"{key}={value}"
                   for key, value in row.items() if key in columns[5:] and value is not None]
        if details:
            lines.append("Metrics: " + "; ".join(details) + ".")
        lines.append("")
    if advisor.get("error"):
        lines += ["Module 3 retrieval could not be measured because the configured PostgreSQL schema is missing `knowledge_chunks.search_vector`; apply the repository's pending Alembic migration before rerunning. No migration was applied by this evaluator.", ""]
    if health.get("test_images_available") is False:
        lines += ["Crop-health accuracy/F1 are from the saved training report only; the original image files are not available to independently rerun the holdout evaluation.", ""]
    if module2.get("limitations"):
        lines += ["Module 2 caveat: " + " ".join(module2["limitations"]), ""]
    (out / "evaluation_summary.md").write_text("\n".join(lines), encoding="utf-8")


def print_evaluation_table(report: dict, report_dir: Path) -> None:
    """Print a compact, readable view of the metrics saved in the report."""
    rows = []

    def metric(label: str, value, precision: int = 3, suffix: str = "") -> str | None:
        if value is None:
            return None
        if isinstance(value, float):
            value = f"{value:.{precision}f}"
        return f"{label}: {value}{suffix}"

    health = report.get("crop_health") or {}
    health_metrics = health.get("recorded_metrics") or {}
    details = [
        metric("Accuracy", health_metrics.get("accuracy")),
        metric("Macro F1", health_metrics.get("macro_f1")),
        metric("P95 latency", (health.get("recorded_latency_ms") or {}).get("p95"), 1, " ms"),
    ]
    rows.append([
        "Crop health (Module 1)",
        health.get("engine", "MobileNetV2"),
        health.get("status", "not_run"),
        str(health.get("recorded_test_samples") or "-"),
        "; ".join(value for value in details if value) or "Saved metrics unavailable",
    ])

    module2 = report.get("module2")
    if module2:
        for model in module2.get("models", []):
            details = [
                metric("MAE", model.get("mae_kg_ha"), 1, " kg/ha"),
                metric("RMSE", model.get("rmse_kg_ha"), 1, " kg/ha"),
                metric("R2", model.get("r2")),
            ]
            rows.append([
                "Crop yield (Module 2)",
                model.get("model", "-"),
                "evaluated",
                str(model.get("test_rows") or "-"),
                "; ".join(value for value in details if value) or "-",
            ])
    else:
        rows.append(["Crop yield (Module 2)", "-", "skipped", "-", "-"])

    advisor = report.get("module3")
    if advisor:
        details = [
            metric("Hit@1", advisor.get("hit_at_1")),
            metric("Hit@3", advisor.get("hit_at_3")),
            metric("MRR", advisor.get("mrr")),
            metric("Avg latency", advisor.get("mean_query_latency_ms"), 1, " ms"),
        ]
        for label, key in (("Sensitive blocked", "sensitive_query_blocked"),
                           ("Off-topic abstained", "off_topic_abstained")):
            if advisor.get(key) is not None:
                details.append(f"{label}: {'yes' if advisor[key] else 'no'}")
        if advisor.get("error"):
            details.append(f"Error: {advisor['error']}")
        rows.append([
            "Advisor (Module 3)",
            advisor.get("engine", "PostgreSQL retrieval"),
            advisor.get("status", "not_run"),
            str(advisor.get("test_queries") or "-"),
            "; ".join(value for value in details if value) or "-",
        ])
    else:
        rows.append(["Advisor (Module 3)", "-", "skipped", "-", "-"])

    headers = ["Module", "Model / engine", "Status", "Samples", "Key metrics"]
    widths = [27, 25, 22, 9, 62]
    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def print_row(cells: list[str]) -> None:
        wrapped = [
            textwrap.wrap(str(cell).replace("\n", " "), width=width) or [""]
            for cell, width in zip(cells, widths)
        ]
        for line_index in range(max(map(len, wrapped))):
            print("| " + " | ".join(
                (cell_lines[line_index] if line_index < len(cell_lines) else "").ljust(width)
                for cell_lines, width in zip(wrapped, widths)
            ) + " |")

    print(f"Evaluation report: {report_dir}")
    print(border)
    print_row(headers)
    print(border)
    for row in rows:
        print_row(row)
    print(border)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None, help="New report directory; defaults to evaluation_reports/<UTC timestamp>")
    parser.add_argument("--yield-data", type=Path, default=ROOT / "data/raw/crop-yield-benchmark/crop_yield.csv")
    parser.add_argument("--holdout-years", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-module2", action="store_true")
    parser.add_argument("--skip-advisor", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (args.output_dir or ROOT / "evaluation_reports" / stamp).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
              "crop_health": evaluate_disease(), "module2": None, "module3": None}
    if not args.skip_module2:
        report["module2"] = evaluate_yield(args.yield_data.resolve(), out / "module2", args.holdout_years, args.seed)
    if not args.skip_advisor:
        try:
            report["module3"] = evaluate_advisor()
        except Exception as exc:
            report["module3"] = {"module": "Local agronomy advisor (Module 3)", "status": "database_unavailable",
                                 "error": f"{type(exc).__name__}: {exc}"}
    write_matrix(out, report)
    (out / "evaluation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_evaluation_table(report, out)


if __name__ == "__main__":
    main()
