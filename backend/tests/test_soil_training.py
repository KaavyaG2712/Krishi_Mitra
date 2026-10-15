import csv
from types import SimpleNamespace

import pytest

pytest.importorskip("sklearn")
from scripts.train_soil import read_dataset, train


def test_duplicate_rows_rejected_before_geographic_split(tmp_path):
    path = tmp_path / "soil.csv"
    path.write_text("ph,group,crop\n7,north,rice\n7,south,wheat\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        read_dataset(path, ["ph"], "crop", "group")


def test_reproducible_pipeline_smoke_only_not_agricultural_evidence(tmp_path):
    path = tmp_path / "synthetic.csv"
    with path.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["feature", "group", "target"])
        for group in range(10):
            for value in range(12):
                writer.writerow([group * 0.001 + value, f"region-{group}", "a" if value < 6 else "b"])
    train(SimpleNamespace(dataset=path, source="Synthetic software test; not agricultural evidence", features="feature", target="target", group="group", seed=42, version="test-only", output=tmp_path / "model"))
    assert (tmp_path / "model" / "pipeline.joblib").is_file()
    assert '"confusion_matrix"' in (tmp_path / "model" / "metadata.json").read_text()
