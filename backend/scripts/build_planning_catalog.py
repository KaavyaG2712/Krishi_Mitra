"""Rebuild the small, attributed crop catalogue from downloaded primary sources.

Run from the repository root after downloading the sources listed in
docs/module-2.md to data/raw/module2. No training accuracy is claimed.
"""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag in {"td", "th"}:
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            if self.row is not None:
                self.row.append(" ".join(self.cell.split()))
            self.cell = None
        if tag == "tr" and self.row:
            self.rows.append(self.row)
            self.row = None


# Yield: E,S&E, Agricultural Statistics at a Glance 2024-25, table 2.1,
# printed p40 / PDF p70: 2020-21 through 2024-25 normal estimates, kg/ha.
# Months are conservative application screening windows, NOT FAO sowing dates.
CROPS = [
    ("wheat", "Wheat", 2114, {"rabi": 3547}, [10, 11, 12], 2610, 1264, "rabi"),
    ("gram", "Chickpea (gram)", 2479, {"rabi": 1199}, [10, 11, 12], 5958, 3751, "rabi"),
    ("mustard", "Rapeseed / mustard", 548, {"rabi": 1468}, [9, 10, 11], 6613, 3367, "rabi"),
    ("maize", "Maize", 2175, {"kharif": 2847, "rabi": 5206, "summer": 4743}, [1, 2, 6, 7, 10, 11], 2410, 1544, "kharif"),
    ("jowar", "Sorghum (jowar)", 48747, {"kharif": 1152, "rabi": 1129}, [6, 7, 9, 10], 4023, 2682, "kharif"),
    ("bajra", "Pearl millet (bajra)", 8418, {"kharif": 1427, "summer": 2526}, [2, 3, 6, 7], 2900, 1858, "kharif"),
    ("groundnut", "Groundnut", 2199, {"annual": 1945}, [1, 2, 6, 7, 10, 11], 7517, 5011, "kharif"),
    ("soybean", "Soybean", 1150, {"annual": 1071}, [6, 7], 5708, 3805, "kharif"),
    ("sunflower", "Sunflower", 1191, {"annual": 1042}, [1, 2, 6, 7, 10, 11], 8343, 5562, "kharif"),
]
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/module2"
DEST = ROOT / "backend/app/modules/planning/data"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    crops = []
    for key, name, eco_id, yields, months, price, cost, economics in CROPS:
        parser = Rows()
        parser.feed((RAW / f"{key}.html").read_text(encoding="utf-8"))
        values = {}
        for label, target in [("Temperat. requir.", "temperature"), ("Rainfall (annual)", "annual_rain"), ("Soil PH", "ph")]:
            row = next(r for r in parser.rows if r[0] == label)
            numbers = [float(v) for v in row[1:5]]
            assert len(numbers) == 4 and numbers[2] <= numbers[0] <= numbers[1] <= numbers[3], row
            values[target] = dict(zip(["optimal_min", "optimal_max", "min", "max"], numbers))
        crops.append(dict(id=key, name=name, requirements=values, yields_kg_ha=yields,
                          sowing_months=months, price_inr_quintal=price, cost_inr_quintal=cost,
                          marketing_season="2027-28" if economics == "rabi" else "2026-27",
                          price_kind="MSP benchmark", cost_basis="All-India A2+FL production cost benchmark",
                          requirements_source=f"https://ecocrop.apps.fao.org/ecocrop/srv/en/dataSheet?id={eco_id}",
                          economics_source="https://www.pib.gov.in/newsite/erelcontent.aspx?lang=2&reg=3&relid=295517" if economics == "rabi" else "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2260617"))
    result = {"version": "2026-10-08", "yield_period": "2020-21 to 2024-25",
              "yield_source": "https://nccd.gov.in/uploads/Agricultural_Statisitcs_at_a_Glance_2024_25_11da3cd37d.pdf#page=70",
              "yield_table": "2.1 (national normal estimates, kg/ha)", "crops": crops}
    (DEST / "crops.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.glob("*") if p.suffix in {".html", ".pdf"}}
    (DEST / "source-checksums.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(crops)} crop records")


if __name__ == "__main__":
    main()
