# Literature comparison notes

## Closest reference located

De Clercq and Mahdi, “Feasibility of machine learning-based rice yield
prediction in India at the district level using climate reanalysis and remote
sensing data,” *Agricultural Systems* 220 (2024), 104099.

- DOI / journal article: https://doi.org/10.1016/j.agsy.2024.104099
- Open paper: https://arxiv.org/abs/2403.07967
- Task: kharif rice yield forecasting in Indian districts.
- Data: 20 years of rice yield plus ERA5 climate / soil-water and NASA MODIS
  vegetation observations; 52 engineered growing-season features.
- Split: train on 2001–2018 (4,606 observations), test on 2019–2020 (502).
- Reported test results (all features): RF MAE 0.31, RMSE 0.41, R² 0.80;
  CatBoost 0.29, 0.39, 0.82; XGBoost 0.33, 0.43, 0.78. The paper's table
  does not label the MAE/RMSE units, so retain them as “as reported” unless
  checking the authors' released data/code before converting.

## KrishiMitra experiment result

This experiment uses the ICRISAT DLD apportioned yield table and the nine crop
families represented in Module 2 (Kharif and Rabi sorghum kept distinct). Its
chronological split is 1966–2012 train and 2013–2017 test (10,011 records).
Features are just crop, district, state and year; no soil, weather or satellite
features are joined. All 304 test districts also appear in training.

| Model | MAE (kg/ha) | RMSE (kg/ha) | R² |
|---|---:|---:|---:|
| Mean baseline | 770.31 | 1,252.26 | -0.207 |
| Random Forest | 676.89 | 1,071.50 | 0.116 |
| XGBoost | 683.10 | 1,080.97 | 0.100 |

In tonnes/ha, the MAE is 0.677 for Random Forest and 0.683 for XGBoost. These
results are weaker than the cited rice study, but they are **not a like-for-like
performance comparison**: the cited work predicts one crop with much richer,
season-specific climate and remote-sensing data, whereas this experiment pools
multiple crops and has only categorical geography/crop identity and year.
Further, the two time ranges and yield data sources differ. The defensible
report claim is that the local pipeline ran a temporal model comparison and
Random Forest slightly outperformed XGBoost on this initial feature set—not
that one model is generally better or that the scores reproduce the paper.

## Reporting rule

Only compare scores directly when target, crop scope, yield units, geography,
features, preprocessing, and train/test protocol are sufficiently aligned.
Otherwise put the results side by side as contextual literature, and describe
the differences. Do not compare a crop-classification “accuracy” with yield
regression MAE/RMSE/R².
