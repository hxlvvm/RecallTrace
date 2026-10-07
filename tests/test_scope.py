import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recalltrace.normalize import in_range, norm_id, udi_key  # noqa: E402
from recalltrace.scope import AFFECTED, NOT_AFFECTED, UNRESOLVED, Scope, UnitScope, check  # noqa: E402


def test_norm_and_udi():
    assert norm_id("66 40 440") == norm_id("6640440")
    assert udi_key("(01)00884838028890(21)") == "00884838028890"
    assert udi_key("606959052000") == "00606959052000"


def test_range_needs_same_shape():
    assert in_range("US00453500", "US00453441", "US00453910") is True
    assert in_range("US00453911", "US00453441", "US00453910") is False
    assert in_range("ABC1", "US00453441", "US00453910") is False
    assert in_range("12", "AB1", "CD9") is None


def test_listed_serial_range_and_missing_serial():
    s = Scope(identifiers={"M4735A"}, units=UnitScope(serials={"X100"}, serial_ranges=[("US00453441", "US00453910")]))
    assert check(s, {"model": "M4735A", "serial": "X100"}).status == AFFECTED
    assert check(s, {"model": "M4735A", "serial": "US00453500"}).status == AFFECTED
    assert check(s, {"model": "M4735A", "serial": "US00453999"}).status == NOT_AFFECTED
    assert check(s, {"model": "M4735A"}).status == UNRESOLVED


def test_model_mismatch_and_all_units():
    s = Scope(identifiers={"M3536A"}, units=UnitScope(all_units=True))
    assert check(s, {"model": "M3536A"}, "Model/ID # M3536A").status == AFFECTED
    assert check(s, {"model": "M3535A"}, "Model/ID # M3536A").status == NOT_AFFECTED


def test_per_identifier_ranges_do_not_mix():
    s = Scope(identifiers={"11971", "11973"}, per_identifier={
        "11971": UnitScope(serial_ranges=[("0013120799", "0099072300")]),
        "11973": UnitScope(serial_ranges=[("0012570058", "0012573663")])})
    assert check(s, {"model": "11971", "serial": "0013125000"}).status == AFFECTED
    assert check(s, {"model": "11973", "serial": "0013125000"}).status == NOT_AFFECTED


def test_software_rules():
    s = Scope(identifiers={"VT2110X24B"}, units=UnitScope(all_units=True), software_exclude=["1.05.06.00"])
    assert check(s, {"model": "VT2110X24B", "software": "1.05.06.00"}).status == NOT_AFFECTED
    w = Scope(units=UnitScope(all_units=True), software_include=["4.XX", "6.XX"])
    assert check(w, {"software": "6.12"}).status == AFFECTED
    assert check(w, {"software": "8.00"}).status == NOT_AFFECTED
    assert check(w, {}).status == UNRESOLVED


def test_date_rule():
    s = Scope(units=UnitScope(serial_date_rule={"start": 2, "length": 2, "min": 13, "max": 19}))
    assert check(s, {"serial": "22151234567"}).status == AFFECTED
    assert check(s, {"serial": "22211234567"}).status == NOT_AFFECTED
