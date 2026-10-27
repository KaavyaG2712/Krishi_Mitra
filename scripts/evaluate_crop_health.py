"""Evaluate the released MobileNetV2 crop-health model on its fixed test split.

By default the script searches the project's standard PlantVillage folders. If
images are missing, it exports the saved training report with an explicit
saved_metrics_only status. Pass --dataset-root to point at the restored dataset.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "models/checkpoints/mobilenetv2-10class-v1/best_model.pt"
SAVED_METRICS = ROOT / "models/checkpoints/mobilenetv2-10class-v1/metrics.json"
DEFAULT_MANIFEST = ROOT / "data/splits/plantvillage_10class.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_saved_metrics(output: Path, reason: str) -> dict:
    if not SAVED_METRICS.exists():
        raise SystemExit(f"Cannot evaluate: saved metric file not found: {SAVED_METRICS}")
    saved = json.loads(SAVED_METRICS.read_text(encoding="utf-8"))
    test = saved["test"]
    report = {
        "status": "saved_metrics_only",
        "reason": reason,
        "model": "MobileNetV2",
        "dataset": "PlantVillage 10-class test split (from existing training report)",
        "samples": int(test["classification_report"]["macro avg"]["support"]),
        "accuracy": test["accuracy"], "macro_precision": test["macro_precision"],
        "macro_recall": test["macro_recall"], "macro_f1": test["macro_f1"],
        "latency_p50_ms": test["cpu_or_device_latency_ms"]["p50"],
        "latency_p95_ms": test["cpu_or_device_latency_ms"]["p95"],
        "per_class": test["per_class"],
        "metrics_source": str(SAVED_METRICS.relative_to(ROOT)),
        "recomputed_in_this_run": False,
    }
    write_report(output, report)
    return report


def write_report(output: Path, report: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "module1_mobilenet_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fields = ["status", "model", "dataset", "samples", "accuracy", "macro_precision", "macro_recall",
              "macro_f1", "latency_p50_ms", "latency_p95_ms", "recomputed_in_this_run"]
    with (output / "module1_mobilenet_matrix.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(report)
    if report.get("per_class"):
        with (output / "per_class_metrics.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["class", "precision", "recall", "f1", "support"])
            writer.writeheader()
            for label, values in report["per_class"].items():
                writer.writerow({"class": label, **values})
    summary = [
        "# Module 1 — MobileNetV2 evaluation", "",
        f"**Status:** {report.get('status')}  ",
        f"**Dataset:** {report.get('dataset')}  ",
        f"**Samples:** {report.get('samples', '—')}  ",
        f"**Recomputed in this run:** {'Yes' if report.get('recomputed_in_this_run') else 'No'}", "",
        "## Overall metrics", "",
        "| Accuracy | Macro precision | Macro recall | Macro F1 | P50 latency (ms) | P95 latency (ms) |",
        "|---:|---:|---:|---:|---:|---:|",
        "| " + " | ".join(f"{report.get(key, float('nan')):.4f}" if report.get(key) is not None else "—"
                         for key in ("accuracy", "macro_precision", "macro_recall", "macro_f1"))
        + " | " + " | ".join(f"{report.get(key, float('nan')):.2f}" if report.get(key) is not None else "—"
                               for key in ("latency_p50_ms", "latency_p95_ms")) + " |",
    ]
    if report.get("per_class"):
        summary += ["", "## Per-class metrics", "",
                    "| Class | Precision | Recall | F1 | Support |", "|---|---:|---:|---:|---:|"]
        for label, values in report["per_class"].items():
            summary.append(f"| {label} | {values['precision']:.4f} | {values['recall']:.4f} | {values['f1']:.4f} | {values['support']} |")
    if report.get("confusion_matrix"):
        labels = report["labels"]
        summary += ["", "## Confusion matrix", "", "Rows are actual classes; columns are predicted classes.", "",
                    "| Actual \\ Predicted | " + " | ".join(labels) + " |",
                    "|---|" + "---:|" * len(labels)]
        for label, values in zip(labels, report["confusion_matrix"]):
            summary.append(f"| {label} | " + " | ".join(map(str, values)) + " |")
        with (output / "confusion_matrix.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["actual\\predicted", *labels])
            writer.writerows([[label, *values] for label, values in zip(labels, report["confusion_matrix"])])
    if report.get("reason"):
        summary += ["", f"**Why this is not a fresh evaluation:** {report['reason']}"]
    if report.get("evaluation_notes"):
        summary += ["", "## Notes", ""] + [f"- {note}" for note in report["evaluation_notes"]]
    (output / "module1_mobilenet_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


def run_image_evaluation(dataset_root: Path, manifest: Path, output: Path, batch_size: int, workers: int, force_cpu: bool) -> dict:
    if not CHECKPOINT.exists():
        raise SystemExit(f"Model checkpoint not found: {CHECKPOINT}")
    if not manifest.exists():
        return export_saved_metrics(output, f"test split manifest is missing: {manifest}")

    import numpy as np
    import torch
    from PIL import Image
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_recall_fscore_support
    from torch import nn
    from torch.utils.data import DataLoader
    from torchvision.models import mobilenet_v2
    from torchvision.transforms import v2

    train_script_path = ROOT / "backend/scripts/train_crop_health.py"
    spec = importlib.util.spec_from_file_location("crop_health_training_utils", train_script_path)
    training = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(training)
    split_records = training.read_records(manifest)
    records = split_records["test"]
    missing_files = [str(dataset_root / row["relative_path"]) for row in records
                     if not (dataset_root / row["relative_path"]).is_file()]
    if missing_files:
        return export_saved_metrics(output,
            f"{len(missing_files)} test image files are missing under {dataset_root}; first missing path: {missing_files[0]}")

    saved = json.loads(SAVED_METRICS.read_text(encoding="utf-8"))
    labels = saved["labels"]
    classes = len(labels)
    device = torch.device("cuda" if torch.cuda.is_available() and not force_cpu else "cpu")
    mean, std = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
    transform = v2.Compose([v2.Resize(256), v2.CenterCrop(224), v2.ToImage(),
                             v2.ToDtype(torch.float32, scale=True), v2.Normalize(mean, std)])
    loader = DataLoader(training.ManifestDataset(dataset_root, records, transform), batch_size=batch_size,
                        shuffle=False, num_workers=workers, pin_memory=device.type == "cuda")
    model = mobilenet_v2(weights=None)
    model.classifier[1] = nn.Linear(model.last_channel, classes)
    model.load_state_dict(torch.load(CHECKPOINT, map_location=device, weights_only=True))
    model.to(device).eval()
    targets, predictions, per_image_latency = [], [], []
    with torch.inference_mode():
        for images, batch_targets in loader:
            started = time.perf_counter()
            logits = model(images.to(device))
            duration_per_image = (time.perf_counter() - started) * 1000 / len(images)
            per_image_latency.extend([duration_per_image] * len(images))
            targets.extend(batch_targets.tolist())
            predictions.extend(logits.argmax(dim=1).cpu().tolist())
    precision, recall, f1, support = precision_recall_fscore_support(
        targets, predictions, labels=list(range(classes)), zero_division=0)
    report = {
        "status": "recomputed",
        "model": "MobileNetV2",
        "dataset": "PlantVillage 10-class fixed test split",
        "samples": len(targets),
        "labels": labels,
        "accuracy": float(accuracy_score(targets, predictions)),
        "macro_precision": float(precision.mean()), "macro_recall": float(recall.mean()),
        "macro_f1": float(f1.mean()),
        "latency_p50_ms": float(np.percentile(per_image_latency, 50)),
        "latency_p95_ms": float(np.percentile(per_image_latency, 95)),
        "device": str(device),
        "per_class": {label: {"precision": float(precision[i]), "recall": float(recall[i]),
                              "f1": float(f1[i]), "support": int(support[i])}
                      for i, label in enumerate(labels)},
        "confusion_matrix": confusion_matrix(targets, predictions, labels=list(range(classes))).tolist(),
        "classification_report": classification_report(targets, predictions, target_names=labels,
                                                        zero_division=0, output_dict=True),
        "split_manifest_sha256": sha256(manifest), "checkpoint_sha256": sha256(CHECKPOINT),
        "test_split": "test",
        "recomputed_in_this_run": True,
        "evaluation_notes": ["Closed-set classification only; the application's confidence rejection and crop-mismatch rules are not included.",
                             "Latency is model forward-pass time per image and excludes image decoding and HTTP overhead."],
    }
    write_report(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=None,
                        help="Root containing the relative paths listed in the split manifest.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    root = args.dataset_root or next((p for p in [ROOT / "data/processed/plantvillage_10class", ROOT / "data/raw/plantvillage"]
                                      if p.exists()), ROOT / "data/processed/plantvillage_10class")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output_dir or ROOT / "evaluation_reports" / f"module1-mobilenet-{stamp}").resolve()
    result = run_image_evaluation(root.resolve(), args.manifest.resolve(), output,
                                  args.batch_size, args.workers, args.cpu)
    values = [["Status", result.get("status")], ["Samples", result.get("samples", "—")],
              ["Accuracy", f"{result['accuracy']:.4f}"], ["Macro precision", f"{result['macro_precision']:.4f}"],
              ["Macro recall", f"{result['macro_recall']:.4f}"], ["Macro F1", f"{result['macro_f1']:.4f}"],
              ["P50 latency (ms)", f"{result['latency_p50_ms']:.2f}"],
              ["P95 latency (ms)", f"{result['latency_p95_ms']:.2f}"],
              ["Freshly recomputed", "Yes" if result.get("recomputed_in_this_run") else "No"]]
    width = max(len(str(row[0])) for row in values)
    print(f"MobileNetV2 evaluation output: {output}")
    print("+" + "-" * (width + 2) + "+" + "-" * 20 + "+")
    print(f"| {'Metric'.ljust(width)} | {'Result'.ljust(18)} |")
    print("+" + "-" * (width + 2) + "+" + "-" * 20 + "+")
    for label, value in values:
        print(f"| {str(label).ljust(width)} | {str(value).ljust(18)} |")
    print("+" + "-" * (width + 2) + "+" + "-" * 20 + "+")
    if result.get("reason"):
        print(f"Note: {result['reason']}")


if __name__ == "__main__":
    main()
