"""Plain-JSON serialisation of Scope objects, so the app can load precomputed scopes."""
from __future__ import annotations

from .scope import Scope, UnitScope


def _dump_units(u: UnitScope) -> dict:
    return {"all": u.all_units, "s": sorted(u.serials), "sr": u.serial_ranges, "sp": u.serial_prefixes,
            "l": sorted(u.lots), "lr": u.lot_ranges, "lp": u.lot_prefixes, "dr": u.serial_date_rule}


def _load_units(d: dict) -> UnitScope:
    return UnitScope(all_units=d["all"], serials=set(d["s"]), serial_ranges=[tuple(x) for x in d["sr"]],
                     serial_prefixes=d["sp"], lots=set(d["l"]), lot_ranges=[tuple(x) for x in d["lr"]],
                     lot_prefixes=d["lp"], serial_date_rule=d["dr"])


def dump(s: Scope) -> dict:
    return {"ids": sorted(s.identifiers), "udi": sorted(s.udi_dis), "units": _dump_units(s.units),
            "per": {k: _dump_units(v) for k, v in s.per_identifier.items()}, "swi": s.software_include,
            "swe": s.software_exclude, "ev": s.evidence, "src": s.source}


def load(d: dict) -> Scope:
    return Scope(identifiers=set(d["ids"]), udi_dis=set(d["udi"]), units=_load_units(d["units"]),
                 per_identifier={k: _load_units(v) for k, v in d["per"].items()}, software_include=d["swi"],
                 software_exclude=d["swe"], evidence=d["ev"], source=d["src"])
