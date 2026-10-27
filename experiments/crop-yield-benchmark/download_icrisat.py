"""Fetch the ICRISAT DLD crop yield source response (offline experiment only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import csv
from datetime import datetime, timezone
from pathlib import Path

import httpx

API = "http://data.icrisat.org/dldAPI"
SOURCE_PAGE = "https://tci.cornell.edu/data/"
PORTAL_PAGE = "http://data.icrisat.org/dld/src/crops.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/crop-yield-benchmark"))
    parser.add_argument("--input", type=Path, help="Use an already normalized DLD CSV (state,district,year,crop,yield) instead of the API.")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "crop_yield_source.json"

    if args.input:
        content = args.input.read_bytes()
        destination = args.output_dir / "crop_yield.csv"
        destination.write_bytes(content)
        record = {"source_page": SOURCE_PAGE, "portal_page": PORTAL_PAGE,
                  "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                  "file": destination.name, "sha256": hashlib.sha256(content).hexdigest(),
                  "note": "User-provided CSV export from ICRISAT DLD; verify schema and units."}
    else:
        url = f"{API}/apportioned/area-production-yield"
        with httpx.Client(timeout=httpx.Timeout(args.timeout), follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        output.write_bytes(content)
        if not isinstance(payload, dict) or not isinstance(payload.get("headers"), list) or not isinstance(payload.get("data"), list):
            raise SystemExit("Unexpected ICRISAT API response. Raw response was saved; export the DLD table as CSV and rerun with --input.")
        yield_columns = [(i, str(item.get("header", ""))) for i, item in enumerate(payload["headers"])
                         if "yield" in str(item.get("header", "")).casefold()]
        if not yield_columns:
            raise SystemExit("No yield columns found in the ICRISAT response. Raw response was saved for inspection.")
        destination = args.output_dir / "crop_yield.csv"
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["state", "district", "year", "crop", "yield"])
            writer.writeheader()
            for row in payload["data"]:
                if len(row) <= 13:
                    continue
                for index, header in yield_columns:
                    if index >= len(row) or row[index] in (None, "", "NA", "N/A", "-"):
                        continue
                    try:
                        value = float(row[index])
                    except (TypeError, ValueError):
                        continue
                    if value < 0:
                        continue
                    crop = header.rsplit(" ", 1)[0].strip()
                    writer.writerow({"state": row[11], "district": row[13],
                                     "year": row[1], "crop": crop, "yield": value})
        normalized_bytes = destination.read_bytes()
        record = {"source_page": SOURCE_PAGE, "portal_page": PORTAL_PAGE, "api_url": url,
                  "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                  "raw_file": output.name, "raw_sha256": hashlib.sha256(content).hexdigest(),
                  "file": destination.name, "sha256": hashlib.sha256(normalized_bytes).hexdigest(),
                  "rows": sum(1 for _ in destination.open(encoding="utf-8")) - 1,
                  "note": "Raw response retained. ICRISAT labels yield in kg/ha; normalized crop names are preserved as source labels."}
    (args.output_dir / "source_metadata.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
