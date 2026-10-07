"""Structured recall scope and the per-unit verdict."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import in_range, looks_like_code, norm_id, udi_key

AFFECTED, NOT_AFFECTED, UNRESOLVED = "affected", "not_affected", "unresolved"


@dataclass
class UnitScope:
    """Which units of one product are covered; empty lists mean 'not constrained this way'."""
    all_units: bool = False
    serials: set[str] = field(default_factory=set)
    serial_ranges: list[tuple[str, str]] = field(default_factory=list)
    serial_prefixes: list[str] = field(default_factory=list)
    lots: set[str] = field(default_factory=set)
    lot_ranges: list[tuple[str, str]] = field(default_factory=list)
    lot_prefixes: list[str] = field(default_factory=list)
    serial_date_rule: dict | None = None

    def constrains(self, kind: str) -> bool:
        if kind == "serial":
            return bool(self.serials or self.serial_ranges or self.serial_prefixes or self.serial_date_rule)
        return bool(self.lots or self.lot_ranges or self.lot_prefixes)

    def is_empty(self) -> bool:
        return not (self.all_units or self.constrains("serial") or self.constrains("lot"))


@dataclass
class Scope:
    """Parsed scope of one recall record."""
    identifiers: set[str] = field(default_factory=set)
    udi_dis: set[str] = field(default_factory=set)
    units: UnitScope = field(default_factory=UnitScope)
    per_identifier: dict[str, UnitScope] = field(default_factory=dict)
    software_include: list[str] = field(default_factory=list)
    software_exclude: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)
    source: str = "rules"


@dataclass
class Verdict:
    status: str
    reason: str


def _date_rule_hit(serial: str, rule: dict) -> bool | None:
    digits = re.sub(r"\D", "", serial) if rule.get("digits_only") else serial
    start, length = int(rule["start"]), int(rule["length"])
    chunk = digits[start:start + length]
    if not chunk.isdigit() or len(chunk) != length:
        return None
    value = int(chunk)
    lo, hi = rule.get("min"), rule.get("max")
    return (lo is None or value >= int(lo)) and (hi is None or value <= int(hi))


def _match_units(units: UnitScope, unit: dict) -> Verdict:
    if units.all_units:
        return Verdict(AFFECTED, "all units of this product are in scope")
    for kind in ("serial", "lot"):
        if not units.constrains(kind):
            continue
        value = unit.get(kind)
        if not value:
            return Verdict(UNRESOLVED, f"recall is limited by {kind} number and the unit has none recorded")
        listed = units.serials if kind == "serial" else units.lots
        if norm_id(value) in {norm_id(v) for v in listed}:
            return Verdict(AFFECTED, f"{kind} {value} is listed in the recall")
        ranges = units.serial_ranges if kind == "serial" else units.lot_ranges
        comparable = False
        for a, b in ranges:
            hit = in_range(value, a, b)
            if hit:
                return Verdict(AFFECTED, f"{kind} {value} falls within {a} to {b}")
            comparable |= hit is not None
        prefixes = units.serial_prefixes if kind == "serial" else units.lot_prefixes
        for p in prefixes:
            if norm_id(value).startswith(norm_id(p)):
                return Verdict(AFFECTED, f"{kind} {value} starts with {p}")
        if kind == "serial" and units.serial_date_rule:
            hit = _date_rule_hit(value, units.serial_date_rule)
            if hit is None:
                return Verdict(UNRESOLVED, "serial does not fit the date-code format in the recall")
            return Verdict(AFFECTED if hit else NOT_AFFECTED, "serial date code " + ("inside" if hit else "outside") + " the recalled period")
        if ranges and not comparable and not listed and not prefixes:
            return Verdict(UNRESOLVED, f"{kind} format does not match the recalled ranges")
        return Verdict(NOT_AFFECTED, f"{kind} {value} is not in the recalled {kind} list or ranges")
    return Verdict(UNRESOLVED, "recall text does not state which units are affected")


def _merge(scopes: list[UnitScope]) -> UnitScope:
    if len(scopes) == 1:
        return scopes[0]
    m = UnitScope(all_units=any(u.all_units for u in scopes))
    for u in scopes:
        m.serials |= u.serials
        m.lots |= u.lots
        m.serial_ranges += u.serial_ranges
        m.lot_ranges += u.lot_ranges
        m.serial_prefixes += u.serial_prefixes
        m.lot_prefixes += u.lot_prefixes
        m.serial_date_rule = m.serial_date_rule or u.serial_date_rule
    return m


def check(scope: Scope, unit: dict, record_text: str = "") -> Verdict:
    """Verdict for one inventory unit against one recall record already matched by identity."""
    text = norm_id(record_text)
    ids = {norm_id(i) for i in scope.identifiers}
    udi = udi_key(unit.get("udi_di"))
    sub = None

    if udi and scope.udi_dis:
        if udi not in {udi_key(u) for u in scope.udi_dis}:
            return Verdict(NOT_AFFECTED, "UDI-DI is not among those listed in the recall")
    for key in ("ref", "model"):
        value = unit.get(key)
        if not value:
            continue
        nv = norm_id(value)
        hits = [u for ident, u in scope.per_identifier.items() if norm_id(ident) == nv]
        hits = hits or [u for ident, u in scope.per_identifier.items()
                        if looks_like_code(value) and norm_id(ident).startswith(nv) and not norm_id(ident)[len(nv):][:1].isdigit()]
        if hits:
            sub = _merge(hits)
        if looks_like_code(value) and ids and nv not in ids and nv not in text and sub is None:
            return Verdict(NOT_AFFECTED, f"{key} {value} is not one of the recalled models or catalogue numbers")

    soft = unit.get("software")
    if scope.software_exclude and soft and norm_id(soft) in {norm_id(s) for s in scope.software_exclude}:
        return Verdict(NOT_AFFECTED, f"software {soft} is explicitly excluded")
    if scope.software_include:
        if not soft:
            return Verdict(UNRESOLVED, "recall is limited to certain software versions and the unit has none recorded")
        if norm_id(soft) not in {norm_id(s) for s in scope.software_include}:
            return Verdict(NOT_AFFECTED, f"software {soft} is not a recalled version")

    if scope.per_identifier and sub is None and not scope.units.constrains("serial") and not scope.units.constrains("lot"):
        if not scope.units.all_units:
            return Verdict(UNRESOLVED, "recall scope depends on the model, and the unit's model is not one listed")
    units = sub if sub is not None else scope.units
    if units.is_empty() and (scope.identifiers or scope.udi_dis or sub is not None):
        return Verdict(AFFECTED, "recall names this product without limiting serial or lot numbers")
    return _match_units(units, unit)
