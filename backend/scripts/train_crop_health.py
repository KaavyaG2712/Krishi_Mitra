"""Fine-tune MobileNetV2 for the KrishiMitra 10-class Review 3 model."""

from __future__ import annotations

import argparse
import csv
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, precision_recall_fscore_support
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models import MobileNet_V2_Weights, mobilenet_v2
from torchvision.transforms import v2


class ManifestDataset(Dataset[tuple[torch.Tensor, int]]):
    def __init__(self, dataset_root: Path, records: list[dict[str, str]], transform: v2.Compose):
        self.dataset_root = dataset_root
        self.records = records
        self.transform = transform

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        record = self.records[index]
        with Image.open(self.dataset_root / record["relative_path"]) as image:
            return self.transform(image.convert("RGB")), int(record["class_index"])


def read_records(manifest: Path) -> dict[str, list[dict[str, str]]]:
    splits: dict[str, list[dict[str, str]]] = defaultdict(list)
    with manifest.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            splits[row["split"]].append(row)
    if set(splits) != {"train", "validation", "test"}:
        raise ValueError(f"Expected train, validation and test splits; found {sorted(splits)}")
    return splits


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device, labels: list[str]) -> dict[str, object]:
    model.eval()
    targets: list[int] = []
    predictions: list[int] = []
    latencies_ms: list[float] = []
    with torch.inference_mode():
        for images, batch_targets in loader:
            started = time.perf_counter()
            logits = model(images.to(device))
            latencies_ms.extend([(time.perf_counter() - started) * 1000 / len(images)] * len(images))
            targets.extend(batch_targets.tolist())
            predictions.extend(logits.argmax(dim=1).cpu().tolist())
    precision, recall, f1, support = precision_recall_fscore_support(targets, predictions, labels=list(range(len(labels))), zero_division=0)
    return {
        "accuracy": accuracy_score(targets, predictions),
        "macro_precision": float(precision.mean()),
        "macro_recall": float(recall.mean()),
        "macro_f1": float(f1.mean()),
        "per_class": {label: {"precision": float(precision[index]), "recall": float(recall[index]), "f1": float(f1[index]), "support": int(support[index])} for index, label in enumerate(labels)},
        "classification_report": classification_report(targets, predictions, target_names=labels, zero_division=0, output_dict=True),
        "cpu_or_device_latency_ms": {"p50": float(np.percentile(latencies_ms, 50)), "p95": float(np.percentile(latencies_ms, 95))},
    }


def train_epoch(model: nn.Module, loader: DataLoader, optimiser: torch.optim.Optimizer, device: torch.device) -> float:
    model.train()
    criterion = nn.CrossEntropyLoss()
    total_loss = 0.0
    for images, targets in loader:
        optimiser.zero_grad()
        loss = criterion(model(images.to(device)), targets.to(device))
        loss.backward()
        optimiser.step()
        total_loss += float(loss.item()) * len(images)
    return total_loss / len(loader.dataset)


def main(arguments: argparse.Namespace) -> None:
    random.seed(arguments.seed)
    np.random.seed(arguments.seed)
    torch.manual_seed(arguments.seed)
    device = torch.device("cuda" if torch.cuda.is_available() and not arguments.cpu else "cpu")
    labels = [label for label, _ in sorted(json.loads((arguments.dataset_root / "class_to_index.json").read_text()).items(), key=lambda item: item[1])]
    splits = read_records(arguments.manifest)
    normalise = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
    train_transform = v2.Compose([v2.Resize(256), v2.RandomResizedCrop(224, scale=(0.85, 1.0)), v2.RandomHorizontalFlip(), v2.RandomRotation(12), v2.ColorJitter(brightness=0.15, contrast=0.15), v2.ToImage(), v2.ToDtype(torch.float32, scale=True), v2.Normalize(*normalise)])
    evaluation_transform = v2.Compose([v2.Resize(256), v2.CenterCrop(224), v2.ToImage(), v2.ToDtype(torch.float32, scale=True), v2.Normalize(*normalise)])
    loaders = {name: DataLoader(ManifestDataset(arguments.dataset_root, records, train_transform if name == "train" else evaluation_transform), batch_size=arguments.batch_size, shuffle=name == "train", num_workers=arguments.workers, pin_memory=device.type == "cuda") for name, records in splits.items()}
    model = mobilenet_v2(weights=MobileNet_V2_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.last_channel, len(labels))
    model.to(device)
    for parameter in model.features.parameters(): parameter.requires_grad = False
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    best_f1 = -1.0
    history: list[dict[str, object]] = []
    for stage, epochs in (("head", arguments.head_epochs), ("fine_tune", arguments.fine_tune_epochs)):
        if stage == "fine_tune":
            for parameter in model.features[-4:].parameters(): parameter.requires_grad = True
        optimiser = torch.optim.AdamW((parameter for parameter in model.parameters() if parameter.requires_grad), lr=arguments.learning_rate if stage == "head" else arguments.learning_rate / 10, weight_decay=arguments.weight_decay)
        for epoch in range(epochs):
            loss = train_epoch(model, loaders["train"], optimiser, device)
            validation = evaluate(model, loaders["validation"], device, labels)
            history.append({"stage": stage, "epoch": epoch + 1, "train_loss": loss, "validation": validation})
            if validation["macro_f1"] > best_f1:
                best_f1 = float(validation["macro_f1"])
                torch.save(model.state_dict(), arguments.output_dir / "best_model.pt")
    model.load_state_dict(torch.load(arguments.output_dir / "best_model.pt", map_location=device, weights_only=True))
    metrics = {"model": "mobilenet_v2", "labels": labels, "device": str(device), "best_validation_macro_f1": best_f1, "test": evaluate(model, loaders["test"], device, labels), "history": history}
    (arguments.output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (arguments.output_dir / "preprocessing.json").write_text(json.dumps({"input_size": [224, 224], "normalization_mean": normalise[0], "normalization_std": normalise[1], "training_augmentation": "horizontal flip, rotation, colour jitter, random resized crop"}, indent=2) + "\n", encoding="utf-8")
    print(f"Saved model and metrics to {arguments.output_dir}; best validation macro-F1: {best_f1:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train KrishiMitra crop-health MobileNetV2.")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--head-epochs", type=int, default=3)
    parser.add_argument("--fine-tune-epochs", type=int, default=7)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--weight-decay", type=float, default=0.0001)
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--cpu", action="store_true")
    main(parser.parse_args())
