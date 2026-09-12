"""Create reproducible stratified train/validation/test split manifests."""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


def allocate(count: int, validation_fraction: float, test_fraction: float) -> tuple[int, int, int]:
    """Allocate each class while retaining at least one image in every split."""
    if count < 3:
        raise ValueError("Each class must contain at least three images for a three-way split.")
    validation = max(1, round(count * validation_fraction))
    test = max(1, round(count * test_fraction))
    train = count - validation - test
    if train < 1:
        raise ValueError(f"Split fractions leave no training image for class size {count}.")
    return train, validation, test


def create_splits(dataset_root: Path, output: Path, seed: int, validation_fraction: float, test_fraction: float) -> None:
    label_map_path = dataset_root / "class_to_index.json"
    if not label_map_path.is_file():
        raise FileNotFoundError(f"Missing label map: {label_map_path}")
    label_to_index: dict[str, int] = json.loads(label_map_path.read_text(encoding="utf-8"))
    rng = random.Random(seed)
    rows: list[dict[str, str | int]] = []

    for label, index in sorted(label_to_index.items(), key=lambda item: item[1]):
        image_paths = sorted(path for path in (dataset_root / label).iterdir() if path.is_file())
        rng.shuffle(image_paths)
        train_count, validation_count, test_count = allocate(len(image_paths), validation_fraction, test_fraction)
        boundaries = {"train": train_count, "validation": train_count + validation_count}
        for position, path in enumerate(image_paths):
            split = "train" if position < boundaries["train"] else "validation" if position < boundaries["validation"] else "test"
            rows.append({"split": split, "label": label, "class_index": index, "relative_path": str(path.relative_to(dataset_root))})

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["split", "label", "class_index", "relative_path"])
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter((str(row["split"]), str(row["label"])) for row in rows)
    summary = {
        "seed": seed,
        "dataset_root": str(dataset_root),
        "validation_fraction": validation_fraction,
        "test_fraction": test_fraction,
        "labels": label_to_index,
        "counts": {f"{split}:{label}": count for (split, label), count in sorted(counts.items())},
    }
    output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} records to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create stratified PlantVillage split manifests.")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.15)
    arguments = parser.parse_args()
    if arguments.validation_fraction <= 0 or arguments.test_fraction <= 0 or arguments.validation_fraction + arguments.test_fraction >= 1:
        raise ValueError("Validation and test fractions must be positive and total less than 1.")
    create_splits(**vars(arguments))
