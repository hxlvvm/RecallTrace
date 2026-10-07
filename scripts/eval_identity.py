"""Identity retrieval on synthetic inventory rows: baseline vs learned reranker.

usage: eval_identity.py [rules|llm] [--aliases]
Rows are generated from dev-split records for training and test-split records for evaluation.
Ranking is 'filtered': other records of the same product (same firm, shared code) are removed before
the rank of the source record is taken, so repeat recalls of one product do not count as misses.
"""
import gzip
import json
import pathlib
import random
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from recalltrace import aliases, llm_extract, rules  # noqa: E402
from recalltrace.match import RecallIndex, baseline_score, firm_key  # noqa: E402
from recalltrace.normalize import looks_like_code, norm_id  # noqa: E402
from recalltrace.synth import make_row  # noqa: E402

NOISES = ["clean", "alias", "abbrev", "typo", "no_id"]


def equivalents(records, scopes):
    key = {}
    for i, (r, s) in enumerate(zip(records, scopes)):
        codes = {norm_id(c) for c in s.identifiers if looks_like_code(c)}
        key[i] = (firm_key(r["recalling_firm"]), codes, norm_id(r["product_description"][:60]))
    eq = {}
    for i in key:
        f, c, d = key[i]
        eq[i] = {j for j in key if key[j][0] == f and (key[j][1] & c or key[j][2] == d)}
    return eq


def rank_of(order, target, same):
    r = 0
    for j in order:
        if j == target:
            return r
        if j not in same:
            r += 1
    return 10 ** 6


def build(index, records, scopes, ids, rng, per=1):
    data = []
    for i in ids:
        for noise in NOISES:
            for _ in range(per):
                row = make_row(records[i], scopes[i], rng, noise)
                cands = index.candidates(row)
                feats = [index.features(row, j) for j in cands]
                data.append((i, noise, row, cands, feats))
    return data


def main():
    parser = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "rules"
    records = [json.loads(l) for l in gzip.open(ROOT / "data/snapshot/recalls.jsonl.gz", "rt")]
    split = json.load(open(ROOT / "data/split.json"))
    cache = llm_extract.load_cache(ROOT / "data/extractions/llm.jsonl") if parser == "llm" else {}
    scopes = [llm_extract.to_scope(cache.get(r["product_res_number"]), r) if parser == "llm"
              else rules.parse(r["product_description"], r["code_info"]) for r in records]
    al = aliases.load(ROOT / "data/extractions/aliases.jsonl") if "--aliases" in sys.argv else {}
    index = RecallIndex(records, scopes, al)
    eq = equivalents(records, scopes)
    rng = random.Random(0)
    dev = [i for i, r in enumerate(records) if split[r["product_res_number"]] == "dev"]
    test = [i for i, r in enumerate(records) if split[r["product_res_number"]] == "test"]
    train = build(index, records, scopes, rng.sample(dev, 400), rng)
    evals = build(index, records, scopes, test, random.Random(1))

    names = sorted(train[0][4][0])
    X, y = [], []
    for i, _, _, cands, feats in train:
        for j, f in zip(cands, feats):
            if j in eq[i] and j != i:
                continue
            X.append([f[n] for n in names]); y.append(int(j == i))
    model = LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced").fit(np.array(X), np.array(y))

    out = {}
    for label, scorer in (("baseline", lambda fs: [baseline_score(f) for f in fs]),
                          ("reranker", lambda fs: model.decision_function(np.array([[f[n] for n in names] for f in fs])))):
        per_noise = {}
        for noise in NOISES + ["noisy", "all"]:
            sub = [d for d in evals if d[1] == noise or noise == "all" or (noise == "noisy" and d[1] != "clean")]
            ranks = []
            for i, _, _, cands, feats in sub:
                order = [cands[k] for k in np.argsort(-np.array(scorer(feats)), kind="stable")]
                ranks.append(rank_of(order, i, eq[i] - {i}))
            ranks = np.array(ranks)
            per_noise[noise] = {"n": len(ranks), "top1": round(float(np.mean(ranks < 1)), 3),
                                "top3": round(float(np.mean(ranks < 3)), 3), "top10": round(float(np.mean(ranks < 10)), 3)}
        out[label] = per_noise
    out["coefficients"] = dict(zip(names, np.round(model.coef_[0], 2).tolist()))
    print(json.dumps({"parser": parser, "aliases": bool(al), **out}, indent=1))


if __name__ == "__main__":
    main()
