"""LLM-suggested brand and parent-company names for each recalling firm (matcher side)."""
from __future__ import annotations

import json

SYSTEM = """You map the legal name of a medical-device company, as written in an FDA recall, to the names a hospital
equipment inventory is likely to use for it: the short company name, current parent company after acquisitions,
and the main product brand names. Return JSON {"names": [str, ...]} with at most 6 short names. Use only names you
are confident about; return an empty list if unsure."""


def messages(firm: str, sample_descriptions: list[str]) -> list[dict]:
    ctx = "\n".join(f"- {d[:160]}" for d in sample_descriptions[:3])
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Recalling firm: {firm}\nExample recalled products:\n{ctx}"}]


def load(path) -> dict[str, list[str]]:
    out = {}
    try:
        for line in open(path):
            row = json.loads(line)
            names = (row.get("extraction") or {}).get("names") or []
            out[row["id"]] = [str(n) for n in names if isinstance(n, str) and 1 < len(n) < 40][:6]
    except FileNotFoundError:
        pass
    return out
