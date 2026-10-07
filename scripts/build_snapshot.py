"""Trim the raw openFDA download to the fields RecallTrace uses and write one gzipped JSONL."""
import glob
import gzip
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEEP = ["product_res_number", "res_event_number", "product_code", "recalling_firm", "product_description",
        "code_info", "reason_for_recall", "action", "recall_status", "event_date_initiated", "event_date_posted",
        "root_cause_description", "k_numbers"]


def main():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "data/raw/recalls_*.json"))):
        for r in json.load(open(f)):
            row = {k: r.get(k) for k in KEEP}
            row["device_name"] = (r.get("openfda") or {}).get("device_name")
            rows.append(row)
    rows.sort(key=lambda r: r["product_res_number"])
    out = ROOT / "data/snapshot/recalls.jsonl.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    events = len({r["res_event_number"] for r in rows})
    print(len(rows), "records,", events, "events ->", out, out.stat().st_size // 1024, "kB")


if __name__ == "__main__":
    main()
