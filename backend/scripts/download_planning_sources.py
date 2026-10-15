"""Download primary-source reference material; does not execute downloaded code.

Run with backend's Python from any directory, then build_planning_catalog.py.
Global soil rasters are NOT downloaded here: runtime reads one COG window.
"""
import hashlib
import json
from pathlib import Path

import httpx
from build_planning_catalog import CROPS

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "data/raw/module2"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    sources = {f"{row[0]}.html": f"https://ecocrop.apps.fao.org/ecocrop/srv/en/dataSheet?id={row[2]}" for row in CROPS}
    sources.update({
        "statistics.pdf": "https://nccd.gov.in/uploads/Agricultural_Statisitcs_at_a_Glance_2024_25_11da3cd37d.pdf",
        "kharif.html": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2260617",
        "rabi.html": "https://www.pib.gov.in/newsite/erelcontent.aspx?lang=2&reg=3&relid=295517",
        "countries.geojson": "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson",
    })
    for name, url in sources.items():
        target = DEST / name
        with httpx.stream("GET", url, timeout=30, follow_redirects=True) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 30_000_000:
                    raise ValueError("Reference download exceeds 30 MB limit")
        target.write_bytes(content)
        print(name, len(content), hashlib.sha256(content).hexdigest())
    geo = json.loads((DEST / "countries.geojson").read_text(encoding="utf-8"))
    india = next(f for f in geo["features"] if f["properties"]["ADM0_A3"] == "IND")
    out = ROOT / "backend/app/modules/planning/data/india.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(india["geometry"]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
