"""Candidate retrieval and pair features for matching inventory rows to recall records."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from rapidfuzz import fuzz

from .normalize import looks_like_code, norm_id, udi_key

STOP = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "dba", "of", "the", "and", "div", "division",
        "usa", "north", "america", "systems", "system", "medical", "healthcare", "health", "gmbh", "limited", "with", "for"}
WORD = re.compile(r"[a-z0-9]+")


def words(text: str) -> list[str]:
    return [w for w in WORD.findall((text or "").lower()) if w not in STOP and len(w) > 1]


def firm_key(firm: str) -> str:
    """Short firm key: 'CareFusion 303, Inc.' -> 'carefusion'."""
    ws = [w for w in words(firm) if not w.isdigit()]
    return ws[0] if ws else ""


class RecallIndex:
    """BM25 over firm + description text, plus exact lookups for identifiers and UDI-DIs."""

    def __init__(self, records: list[dict], scopes: list, aliases: dict[str, list[str]] | None = None):
        self.records, self.scopes = records, scopes
        self.aliases = {k.lower(): [a.lower() for a in v] for k, v in (aliases or {}).items()}
        self.docs, self.by_id, self.by_udi = [], defaultdict(set), defaultdict(set)
        for i, (r, s) in enumerate(zip(records, scopes)):
            names = [r["recalling_firm"]] + self.aliases.get(r["recalling_firm"].lower(), [])
            self.docs.append(Counter(words(" ".join(names) + " " + r["product_description"][:400])))
            for ident in s.identifiers:
                if looks_like_code(ident):
                    self.by_id[norm_id(ident)].add(i)
            for u in s.udi_dis:
                self.by_udi[udi_key(u)].add(i)
        self.df = Counter(w for d in self.docs for w in d)
        self.avg = sum(sum(d.values()) for d in self.docs) / max(len(self.docs), 1)

    def bm25(self, query: list[str], i: int, k1: float = 1.2, b: float = 0.75) -> float:
        d, n, score = self.docs[i], len(self.docs), 0.0
        dl = sum(d.values())
        for w in set(query):
            if w in d:
                idf = math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                score += idf * d[w] * (k1 + 1) / (d[w] + k1 * (1 - b + b * dl / self.avg))
        return score

    def exact_hits(self, row: dict) -> set[int]:
        hits = set()
        for key in ("model", "ref"):
            if looks_like_code(row.get(key)):
                hits |= self.by_id.get(norm_id(row[key]), set())
        if row.get("udi_di"):
            hits |= self.by_udi.get(udi_key(row["udi_di"]), set())
        return hits

    def candidates(self, row: dict, k: int = 30) -> list[int]:
        q = words(f'{row.get("manufacturer", "")} {row.get("device", "")} {row.get("model", "")}')
        scored = sorted(range(len(self.docs)), key=lambda i: -self.bm25(q, i))[:k]
        return list(dict.fromkeys(list(self.exact_hits(row)) + scored))

    def features(self, row: dict, i: int) -> dict[str, float]:
        r, s = self.records[i], self.scopes[i]
        text = norm_id(f'{r["product_description"]} {(r.get("code_info") or "")[:5000]}')
        ids = {norm_id(x) for x in s.identifiers}
        names = [r["recalling_firm"]] + self.aliases.get(r["recalling_firm"].lower(), [])
        manu = row.get("manufacturer", "")
        f = {
            "udi_exact": float(bool(row.get("udi_di")) and i in self.by_udi.get(udi_key(row["udi_di"]), set())),
            "code_exact": 0.0, "code_in_text": 0.0, "code_conflict": 0.0, "has_code": 0.0,
            "manu_fuzzy": max((fuzz.token_set_ratio(manu.lower(), n.lower()) for n in names), default=0) / 100 if manu else 0.0,
            "manu_partial": max((fuzz.partial_ratio(manu.lower(), n.lower()) for n in names), default=0) / 100 if manu else 0.0,
            "device_fuzzy": fuzz.token_set_ratio(row.get("device", "").lower(), r["product_description"][:300].lower()) / 100,
            "bm25": self.bm25(words(f'{manu} {row.get("device", "")} {row.get("model", "")}'), i) / 20,
        }
        for key in ("model", "ref"):
            v = row.get(key)
            if not looks_like_code(v):
                continue
            f["has_code"] = 1.0
            nv = norm_id(v)
            if nv in ids:
                f["code_exact"] = 1.0
            elif nv in text:
                f["code_in_text"] = 1.0
            elif any(len(x) == len(nv) and fuzz.ratio(x, nv) >= 80 for x in ids):
                f["code_conflict"] = 1.0
        return f


def baseline_score(f: dict[str, float]) -> float:
    """Hand-weighted baseline: exact identifiers first, then manufacturer and text similarity."""
    return (3 * f["udi_exact"] + 2 * f["code_exact"] + 1.5 * f["code_in_text"] + f["manu_fuzzy"]
            + f["device_fuzzy"] + 0.5 * f["bm25"])
