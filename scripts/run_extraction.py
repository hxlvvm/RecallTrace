"""Run LLM scope extraction against an OpenAI-compatible endpoint and append results to a JSONL cache.

usage: run_extraction.py BASE_URL MODEL OUT.jsonl [--split dev|test|all] [--workers N]
"""
import argparse
import concurrent.futures as cf
import gzip
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from recalltrace import aliases, llm_extract  # noqa: E402


def call(base, model, record, key=None):
    msgs = record.get("_messages") or llm_extract.messages(record["product_description"], record["code_info"])
    body = {"model": model, "messages": msgs,
            "temperature": 0, "max_tokens": 6000, "reasoning_effort": "low"}
    req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        reply = json.load(r)
    text = reply["choices"][0]["message"].get("content") or ""
    return {"id": record["product_res_number"], "model": model, "seconds": round(time.time() - t0, 2),
            "usage": reply.get("usage"), "extraction": llm_extract.parse_reply(text), "raw": text[:20000]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"), ap.add_argument("model"), ap.add_argument("out")
    ap.add_argument("--split", default="all"), ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--task", default="scope", choices=["scope", "aliases"])
    a = ap.parse_args()
    rows = [json.loads(l) for l in gzip.open(ROOT / "data/snapshot/recalls.jsonl.gz", "rt")]
    split = json.load(open(ROOT / "data/split.json"))
    done = set(llm_extract.load_cache(a.out))
    if a.task == "aliases":
        firms = {}
        for r in rows:
            firms.setdefault(r["recalling_firm"], []).append(r["product_description"])
        todo = [{"product_res_number": f, "_messages": aliases.messages(f, d)} for f, d in firms.items() if f not in done]
    else:
        todo = [r for r in rows if r["code_info"] and r["product_res_number"] not in done
                and (a.split == "all" or split[r["product_res_number"]] == a.split)]
    print(f"{len(todo)} records to extract", flush=True)
    with open(a.out, "a") as fh, cf.ThreadPoolExecutor(a.workers) as ex:
        futures = [ex.submit(call, a.base, a.model, r) for r in todo]
        for i, f in enumerate(cf.as_completed(futures), 1):
            try:
                fh.write(json.dumps(f.result()) + "\n")
            except Exception as e:  # keep going; failed records fall back to the regex parser
                print("error:", repr(e)[:200], flush=True)
            if i % 100 == 0:
                fh.flush()
                print(i, "done", flush=True)


if __name__ == "__main__":
    main()
