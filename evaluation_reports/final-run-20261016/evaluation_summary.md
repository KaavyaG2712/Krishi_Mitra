# KrishiMitra Module 2 and Module 3 evaluation

Metrics are task-specific and should not be compared across modules.

| Module | Model / engine | Status | Test samples | Key metrics |
|---|---|---:|---:|---|
| Crop yield benchmark (Module 2 experiment) | mean_baseline | evaluated | 10011 | mae_kg_ha=770.3075; rmse_kg_ha=1252.2561; r2=-0.2075; fit_seconds=0.1300; predict_seconds=0.0100 |
| Crop yield benchmark (Module 2 experiment) | random_forest | evaluated | 10011 | mae_kg_ha=676.8886; rmse_kg_ha=1071.5027; r2=0.1159; fit_seconds=35.0370; predict_seconds=0.0610 |
| Crop yield benchmark (Module 2 experiment) | xgboost | evaluated | 10011 | mae_kg_ha=683.0989; rmse_kg_ha=1080.9660; r2=0.1003; fit_seconds=0.4040; predict_seconds=0.0200 |
| Local agronomy advisor (Module 3) | PostgreSQL full-text retrieval | database_unavailable | — | — |

Module 3 retrieval could not be measured because PostgreSQL is missing `knowledge_chunks.search_vector`. Apply the repository's pending Alembic migration before rerunning. This evaluator does not apply migrations.

**Module 2 limitations:** Predictive yield evaluation does not evaluate crop choice utility or profit. Districts overlap train and test; this is not a new-district generalization test. Soil nutrients and weather are not joined as matched historical features. A crop's realized yield is not the same as its profitability or suitability. Model hyperparameters are fixed and not tuned.