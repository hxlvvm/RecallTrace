"""Assign each recall event to dev or test by a stable hash, so related product rows never straddle the split."""
import gzip
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def split_of(event_id):
    h = int(hashlib.sha256(f"recalltrace-{event_id}".encode()).hexdigest(), 16)
    return "test" if h % 10 < 3 else "dev"


def main():
    rows = [json.loads(l) for l in gzip.open(ROOT / "data/snapshot/recalls.jsonl.gz", "rt")]
    split = {r["product_res_number"]: split_of(r["res_event_number"]) for r in rows}
    (ROOT / "data/split.json").write_text(json.dumps(split, indent=0, sort_keys=True))
    n = sum(v == "test" for v in split.values())
    print(f"{n} test / {len(split) - n} dev records")


if __name__ == "__main__":
    main()
