"""Offline classification experiment. Never estimates laboratory nutrients.

Requires a licensed, reviewed tabular dataset and meaningful geographic groups.
No dataset/model is bundled and this script does not enable production inference.
"""
import argparse
import csv
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_validate
from sklearn.pipeline import Pipeline


def read_dataset(path, features, target, group):
    if len(set(features)) != len(features) or target in features or group in features or target == group:
        raise ValueError("Features, target and geographic group must be distinct.")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not set(features + [target, group]).issubset(rows[0]):
        raise ValueError("CSV is empty or required columns are missing.")
    x, y, groups = [], [], []
    fingerprints = {}
    for row in rows:
        if not row[target].strip() or not row[group].strip():
            raise ValueError("Every sample needs a target and geographic group.")
        values = [float(row[name]) if row[name].strip() else np.nan for name in features]
        if np.isinf(values).any() or np.isnan(values).mean() > 0.25:
            raise ValueError("Invalid features or more than 25% missing values in a sample.")
        fingerprint = tuple(None if np.isnan(v) else v for v in values)
        if fingerprint in fingerprints:
            raise ValueError("Duplicate feature rows detected; review repeated or near-location samples before training.")
        fingerprints[fingerprint] = row[group]
        x.append(values); y.append(row[target]); groups.append(row[group])
    if len(set(groups)) < 6 or len(set(y)) < 2:
        raise ValueError("Need at least six geographic groups and two target classes.")
    return np.asarray(x), np.asarray(y), np.asarray(groups)


def train(args):
    features = args.features.split(",")
    x, y, groups = read_dataset(args.dataset, features, args.target, args.group)
    development, test = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=args.seed).split(x, y, groups))
    if set(y[development]) != set(y[test]):
        raise ValueError("The geographic holdout does not cover all classes. Collect more representative data; do not tune the split against test scores.")
    if np.isnan(x[development]).all(axis=0).any():
        raise ValueError("A feature is entirely absent from development data.")
    folds = list(GroupKFold(n_splits=min(5, len(set(groups[development])))).split(x[development], y[development], groups[development]))
    for train_index, validation_index in folds:
        if set(y[development][train_index]) != set(y[development][validation_index]):
            raise ValueError("A validation fold lacks classes. Improve geographic coverage before comparison.")
    candidates = {
        "random_forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=3, class_weight="balanced", random_state=args.seed, n_jobs=-1),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=150, l2_regularization=1, random_state=args.seed),
    }
    comparisons = {}
    pipelines = {}
    for name, estimator in candidates.items():
        pipeline = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)), ("model", estimator)])
        metrics = cross_validate(pipeline, x[development], y[development], cv=folds,
                                 scoring={"accuracy": "accuracy", "precision": "precision_macro", "recall": "recall_macro", "f1": "f1_macro"}, error_score="raise")
        comparisons[name] = {key[5:]: {"mean": float(value.mean()), "std": float(value.std())} for key, value in metrics.items() if key.startswith("test_")}
        pipelines[name] = pipeline
    selected = max(comparisons, key=lambda name: comparisons[name]["f1"]["mean"])
    model = pipelines[selected].fit(x[development], y[development])
    prediction = model.predict(x[test])
    labels = sorted(set(y))
    metadata = {
        "model_version": args.version, "dataset_source": args.source,
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(), "seed": args.seed,
        "task": "classification", "target": args.target, "features": features, "geographic_group_column": args.group,
        "missing_strategy": "Reject rows above 25% missing; fit median imputation inside each development fold.",
        "validation": "GroupKFold on development groups; model selected by mean macro-F1; single disjoint geographic test holdout.",
        "sample_counts": {"development": len(development), "test": len(test)},
        "group_counts": {"development": len(set(groups[development])), "test": len(set(groups[test]))},
        "comparison": comparisons, "selected_model": selected,
        "test": {"accuracy": float(accuracy_score(y[test], prediction)), "classification_report": classification_report(y[test], prediction, labels=labels, output_dict=True, zero_division=0), "confusion_matrix": confusion_matrix(y[test], prediction, labels=labels).tolist(), "labels": labels},
        "runtime": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "numpy": np.__version__},
        "limitations": ["Not a laboratory soil test or fertilizer dosage model.", "Geographic grouping must separate nearby/repeated sites; district labels alone may not be sufficient.", "Requires agronomist review, temporal holdout and field validation before deployment."],
    }
    args.output.mkdir(parents=True, exist_ok=False)
    joblib.dump(model, args.output / "pipeline.joblib")
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"selected_model": selected, "output": str(args.output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--source", required=True, help="Dataset citation and licence")
    parser.add_argument("--features", required=True, help="Comma-separated numerical features with documented units")
    parser.add_argument("--target", required=True)
    parser.add_argument("--group", required=True, help="Geographically separated region identifier")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260926)
    train(parser.parse_args())
