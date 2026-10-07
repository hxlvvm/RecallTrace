"""Score a scope parser on the hand-written probes: python scripts/eval_scope.py rules|llm [split]."""
import gzip
import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from recalltrace import rules  # noqa: E402
from recalltrace.scope import AFFECTED, NOT_AFFECTED, UNRESOLVED, check  # noqa: E402


def load_parser(name):
    if name == "rules":
        return lambda r: rules.parse(r["product_description"], r["code_info"])
    from recalltrace import llm_extract
    cache = llm_extract.load_cache(ROOT / "data/extractions/llm.jsonl")
    return lambda r: llm_extract.to_scope(cache.get(r["product_res_number"]), r)


def evaluate(parser, probes, rows, show=False):
    c, wrong, false_reassure, unres_definitive = Counter(), [], 0, 0
    for p in probes:
        r = rows[p["res"]]
        v = check(parser(r), p["unit"], f'{r["product_description"]} {r["code_info"]}')
        truth = p["expect"]
        c[(truth, v.status)] += 1
        if truth != UNRESOLVED and v.status not in (UNRESOLVED, truth):
            wrong.append((p, v))
            false_reassure += truth == AFFECTED
        if truth == UNRESOLVED and v.status != UNRESOLVED:
            unres_definitive += 1
            wrong.append((p, v))
    n = len(probes)
    definitive_truth = sum(p["expect"] != UNRESOLVED for p in probes)
    covered = sum(v for (t, s), v in c.items() if t != UNRESOLVED and s != UNRESOLVED)
    correct = c[(AFFECTED, AFFECTED)] + c[(NOT_AFFECTED, NOT_AFFECTED)] + c[(UNRESOLVED, UNRESOLVED)]
    wrong_def = sum(v for (t, s), v in c.items() if t != UNRESOLVED and s not in (UNRESOLVED, t))
    res = {"probes": n, "correct": correct, "wrong_definitive": wrong_def, "false_reassurance": false_reassure,
           "coverage": round(covered / definitive_truth, 3), "definitive_on_unresolved": unres_definitive}
    res["gate_pass"] = (wrong_def <= 0.05 * n and false_reassure <= 2 and res["coverage"] >= 0.80
                        and unres_definitive <= 1)
    if show:
        for p, v in wrong:
            print("  WRONG", p["res"], p["unit"], "expect", p["expect"], "got", v.status, "-", v.reason)
    return res


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "rules"
    rows = {json.loads(l)["product_res_number"]: json.loads(l) for l in gzip.open(ROOT / "data/snapshot/recalls.jsonl.gz", "rt")}
    probes = [json.loads(l) for l in open(ROOT / "data/gold" / ("scope_probes_blind.jsonl" if "--blind" in sys.argv else "scope_probes.jsonl"))]
    print(name, json.dumps(evaluate(load_parser(name), probes, rows, show="-v" in sys.argv)))


if __name__ == "__main__":
    main()
