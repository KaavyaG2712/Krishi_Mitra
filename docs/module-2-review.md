# Module 2 completion and bug review — 8 October 2026

## Delivered workflow

Open Module 2, search for an Indian village/town or request GPS, select sowing
date, water availability and area, then request crop options. The backend reads
OpenLandMap pH, organic carbon and sand; current/seven-day Open-Meteo weather;
and ten years of ERA5 climate. It filters a nine-crop FAO catalogue and shows up
to three options ordered by a published national yield/MSP/A2+FL surplus
scenario. No Soil Health Card account, key or manual soil values are required.

The supporting FAO sheets and Indian government price/cost/yield references
were downloaded into `data/raw/module2`. The reviewed numerical catalogue and
source checksums are bundled with the backend. See [method and sources](module-2.md).

## Bugs found and resolved

| Finding | Change and verification |
|---|---|
| ERA5-Land response contained null rainfall | Use ERA5; reject null, nonfinite, inconsistent-unit or incomplete climate data. Regression verifies missing rainfall never becomes zero. |
| One cache lock held through network I/O | Cache coalesces identical requests while unrelated weather/climate lookups run concurrently. Barrier-based regression verifies concurrency. |
| Partial soil cached for 24 hours prevented recovery | Cache only complete soil results; retries can fill missing properties. Regression exercises partial → complete → cached. |
| Slow raster HTTP reads lost valid soil properties | Increased bounded read timeout; live checks returned all three properties. Local GeoTIFF regression verifies coordinate reads, unit conversions and nodata rejection. |
| Broad survival temperatures admitted unsuitable high-margin crops | Require four-month mean inside the FAO optimal temperature range, plus each monthly mean inside absolute limits. Cool-season groundnut and warm-season wheat regression cases now fail screening. This remains an application approximation. |
| Rainfed check considered only sowing month | Check all four growing months for the explicit 30 mm/month dry-month heuristic; do not assume irrigation or stored moisture. |
| Provider connection/server glitches immediately failed | Retry once for network errors and HTTP 502/503/504; no automatic retry for quota errors. Regression verifies both cases. |
| Slow frontend request locked controls without cancellation | Add Cancel lookup, request abort on cancellation/unmount, stale-result protection and a two-minute planner timeout. Regression verifies late responses cannot replace cancelled results. |
| Connection badge remained stale across backend recovery/failure | Poll health every 30 seconds while active; update false on network failure and display initial checking state. Regression verifies success → failure → recovery. |
| Failed lazy-loaded component could blank the application | Add a top-level error boundary with a reload action and unsaved-entry notice. Rendering failure regression exercises recovery UI. |
| Forecast accepted duplicate dates/inverted temperature ranges | Validate every expected date and low ≤ high. Regression covers both. |
| Server timezone could disagree with Indian forecast/sowing dates | Use the India calendar for backend date validation, forecast keys and historical-year boundaries. |
| Boolean values could coerce into numeric request fields | Coordinates and area now require numeric types; regression rejects booleans. |
| Long geocoder labels exceeded request length | Bound selected place labels to the same 180-character API limit. |
| Existing launcher did not detect missing soil dependency | Add rasterio to the startup dependency check. |

## Verification and its limits

- Final full backend suite: **87 passed**, including **27 planning tests**.
- Frontend suite: **37 passed**; TypeScript and Vite production build passed.
- `npm audit --omit=dev`: **0 known vulnerabilities** reported at review time.
- Live requests for Warangal, Ludhiana and Coimbatore exercised actual public
  sources. After screening changes, Ludhiana returned wheat/mustard/sunflower;
  Coimbatore returned groundnut/mustard/maize for the test date with irrigation.
  These are smoke-test outputs, not agronomic endorsements.
- An actual transient weather outage produced an explicit insufficient-data
  state rather than a fabricated ranking; retry recovered all sources and
  returned three crop options. External services can still fail.
- Browser checks at 390 px and 1280 px widths found no horizontal overflow;
  crop cards stacked on mobile and displayed in three columns on desktop.
  [Verified result screenshot](screenshots/module-2-results.jpg).
- Existing soil, voice, advisor, image validation and security regression tests
  passed. This turn did not validate real microphone transcription, paid Gemini
  responses, a real PostgreSQL conversation or model accuracy on a field image.
- Dependency deprecation warnings remain in FastAPI's test client and
  Rasterio/NumPy masked-array handling; these did not fail tests.

## Improvements in priority order

1. **District and crop-specific validation.** Replace broad month windows and
   the fixed four-month screen with reviewed district calendars, varieties,
   growth stages and irrigation needs. Validate shortlists with local KVK or
   agricultural-university agronomists before farmer field release.
2. **Local profit inputs.** Add licensed/authorized AGMARKNET or eNAM price
   history, district yields and local cultivation/transport costs. Forecast
   harvest-time price with out-of-time evaluation and uncertainty. MSP × national
   yield is a comparison scenario, not a field profit prediction.
3. **Better soil coverage.** Validate map predictions against permitted local
   samples and expose uncertainty. Add nutrient data only with documented units,
   depth, provenance and coverage. Do not infer plant-available N/P/K from pH,
   carbon and sand or train on incompatible synthetic NPK rows.
4. **Farmer usability.** Complete native-speaker Hindi/Tamil/Telugu translations
   for explanations and errors; add consent-based saved farm locations/plans,
   clearly dated offline results, and a printable comparison.
5. **Deployment reliability.** Containerize backend/frontend, pin reproducible
   dependencies, add CI, shared cache/rate limits and provider health metrics.
   Review Open-Meteo licensing/plan before commercial release. Current Compose
   starts only the database; it does not containerize the application.

The module is a working, transparent planning prototype. It does not establish
the three most profitable crops across every crop, district and farm in India.
