# Module 1 — MobileNetV2 evaluation

**Status:** saved_metrics_only  
**Dataset:** PlantVillage 10-class test split (from existing training report)  
**Samples:** 1591  
**Recomputed in this run:** No

## Overall metrics

| Accuracy | Macro precision | Macro recall | Macro F1 | P50 latency (ms) | P95 latency (ms) |
|---:|---:|---:|---:|---:|---:|
| 0.9868 | 0.9891 | 0.9837 | 0.9863 | 40.85 | 43.52 |

## Per-class metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| tomato_healthy | 0.9917 | 1.0000 | 0.9958 | 239 |
| tomato_early_blight | 0.9858 | 0.9267 | 0.9553 | 150 |
| tomato_late_blight | 0.9724 | 0.9860 | 0.9792 | 286 |
| potato_healthy | 1.0000 | 0.9565 | 0.9778 | 23 |
| potato_early_blight | 0.9804 | 1.0000 | 0.9901 | 150 |
| potato_late_blight | 0.9669 | 0.9733 | 0.9701 | 150 |
| maize_healthy | 0.9943 | 1.0000 | 0.9971 | 174 |
| maize_common_rust | 1.0000 | 0.9944 | 0.9972 | 179 |
| grape_healthy | 1.0000 | 1.0000 | 1.0000 | 63 |
| grape_black_rot | 1.0000 | 1.0000 | 1.0000 | 177 |

**Why this is not a fresh evaluation:** 1591 test image files are missing under C:\Users\Ajay\OneDrive\Documents\KrishiMitra_Final\data\processed\plantvillage_10class; first missing path: C:\Users\Ajay\OneDrive\Documents\KrishiMitra_Final\data\processed\plantvillage_10class\tomato_healthy\000544.jpg
