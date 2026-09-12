# Local project data

This folder is deliberately not a source of truth for raw data in Git.

- `raw/` — downloaded PlantVillage source images; ignored by Git.
- `external_test/` — consented field images used only for external evaluation; ignored by Git.
- `processed/` — generated split manifests and derived files; ignored by Git.

Keep source metadata, checksums, and evaluation-question registers under `docs/`, where they can be reviewed and versioned without exposing images or private information.

## PlantVillage dataset preparation

Download the Kaggle dataset into `data/raw/plantvillage/`; it is intentionally ignored by Git. Then run the preparation script from the repository root:

```powershell
py -3.12 data/prepare_plantvillage.py --source data/raw/plantvillage --output data/processed/plantvillage_10class
```

The script selects only the Review 3 classes, copies images into stable label folders, and writes `class_to_index.json` and a source manifest. It does not mix any consented field images into the training data.
