"""Precompute the small identity index and alias table the app loads at start-up."""
import gzip
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from recalltrace import aliases, llm_extract, scope_io  # noqa: E402


def main():
    records = [json.loads(l) for l in gzip.open(ROOT / "data/snapshot/recalls.jsonl.gz", "rt")]
    cache = llm_extract.load_cache(ROOT / "data/extractions/llm.jsonl")
    out, full = {}, {}
    for r in records:
        s = llm_extract.to_scope(cache.get(r["product_res_number"]), r)
        out[r["product_res_number"]] = {"ids": sorted(s.identifiers), "udi": sorted(s.udi_dis), "src": s.source}
        full[r["product_res_number"]] = scope_io.dump(s)
    (ROOT / "data/index").mkdir(exist_ok=True)
    with gzip.open(ROOT / "data/index/scopes.json.gz", "wt") as fh:
        json.dump(full, fh)
    (ROOT / "data/index/aliases.json").write_text(json.dumps(aliases.load(ROOT / "data/extractions/aliases.jsonl"), indent=0))
    print(len(out), "records;", sum(v["src"] == "llm" for v in out.values()), "from LLM extractions")


if __name__ == "__main__":
    main()
