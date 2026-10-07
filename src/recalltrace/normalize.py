"""Identifier normalisation shared by the parsers and the matcher."""
from __future__ import annotations

import re

_ALNUM = re.compile(r"[^0-9A-Z]")


def norm_id(value: str | None) -> str:
    """Upper-case and drop punctuation and spaces, so '66 40 440' and '6640440' compare equal."""
    return _ALNUM.sub("", (value or "").upper())


def looks_like_code(value: str | None) -> bool:
    """True for catalogue-style identifiers (has a digit, no spaces), False for names like 'Trilogy 100'."""
    v = (value or "").strip()
    return bool(v) and " " not in v and any(c.isdigit() for c in v) and len(norm_id(v)) >= 4


def split_numeric(token: str) -> tuple[str, int, int] | None:
    """Split 'US00453441' into ('US', 453441, width) when the token ends in digits."""
    m = re.fullmatch(r"(.*?)(\d+)", norm_id(token))
    if not m:
        return None
    return m.group(1), int(m.group(2)), len(m.group(2))


def in_range(token: str, start: str, end: str) -> bool | None:
    """Range membership for same-shaped identifiers; None when the shapes are not comparable."""
    t, a, b = split_numeric(token), split_numeric(start), split_numeric(end)
    if not (t and a and b):
        return None
    if a[0] != b[0] or a[2] != b[2]:
        return None
    if t[0] != a[0] or t[2] != a[2]:
        return False
    return a[1] <= t[1] <= b[1]


def udi_key(value: str | None) -> str:
    """GTIN of a UDI-DI with any (01) application identifier and trailing production data removed."""
    v = (value or "").strip()
    m = re.search(r"\(01\)\s*(\d{12,14})", v)
    digits = m.group(1) if m else re.sub(r"\D", "", v)
    if len(digits) == 16 and digits.startswith("01"):
        digits = digits[2:]
    return digits[:14].zfill(14) if digits else ""
