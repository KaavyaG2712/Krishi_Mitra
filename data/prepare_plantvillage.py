"""Create the exact 10-class Review 3 PlantVillage subset without altering raw data.

Expected raw source: the Kaggle PlantVillage dataset downloaded under data/raw/plantvillage.
Only RGB/colour source folders should be included when a dataset distribution contains
multiple representations of the same leaf image.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


LABELS: dict[str, str] = {
    "Tomato___healthy": "tomato_healthy",
    "Tomato___Early_blight": "tomato_early_blight",
    "Tomato___Late_blight": "tomato_late_blight",
    "Potato___healthy": "potato_healthy",
    "Potato___Early_blight": "potato_early_blight",
    "Potato___Late_blight": "potato_late_blight",
    "Corn_(maize)___healthy": "maize_healthy",
    "Corn_(maize)___Common_rust_": "maize_common_rust",
    "Grape___healthy": "grape_healthy",
    "Grape___Black_rot": "grape_black_rot",
}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def locate_label_dir(source: Path, original_name: str) -> Path:
    candidates = [path for path in source.rglob(original_name) if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"Could not find source class folder: {original_name}")
    colour_candidates = [path for path in candidates if "color" in {part.lower() for part in path.parts}]
    return sorted(colour_candidates or candidates, key=lambda path: (len(path.parts), str(path)))[0]


def build_subset(source: Path, output: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Source directory does not exist: {source}")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "source_manifest.csv"
    class_to_index = {label: index for index, label in enumerate(LABELS.values())}

    with manifest_path.open("w", newline="", encoding="utf-8") as manifest:
        writer = csv.DictWriter(manifest, fieldnames=["label", "source_path", "output_path", "sha256"])
        writer.writeheader()
        for source_class, label in LABELS.items():
            class_dir = locate_label_dir(source, source_class)
            target_dir = output / label
            target_dir.mkdir(exist_ok=True)
            images = sorted(path for path in class_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
            if not images:
                raise ValueError(f"No supported images found in {class_dir}")
            for index, image in enumerate(images):
                target = target_dir / f"{index:06d}{image.suffix.lower()}"
                if not target.exists():
                    shutil.copy2(image, target)
                writer.writerow({
                    "label": label,
                    "source_path": str(image.relative_to(source)),
                    "output_path": str(target.relative_to(output)),
                    "sha256": sha256(image),
                })

    (output / "class_to_index.json").write_text(json.dumps(class_to_index, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(LABELS)} classes at {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare the KrishiMitra PlantVillage 10-class subset.")
    parser.add_argument("--source", type=Path, required=True, help="Raw Kaggle PlantVillage dataset directory")
    parser.add_argument("--output", type=Path, required=True, help="Ignored local output directory")
    arguments = parser.parse_args()
    build_subset(arguments.source, arguments.output)
