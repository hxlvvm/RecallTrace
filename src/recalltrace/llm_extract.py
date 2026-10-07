"""LLM-assisted scope extraction: the model proposes structure, Python checks it against the source text."""
from __future__ import annotations

import json
import re
from collections import Counter

from . import rules
from .normalize import norm_id
from .scope import Scope, UnitScope

HEAD, TAIL = 2500, 600
TOP_KEYS = {"all_units", "unit_scope", "identifiers", "per_identifier", "udi_dis", "names"}

SYSTEM = """You read the scope text of a US FDA medical-device recall and return JSON describing which units are affected.
Rules:
- Copy every identifier, serial, lot, range end and prefix exactly as written in the text. Never invent or complete values.
- If the text gives ranges or lists separately for different models, catalogue numbers or list numbers, put them under
  "per_identifier", one entry per identifier, instead of mixing them.
- "all_units" is true only when the text says all serial numbers / all units / all lots of the named product are affected.
- Never copy more than 10 values of any list. For longer lists (or lists cut off with "[... N characters omitted ...]")
  give up to 10 example values and set "bulk_list" to "serial" or "lot"; the full list is read by code.
- If the text only names models, part, product, catalogue or list numbers without limiting serial or lot numbers,
  put them in "identifiers": that means every unit of those products is affected.
- Software versions: "software_include" when only those versions are affected, "software_exclude" for stated exceptions.
  Software versions that only describe the listed units are not a restriction.
- "serial_date_rule" only when the text explains that part of the serial encodes a date and limits the affected dates:
  {"start": 0-based index of the first date digit in the serial, "length": number of date digits,
   "min": smallest affected value or null, "max": largest affected value or null}.
- "evidence": short verbatim quotes from the text supporting all_units, ranges, prefixes, software and date rules.
- If the text does not say which units are affected, leave everything empty and explain in "unresolved_reason".
Return only the JSON object."""

SCHEMA = """{"all_units": bool, "identifiers": [str], "udi_dis": [str],
 "unit_scope": {"serials": [str], "serial_ranges": [[str, str]], "serial_prefixes": [str], "lots": [str],
                "lot_ranges": [[str, str]], "lot_prefixes": [str], "bulk_list": "serial"|"lot"|null,
                "serial_date_rule": object|null},
 "per_identifier": [{"identifier": str, "unit_scope": {same fields as unit_scope}}],
 "software_include": [str], "software_exclude": [str], "evidence": {str: str}, "unresolved_reason": str|null}"""

EXAMPLES = [
    ("HeartStartXL Defibrillator/Monitor Model : M4735A", "Serial Numbers: US00453441 through US00453910",
     {"all_units": False, "identifiers": ["M4735A"], "udi_dis": [],
      "unit_scope": {"serial_ranges": [["US00453441", "US00453910"]]}, "per_identifier": [],
      "evidence": {"serial_ranges": "US00453441 through US00453910"}, "unresolved_reason": None}),
    ("Baxter I-Pump infusion pump, product codes 2L3107, 2L3107K and 2L3107R",
     "product codes 2L3107 and 2L3107R, all serial numbers",
     {"all_units": True, "identifiers": ["2L3107", "2L3107R"], "udi_dis": [], "unit_scope": {}, "per_identifier": [],
      "evidence": {"all_units": "all serial numbers"}, "unresolved_reason": None}),
    ("ACCU-CHEK FlexLink Plus infusion set. Part Number 05511054001.",
     "Part Number: 05511054001.  Lots: GWX 001 up to GWX 206 and GWY 001 up to GWY 033.",
     {"all_units": False, "identifiers": ["05511054001"], "udi_dis": [],
      "unit_scope": {"lot_ranges": [["GWX 001", "GWX 206"], ["GWY 001", "GWY 033"]]}, "per_identifier": [],
      "evidence": {"lot_ranges": "GWX 001 up to GWX 206 and GWY 001 up to GWY 033"}, "unresolved_reason": None}),
    ("VOCSN Multi-Function Ventilators: REF: PRT-00490-001; REF: PRT-01185-000, PRT-01185-002",
     "REF/UDI-DI/Serial Numbers: PRT-00490-001/00855573007792/123627, 121892, 119639;  "
     "PRT-01185-000/00855573007877/5038421, 116700 [... 400 characters omitted ...] 118509, 5039387;  "
     "PRT-01185-002/00850018761154/5037655",
     {"all_units": False, "identifiers": ["PRT-00490-001", "PRT-01185-000", "PRT-01185-002"],
      "udi_dis": ["00855573007792", "00855573007877", "00850018761154"], "unit_scope": {},
      "per_identifier": [
          {"identifier": "PRT-00490-001", "unit_scope": {"serials": ["123627", "121892", "119639"]}},
          {"identifier": "PRT-01185-000", "unit_scope": {"serials": ["5038421", "116700", "5039387"], "bulk_list": "serial"}},
          {"identifier": "PRT-01185-002", "unit_scope": {"serials": ["5037655"]}}],
      "evidence": {}, "unresolved_reason": None}),
    ("HeartStart FR3 Defibrillator, Model: 861388, 861389",
     "Serial Numbers of affected AEDs begin with C16J, C16K, C17A, or C17B.  Serial Numbers: C17B-00171  C17A-01227 "
     "C17A-01349 [... 4600 characters omitted ...] C17B-00084",
     {"all_units": False, "identifiers": ["861388", "861389"], "udi_dis": [],
      "unit_scope": {"serials": ["C17B-00171", "C17A-01227", "C17A-01349", "C17B-00084"], "bulk_list": "serial"},
      "per_identifier": [], "evidence": {"serials": "Serial Numbers: C17B-00171"}, "unresolved_reason": None}),
]


