"""Download a bounded openFDA device-recall snapshot for a few product codes."""
import datetime
import json
import pathlib
import time
import urllib.parse
import urllib.request

CODES = {
    "FRN": "infusion pump",
    "CBK": "ventilator, facility use",
    "MKJ": "automated external defibrillator",
    "MHX": "physiological patient monitor",
    "DQA": "pulse oximeter",
}
BASE = "https://api.fda.gov/device/recall.json"
OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"


def fetch(code):
    rows, skip = [], 0
    while True:
        query = urllib.parse.urlencode({"search": f"product_code:{code}", "limit": 1000, "skip": skip})
        with urllib.request.urlopen(f"{BASE}?{query}", timeout=60) as r:
            page = json.load(r)
        rows += page["results"]
        skip += len(page["results"])
        if skip >= page["meta"]["results"]["total"] or not page["results"]:
            return rows
        time.sleep(1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"source": BASE, "licence": "openFDA data, CC0 (https://open.fda.gov/license/)",
                "retrieved": datetime.date.today().isoformat(), "queries": {}}
    for code, name in CODES.items():
        rows = fetch(code)
        (OUT / f"recalls_{code}.json").write_text(json.dumps(rows, indent=1))
        manifest["queries"][code] = {"device": name, "search": f"product_code:{code}", "records": len(rows)}
        print(code, len(rows))
        time.sleep(1)
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
