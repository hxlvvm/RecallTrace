"""Regex-only scope parser: the baseline the LLM-assisted parser has to beat."""
from __future__ import annotations

import re
from collections import Counter

from .normalize import in_range, norm_id
from .scope import Scope, UnitScope

SERIAL = r"(?:parent\s+sn|serial\s*(?:numbers?|nos?\.?|#)?|s/n|\bsn\b)"
LOT = r"(?:lot\s*(?:numbers?|nos?\.?|#)?|lotnumbers|batch\s*(?:numbers?)?)"
IDENT = (r"(?:\bref\b|model(?:\s*(?:no\.?|numbers?|/id\s*#?))?|catalog(?:ue)?\s*(?:numbers?|no\.?)?|"
         r"part\s*(?:numbers?|no\.?)|p/n|product\s*(?:codes?|numbers?)|list\s*numbers?|article\s*number|"
         r"item\s*numbers?|udi(?:-di)?s?)")
LABEL = re.compile(rf"(?P<serial>{SERIAL})|(?P<lot>{LOT})|(?P<ident>{IDENT})", re.I)
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/.]*[A-Za-z0-9]")
RANGE = re.compile(r"(?P<a>[A-Za-z0-9][A-Za-z0-9\-]*\d)\s*(?:through|thru|up\s+to|to|-|–)\s*(?P<b>[A-Za-z0-9][A-Za-z0-9\-]*\d)", re.I)
ALL_UNITS = re.compile(r"\ball\s+(?:the\s+)?(?:serial\s*(?:numbers?|nos?\.?)|units|lots|devices|monitors|ventilators|"
                       r"pumps|aeds|defibrillators|products?)\b|serial\s*(?:numbers?|nos?\.?)\s*:?\s*all\b", re.I)
PREFIX = re.compile(r"(?:begin(?:s|ning)?\s+with|start(?:s|ing)?\s+with|prefix(?:es)?)\s+([A-Z0-9][A-Z0-9 ,]*(?:\s*(?:,|or|and)\s*[A-Z0-9]+)*)", re.I)
SOFTWARE = re.compile(r"software\s*(?:versions?|revisions?|rev\.?)\s+((?:[A-Z]?\d+(?:\.[0-9A-Z]+)+|[A-Z]\.\d+)(?:\s*(?:,|and|or)\s*(?:[A-Z]?\d+(?:\.[0-9A-Z]+)+|[A-Z]\.\d+))*)", re.I)
EXCEPT = re.compile(r"except\s+(\d+(?:\.\d+)+)", re.I)
UDI = re.compile(r"(?:\(01\))?\b(\d{14}|\d{12})\b")


def _shape(tok: str) -> str:
    return re.sub(r"[A-Z]+", "A", re.sub(r"\d+", "9", tok.upper()))


def _tokens(segment: str) -> list[str]:
    return [t for t in TOKEN.findall(segment) if any(c.isdigit() for c in t) and len(t) >= 3]


def _split_ranges(segment: str) -> tuple[list[tuple[str, str]], str]:
    ranges = []
    for m in RANGE.finditer(segment):
        a, b = m.group("a"), m.group("b")
        if in_range(a, a, b) is not None and norm_id(a) <= norm_id(b) or in_range(a, a, b):
            ranges.append((a, b))
    return ranges, RANGE.sub(lambda m: " " if (m.group("a"), m.group("b")) in ranges else m.group(0), segment)


def parse(description: str, code_info: str) -> Scope:
    scope = Scope(source="rules")
    text = code_info or ""
    both = f"{description or ''}\n{text}"
    if ALL_UNITS.search(text) or re.fullmatch(r"\s*all\b.*", text, re.I | re.S) and len(text) < 120:
        scope.units.all_units = True
        scope.evidence["all_units"] = (ALL_UNITS.search(text) or re.search(r".{0,60}", text)).group(0)

    scope.udi_dis = {m.group(1) for m in UDI.finditer(both)}
    labels = list(LABEL.finditer(text))
    for i, m in enumerate(labels):
        seg = text[m.end(): labels[i + 1].start() if i + 1 < len(labels) else len(text)]
        kind = m.lastgroup
        if kind == "ident":
            scope.identifiers |= {t for t in _tokens(seg)[:40] if not UDI.fullmatch(t)}
            continue
        ranges, rest = _split_ranges(seg)
        toks = _tokens(rest)
        if kind == "serial":
            scope.units.serial_ranges += ranges
            scope.units.serials |= set(toks)
        else:
            scope.units.lot_ranges += ranges
            scope.units.lots |= set(toks)
    for m in LABEL.finditer(description or ""):
        if m.lastgroup == "ident":
            seg = description[m.end(): m.end() + 120]
            scope.identifiers |= {t for t in _tokens(re.split(r"[.;\n]", seg)[0])[:12] if not UDI.fullmatch(t)}

    if not labels and not scope.units.all_units:
        ranges, rest = _split_ranges(text)
        toks = _tokens(rest)
        shapes = Counter(_shape(t) for t in toks)
        if ranges:
            scope.units.serial_ranges += ranges
        elif len(toks) >= 5 and shapes.most_common(1)[0][1] >= 0.8 * len(toks):
            scope.units.serials |= set(toks)
        else:
            scope.identifiers |= set(toks)

    for m in PREFIX.finditer(text):
        scope.units.serial_prefixes += [p for p in re.split(r"\s*(?:,|\bor\b|\band\b)\s*", m.group(1)) if p and len(p) >= 2]
    if not scope.units.serials:
        for m in SOFTWARE.finditer(both):
            scope.software_include += re.split(r"\s*(?:,|\band\b|\bor\b)\s*", m.group(1))
    for m in EXCEPT.finditer(both):
        scope.software_exclude.append(m.group(1))
        scope.software_include = [s for s in scope.software_include if s != m.group(1)]
    if scope.units.serials or scope.units.lots or scope.units.serial_ranges or scope.units.lot_ranges:
        scope.units.all_units = scope.units.all_units and not (scope.units.serials or scope.units.lots)
    return scope