def clip(text: str) -> str:
    text = text or ""
    if len(text) <= HEAD + TAIL + 200:
        return text
    return f"{text[:HEAD]} [... {len(text) - HEAD - TAIL} characters omitted ...] {text[-TAIL:]}"


def _user(description: str, code_info: str) -> str:
    return f"PRODUCT DESCRIPTION:\n{(description or '')[:1200]}\n\nSCOPE TEXT:\n{clip(code_info)}\n\nJSON schema:\n{SCHEMA}"


def messages(description: str, code_info: str) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM}]
    for d, c, out in EXAMPLES:
        msgs += [{"role": "user", "content": _user(d, c)}, {"role": "assistant", "content": json.dumps(out)}]
    return msgs + [{"role": "user", "content": _user(description, code_info)}]


def parse_reply(text: str) -> dict | None:
    """First balanced JSON object in the model reply, or None."""
    start = (text or "").find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break
                if isinstance(obj, dict) and obj.keys() & TOP_KEYS:
                    return obj
                break
        start = text.find("{", start + 1)
    return None


def load_cache(path) -> dict:
    out = {}
    try:
        for line in open(path):
            row = json.loads(line)
            out[row["id"]] = row.get("extraction")
    except FileNotFoundError:
        pass
    return out


def _grounded(values, haystack: str) -> list[str]:
    return [str(v) for v in values or [] if str(v).strip() and norm_id(str(v)) and norm_id(str(v)) in haystack]


def _unit_scope(raw: dict, haystack: str, code_info: str, dropped: Counter) -> UnitScope:
    raw = raw or {}
    u = UnitScope()
    for key in ("serials", "lots", "serial_prefixes", "lot_prefixes"):
        vals = _grounded(raw.get(key), haystack)
        dropped["values"] += len(raw.get(key) or []) - len(vals)
        if key in ("serials", "lots"):
            getattr(u, key).update(vals)
        else:
            getattr(u, key).extend(vals)
    for key in ("serial_ranges", "lot_ranges"):
        for pair in raw.get(key) or []:
            if isinstance(pair, (list, tuple)) and len(pair) == 2 and len(_grounded(pair, haystack)) == 2:
                getattr(u, key).append((str(pair[0]), str(pair[1])))
            else:
                dropped["ranges"] += 1
    rule = raw.get("serial_date_rule")
    if isinstance(rule, dict) and {"start", "length"} <= rule.keys():
        try:
            u.serial_date_rule = {"start": int(rule["start"]), "length": int(rule["length"]),
                                  "min": rule.get("min"), "max": rule.get("max")}
        except (TypeError, ValueError):
            dropped["rules"] += 1
    bulk = raw.get("bulk_list")
    if bulk not in ("serial", "lot"):
        bulk = "serial" if len(raw.get("serials") or []) >= 8 else "lot" if len(raw.get("lots") or []) >= 8 else None
    if bulk in ("serial", "lot"):
        target = u.serials if bulk == "serial" else u.lots
        parsed = rules.parse("", code_info).units
        harvested = parsed.serials | parsed.lots
        if not harvested:
            toks = rules._tokens(code_info)
            lengths = {len(norm_id(t)) for t in target}
            harvested = {t for t in toks if not lengths or min(abs(len(norm_id(t)) - n) for n in lengths) <= 3}
        target.update(harvested)
    return u


def to_scope(extraction: dict | None, record: dict) -> Scope:
    """Turn a cached extraction into a Scope, keeping only values found in the record text."""
    if not extraction:
        scope = rules.parse(record["product_description"], record["code_info"])
        scope.source = "rules-fallback"
        return scope
    code_info = record.get("code_info") or ""
    haystack = norm_id(f'{record.get("product_description") or ""} {code_info}')
    dropped = Counter()
    scope = Scope(source="llm")
    scope.identifiers = set(_grounded(extraction.get("identifiers"), haystack))
    scope.udi_dis = set(_grounded(extraction.get("udi_dis"), haystack))
    scope.units = _unit_scope(extraction.get("unit_scope"), haystack, code_info, dropped)
    scope.units.all_units = bool(extraction.get("all_units"))
    soft_in, soft_out = list(extraction.get("software_include") or []), list(extraction.get("software_exclude") or [])
    for entry in extraction.get("per_identifier") or []:
        if not isinstance(entry, dict):
            continue
        ident, raw = str(entry.get("identifier", "")), entry.get("unit_scope") or {}
        soft_in += raw.get("software_include") or []
        soft_out += raw.get("software_exclude") or []
        if ident and norm_id(ident) in haystack:
            scope.identifiers.add(ident)
            sub = _unit_scope(raw, haystack, code_info, dropped)
            if not sub.is_empty():
                scope.per_identifier[ident] = sub
    scope.software_include = _grounded(soft_in, haystack)
    scope.software_exclude = _grounded(soft_out, haystack)
    if scope.units.serials and not scope.per_identifier:
        scope.software_include = []  # an explicit serial list is authoritative
    if scope.units.all_units and (scope.units.serials or scope.units.lots):
        scope.units.all_units = False
    scope.evidence = {k: v for k, v in (extraction.get("evidence") or {}).items()
                      if isinstance(v, str) and norm_id(v) and norm_id(v) in haystack}
    scope.evidence["_dropped"] = json.dumps(dict(dropped))
    return scope
