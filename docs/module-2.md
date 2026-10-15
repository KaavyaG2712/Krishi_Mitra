# Module 2: location, mapped soil, weather and crop economics

Implemented 8 October 2026. This is an explainable planning comparison, not a
trained profit predictor. Farmers do not enter soil values or provide a Soil
Health Card. The normal flow is: GPS/place search → sowing date, water and area
→ automatic soil/weather retrieval → up to three provisional crop options.

## Run this checkout

Project folder: `C:\Users\Ajay\.codex\worktrees\7110\proj1`.
Install the new runtime dependency once from this folder:

```powershell
backend\.venv\Scripts\python.exe -m pip install -e "./backend[dev]"
```

Then use `Start-KrishiMitra.cmd`. Module 2 itself needs no database, Gemini key,
SHC key or farmer account. Alternatively run the services directly:

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort
```

Open the URL Vite prints, normally http://127.0.0.1:5173. Choose **Check My Soil**.
The crop planner is the default Module 2 screen. Report import/manual tools are
still available in the optional report section. Report values are not silently
mixed into the map-based crop ranking.

## Data actually used

| Source | Fields and interpretation | Access / limitations |
|---|---|---|
| [OpenLandMap v0.2](https://docs.openlandmap.org/016-project.html) | pH, organic carbon and sand at **10 cm depth**, nominal **250 m** pixels | Public COG HTTP range reads from `https://s3.openlandmap.org/arco/`; no key. Global predictions based on historical samples (filename reference period 1950–2017), not current field tests or measured village averages. |
| [FAO ECOCROP](https://www.fao.org/land-water/resources/tools/databases/ecocrop/en) | Published absolute and optimal pH, temperature and **annual** rainfall ranges for nine crops | Factual numeric extract with source URLs in `crops.json`. A requirement catalogue, not profit training labels. |
| [Government Agricultural Statistics at a Glance 2024-25](https://nccd.gov.in/uploads/Agricultural_Statisitcs_at_a_Glance_2024_25_11da3cd37d.pdf#page=70) | Table 2.1, printed p40: national normal yields, **2020-21 to 2024-25**, kg/ha | Downloaded PDF. The contents page describes an older period; use the actual table heading. Season-specific yields used for maize, jowar and bajra; annual values for oilseeds. |
| [PIB Kharif 2026-27](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2260617) and [Rabi 2027-28](https://www.pib.gov.in/newsite/erelcontent.aspx?lang=2&reg=3&relid=295517) | Published MSP and national A2+FL production cost per quintal | Static, dated price scenario, **not live mandi data** or a promised procurement price. |
| [Open-Meteo forecast](https://open-meteo.com/en/docs) | Modelled current temperature, seven days of highs/lows/rain | No key for noncommercial use; attribution is displayed. Commercial deployment requires an appropriate plan/self-hosting. |
| [Open-Meteo historical weather](https://open-meteo.com/en/docs/historical-weather-api) | ERA5 daily temperature and rain for ten complete past calendar years, aggregated to monthly climate and annual rainfall | ERA5 chosen because the tested ERA5-Land daily response had null precipitation. All dates, units and values are validated. Climate is not a harvest-season forecast. |
| [Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api) | Indian place names and coordinates, GeoNames-backed | User must select a result; no silent selection of the first ambiguous place. |
| [Natural Earth](https://github.com/nvkelso/natural-earth-vector) | Public-domain 110m country polygon | Coarse mainland coverage check. Not a legal boundary map. Islands/coastal/border precision are not covered in this version. |

Raster filenames:

```
ph.h2o_usda.4c1a2a_m_250m_b10cm_19500101_20171231_go_epsg.4326_v0.2.tif
organic.carbon_usda.6a1c_m_250m_b10cm_19500101_20171231_go_epsg.4326_v0.2.tif
sand.wfraction_usda.3a1a1a_m_250m_b10cm_19500101_20171231_go_epsg.4326_v0.2.tif
```

Conversions are explicit: pH = raster / 10, organic carbon (%) = raster / 2,
sand (%) = raster. No available nitrogen, phosphorus, potassium, micronutrient
or EC measurements are invented. Only pH currently participates in crop
screening; carbon and sand are displayed as useful area context.

ISRIC's SoilGrids REST endpoint is documented as paused, and its REST/WCS/file
servers timed out during this implementation. The selected public OpenLandMap
COG service is a different product and is attributed accordingly. No government
portal scraping or CAPTCHA bypass is used.

## Ranking method and limits

1. Limit to the nine supported crops: wheat, chickpea, mustard, maize, sorghum,
   pearl millet, groundnut, soybean and sunflower. The UI never claims these are
   the best crops among all crops grown in India.
2. Filter by indicative application sowing-month windows. These are broad
   screening assumptions, not a district crop calendar. Local sowing windows
   and varieties require confirmation. Off-season cropping is intentionally
   not inferred from price alone.
3. Check mapped pH against FAO absolute limits. Check **each** of the first four
   monthly historical temperature means against its temperature limits. This
   is a screening approximation, not a cultivar-specific crop growth model.
   The four-month average must also lie inside the **optimal** temperature
   range: survival tolerance alone cannot put a high-margin crop on the list.
4. Compare annual rainfall to FAO **annual** rainfall limits (never compare
   seven-day rainfall to annual requirements). Any of the four growing months below **30 mm**
   is an application dry-month heuristic, not a sourced crop water requirement.
   Under rainfed selection, low annual or growing-month rain excludes a crop;
   irrigated/unconfirmed choices retain explicit irrigation conditions. Excess
   annual rain produces a drainage caution. Stored soil moisture is unknown.
5. Forecast extremes/heavy rain add sowing cautions only when the chosen date
   overlaps the seven-day forecast. Future dates use historical climate.
6. Rank passing crops by `yield kg/ha ÷ 100 × (MSP − cost/quintal)` and show up
   to three. Fewer than three or no match are legitimate outputs.

The resulting money is **benchmark surplus over A2+FL**, not full C2 net profit.
National yield and cost benchmarks do not predict a particular field's yield,
local input costs, sale price, harvest loss, transport, owned-land opportunity
cost or market access. No probability-of-profit, ML accuracy or guaranteed
return is asserted. Future marketing years still show the dated benchmark;
prices must be refreshed as government tables change.

Stress scenario: yield × 0.75, selling price × 0.80 and baseline cultivation
cost × 1.20. The cost does **not** fall automatically when stress lowers yield.
This is a sensitivity example, not a calibrated confidence interval.

For farm-specific profit forecasting, add geographically matched multi-year
yield/cost data and AGMARKNET/eNAM prices with documented access and commodity
units, plus harvest-time price validation. We did not train on the common
2,200-row NPK crop-class dataset: it has no suitable local cost/profit targets
and requires soil variables these maps do not supply.

## Code and refresh

- Backend routes: `GET /api/v1/planning/locations?q=...`,
  `POST /api/v1/planning/recommend`.
- Request: latitude, longitude, location_name, sowing_date, irrigation
  (`unknown`, `rainfed`, `available`), area_ha. Arbitrary client soil overrides
  and extra fields are rejected.
- Files: `backend/app/modules/planning/`,
  `frontend/src/components/CropPlanner.tsx`, `ModuleTwo.tsx`.
- Bundled numeric catalogue: `backend/app/modules/planning/data/crops.json`.
- Downloaded original references: `data/raw/module2/` (Git-ignored); no keys.
- Reference checksums: `backend/app/modules/planning/data/source-checksums.json`.
- Refresh downloads with `backend/scripts/download_planning_sources.py`, review
  the numeric rows and sowing assumptions in `build_planning_catalog.py`, then
  run that builder. Both scripts run with the backend virtual environment.
  The builder's price/yield entries are reviewed transcriptions; downloading
  new HTML alone does not silently rewrite economic assumptions.
- The catalogue and coverage GeoJSON are included in Python package data.

No location permission, search or external call occurs until the farmer acts.
Coordinates and place queries go to the named services for the requested
lookup. No location is written to browser storage or the database. Bounded
in-memory caches expire: soil/climate/place 24 hours, forecast 30 minutes.
Incomplete soil results are not cached. Transient network errors and HTTP
502/503/504 responses get one retry; quota errors are not retried automatically.
Deployments with multiple workers need a shared cache and global rate limiter.
No credentials appear in the frontend.

Missing soil pH or climate prevents ranking. A weather outage leaves a clearly
marked historical-only provisional shortlist. Partial soil values remain
partial. Responses never substitute synthetic demo values for source outages.

## Validation

From `backend`, run `.venv/Scripts/python.exe -m pytest -q`.
From `frontend`, run `npm test` and `npm run build`.
Tests cover economic units, fixed stress costs, ranking, seasonal yields,
water constraints, absent/invalid data, geography, geocoder country filtering,
API validation, no automatic location collection and acre conversion.

Core planner controls are translated into Hindi, Tamil and Telugu. Detailed
source explanations and caution text currently remain English and need
native-speaker localization before a regional-language field release.
