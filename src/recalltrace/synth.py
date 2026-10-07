"""Synthetic inventory rows derived from recall records, with typed noise for evaluation."""
from __future__ import annotations

import random
import re

from .match import firm_key
from .normalize import looks_like_code

# Hand-written brand/parent names used only to generate test rows; the matcher never sees this table.
EVAL_ALIASES = {
    "carefusion": ["BD", "Becton Dickinson"], "hospira": ["ICU Medical", "Pfizer"], "covidien": ["Medtronic"],
    "oridion": ["Medtronic"], "respironics": ["Philips"], "physio": ["Stryker"], "cardiac": ["ZOLL"],
    "smiths": ["ICU Medical"], "viasys": ["Vyaire"], "cardinal": ["Vyaire"], "welch": ["Baxter", "Hillrom"],
    "zevex": ["Moog"], "draeger": ["Drager"], "draegar": ["Drager"], "newport": ["Medtronic"], "maquet": ["Getinge"],
    "del": ["Spacelabs"], "pulmonetic": ["Vyaire"], "medtronic": ["Physio-Control"], "philips": ["Philips Healthcare"],
}
GENERIC = {"the", "a", "an", "infusion", "pump", "automated", "external", "patient", "monitor", "ventilator", "system",
           "pulse", "oximeter", "single", "large", "volume", "portable", "product", "model", "and", "with", "for"}


def short_device(description: str, n: int = 4) -> str:
    ws = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9+\-]*", description.split(".")[0])
          if w.lower() not in {"ref", "model", "catalog", "product", "usage", "number", "no"}]
    return " ".join(ws[:n])


def brand(record: dict) -> str:
    first = re.findall(r"[A-Za-z][A-Za-z\-]+", record["product_description"])[:1]
    if first and first[0].lower() not in GENERIC and first[0][0].isupper() and len(first[0]) > 2:
        return first[0]
    return firm_key(record["recalling_firm"]).title()


def _typo(s: str, rng: random.Random) -> str:
    if len(s) < 4:
        return s
    i = rng.randrange(1, len(s) - 1)
    return s[:i] + s[i + 1] + s[i] + s[i + 2:] if rng.random() < 0.5 else s[:i] + s[i + 1:]


def make_row(record: dict, scope, rng: random.Random, noise: str = "clean") -> dict:
    codes = sorted(i for i in scope.identifiers if looks_like_code(i))
    row = {"manufacturer": brand(record), "device": short_device(record["product_description"]),
           "model": rng.choice(codes) if codes else None,
           "udi_di": rng.choice(sorted(scope.udi_dis)) if scope.udi_dis and noise == "clean" and rng.random() < 0.3 else None}
    if noise == "alias":
        row["manufacturer"] = rng.choice(EVAL_ALIASES.get(firm_key(record["recalling_firm"]), [row["manufacturer"]]))
    elif noise == "abbrev":
        row["device"] = short_device(record["product_description"], 2)
        row["model"] = None
    elif noise == "typo":
        row["manufacturer"] = _typo(row["manufacturer"], rng)
        row["device"] = _typo(row["device"], rng)
    elif noise == "no_id":
        row["model"] = None
    return row
