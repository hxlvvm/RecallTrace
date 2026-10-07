"""Inventory in, review queue out: identity matching, scope verdicts and evidence snippets."""
from __future__ import annotations

import gzip
import json
import pathlib
import re
from dataclasses import dataclass, field
from types import SimpleNamespace

from . import scope_io
from .match import RecallIndex, baseline_score
from .normalize import looks_like_code, norm_id
from .scope import AFFECTED, NOT_AFFECTED, check

ROOT = pathlib.Path(__file__).resolve().parents[2]
FDA_URL = "https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm?id={}"

REVIEW = "Potential match - review required"
MISMATCH = "Known scope mismatch"
MISSING = "Insufficient identifying information"
NEED_MODEL = "Possible recall - model number needed"
NONE_FOUND = "No candidate found in this snapshot"


@dataclass
class Finding:
    row: int
    status: str
    record: str | None = None
    firm: str = ""
    product: str = ""
    identity: str = ""
    scope: str = ""
    link: str = ""
    snippets: list[str] = field(default_factory=list)
    others: list[dict] = field(default_factory=list)


class Engine:
    """Loads the snapshot once; matching an inventory needs no network and no LLM call."""

    def __init__(self, root: pathlib.Path = ROOT):
        self.records = [json.loads(l) for l in gzip.open(root / "data/snapshot/recalls.jsonl.gz", "rt")]
        self.cfres = json.loads((root / "data/snapshot/cfres_ids.json").read_text())
        self.scope_data = json.loads(gzip.open(root / "data/index/scopes.json.gz", "rt").read())
        stubs = [SimpleNamespace(identifiers=set(self.scope_data[r["product_res_number"]]["ids"]),
                                 udi_dis=set(self.scope_data[r["product_res_number"]]["udi"])) for r in self.records]
        aliases = json.loads((root / "data/index/aliases.json").read_text())
        self.index = RecallIndex(self.records, stubs, aliases)
        self._scopes = {}

    def scope(self, i: int):
        if i not in self._scopes:
            self._scopes[i] = scope_io.load(self.scope_data[self.records[i]["product_res_number"]])
        return self._scopes[i]

    def review_row(self, n: int, row: dict) -> Finding:
        row = {k: (str(v).strip() if v not in (None, "") else None) for k, v in row.items()}
        exact = self.index.exact_hits(row)
        cands = self.index.candidates(row)
        feats = {j: self.index.features(row, j) for j in cands}
        scored = sorted(((baseline_score(feats[j]), j) for j in cands), reverse=True)
        has_code = looks_like_code(row.get("model")) or looks_like_code(row.get("ref")) or bool(row.get("udi_di"))

        if exact:
            ranked = sorted(exact, key=lambda j: (-feats.get(j, self.index.features(row, j))["manu_fuzzy"], j))
            verdicts = [(j, check(self.scope(j), row, self._text(j))) for j in ranked]
            order = {AFFECTED: 0, "unresolved": 1, NOT_AFFECTED: 2}
            verdicts.sort(key=lambda jv: order[jv[1].status])
            j, v = verdicts[0]
            status = {AFFECTED: REVIEW, NOT_AFFECTED: MISMATCH}.get(v.status, MISSING)
            ident = "identifier " + ", ".join(x for x in (row.get("model"), row.get("ref"), row.get("udi_di")) if x) + " appears in the recall"
            f = self._finding(n, status, j, row, ident, v.reason)
            f.others = [{"record": self.records[k]["product_res_number"], "verdict": vv.status, "reason": vv.reason,
                         "link": FDA_URL.format(self.cfres.get(self.records[k]["product_res_number"], ""))}
                        for k, vv in verdicts[1:]]
            return f
        top = [j for s, j in scored[:5] if feats[j]["manu_fuzzy"] >= 0.8 and feats[j]["device_fuzzy"] >= 0.6]
        if top and not has_code:
            f = self._finding(n, NEED_MODEL, top[0], row, "manufacturer and device name resemble this recall",
                              "no model, catalogue number or UDI recorded, so the product cannot be confirmed")
            f.others = [{"record": self.records[k]["product_res_number"], "verdict": "unresolved",
                         "reason": "model number needed", "link": FDA_URL.format(self.cfres.get(self.records[k]["product_res_number"], ""))}
                        for k in top[1:5]]
            return f
        f = Finding(n, NONE_FOUND, identity="no recall in this snapshot lists this identifier",
                    scope="absence here does not mean the device has no recall")
        if top:
            f.others = [{"record": self.records[k]["product_res_number"], "verdict": "similar product",
                         "reason": self.records[k]["product_description"][:80],
                         "link": FDA_URL.format(self.cfres.get(self.records[k]["product_res_number"], ""))} for k in top[:3]]
            f.identity += "; similar products from the same manufacturer were recalled"
        return f

    def review(self, rows: list[dict]) -> list[Finding]:
        return [self.review_row(n, r) for n, r in enumerate(rows)]

    def _text(self, j: int) -> str:
        r = self.records[j]
        return f'{r["product_description"]} {r["code_info"] or ""}'

    def _finding(self, n, status, j, row, identity, scope_reason) -> Finding:
        r = self.records[j]
        terms = [row.get(k) for k in ("model", "ref", "udi_di", "serial", "lot", "software") if row.get(k)]
        return Finding(n, status, r["product_res_number"], r["recalling_firm"], r["product_description"][:160],
                       identity, scope_reason, FDA_URL.format(self.cfres.get(r["product_res_number"], "")),
                       snippets(r["product_description"] + "\n" + (r["code_info"] or ""), terms))


def snippets(text: str, terms: list[str], width: int = 110, limit: int = 4) -> list[str]:
    """Short windows of the source text around each term, with the term wrapped in <mark>."""
    out = []
    for t in terms:
        m = re.search(re.escape(t), text, re.I) or _loose(text, t)
        if not m:
            continue
        a, b = max(0, m.start() - width), min(len(text), m.end() + width)
        out.append(("..." if a else "") + _esc(text[a:m.start()]) + "<mark>" + _esc(text[m.start():m.end()]) + "</mark>"
                   + _esc(text[m.end():b]) + ("..." if b < len(text) else ""))
        if len(out) >= limit:
            break
    return out


def _loose(text: str, term: str):
    core = norm_id(term)
    if len(core) < 4:
        return None
    return re.search(r"[\s\-]?".join(re.escape(c) for c in core), text, re.I)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")
