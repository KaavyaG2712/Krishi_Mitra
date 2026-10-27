# Experimental crop-yield model comparison

This is an offline evaluation experiment. It does not change or feed predictions
into Module 2. It compares an XGBoost regressor, Random Forest and a mean
baseline on observed historical district crop yield from ICRISAT's District
Level Database (DLD).

The Module 2 **ML yield engine** is a separate experimental comparison path. It
uses the same local CSV to fit Random Forest and XGBoost models on a fixed-seed,
balanced sample (up to 2,500 rows per crop) the first time the comparison
endpoint is called, caches them for the backend process, and ranks crops that
passed the existing simple agronomic screen. The user interface shows both
engines side by side. Install `backend[crop-benchmark]` to enable the models; if
the CSV or optional packages are unavailable, the simple engine still returns
and the ML tab reports why its result is unavailable. The offline evaluator
continues to use the full dataset for the report benchmark.

The app models use crop, district, state, and numeric requested year. They do
not use the soil map, nutrient measurements, or weather forecast as model
features. The DLD table ends in 2017, so predictions for later dates are an
experimental historical-pattern comparison rather than a validated forecast.
The simple engine's soil, weather, sowing-window, and water rules still screen
which crops are eligible. Do not interpret the ML ranking as farm-specific
profit or as agronomic advice.

## Data source and workflow

The TCI page describes the open ICRISAT DLD (district-level agriculture, with
historical crop, weather, input and economic data). The original DLD site
exposes JSON endpoints used by its own front end. Run the downloader to save
the crop area/production/yield table and its source metadata under the ignored
`data/raw/crop-yield-benchmark/` directory:

```powershell
backend\.venv\Scripts\python.exe experiments\crop-yield-benchmark\download_icrisat.py
```

This experiment starts with crop identity, district, state, year and observed
yield. The downloader retains the raw response and creates a normalized CSV
from the DLD yield columns. It does not fabricate a district nutrient value or
pretend that the application's 250 m soil map is observed data. The DLD source
may be slow or unavailable; if fetching fails, prepare a normalized CSV with
`state,district,year,crop,yield` and pass it with `--input`.

## Evaluation

Install the optional dependencies, then run:

```powershell
backend\.venv\Scripts\python.exe -m pip install -e "./backend[crop-benchmark]"
backend\.venv\Scripts\python.exe experiments\crop-yield-benchmark\evaluate.py --input data\raw\crop-yield-benchmark\crop_yield.csv --output data\processed\crop-yield-benchmark
```

Expected normalized CSV columns are `state,district,year,crop,yield`. The API
labels yield in kg/ha. Zero-yield district/crop/year cells are excluded because the source
table is a complete district grid and zero means no reported crop yield. The
evaluator holds out the latest years, fits preprocessing only on
training years, and reports MAE, RMSE and R² for the same test records for each
model. It writes a CSV metrics table and JSON run metadata.

The evaluation filters to crops in the current Module 2 catalogue where DLD
has a matching yield column. Kharif and Rabi sorghum remain separate labels.
The target is historical yield, not “best crop” or profit. Do not put production
or yield-derived values in model inputs. Random row splits and the accuracy
scores of NPK crop-classification papers are not directly comparable to these
held-out-year regression results. Report the dataset, split years, features,
units and metrics beside any paper comparison. This experiment is for a report,
not a validated farmer recommendation.

## Initial run

Using the downloaded apportioned DLD table and the latest five years as test
data (2013–2017), the initial results were:

| Model | MAE (kg/ha) | RMSE (kg/ha) | R² |
|---|---:|---:|---:|
| Mean baseline | 770.31 | 1,252.26 | -0.207 |
| Random Forest | **676.89** | **1,071.50** | **0.116** |
| XGBoost | 683.10 | 1,080.97 | 0.100 |

Random Forest narrowly beats XGBoost here. This baseline feature set contains
only crop, district, state and year; it does not include soil nutrients or
weather. All 304 districts in the test years also occur in the training years,
so this only tests later-year prediction for familiar districts. The scores are an
initial reproducible comparison, not evidence of farmer-level accuracy. The
metrics and run metadata are saved in `results/`.

See [`literature-comparison.md`](literature-comparison.md) for one closer
published India district-level reference and why the scores are not directly
comparable.
