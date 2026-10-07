import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recalltrace import llm_extract, rules  # noqa: E402
from recalltrace.pipeline import snippets  # noqa: E402

RECORD = {"product_res_number": "Z-TEST", "product_description": "Ventilator Model V1000",
          "code_info": "Serial numbers: VSF100 VSF101 VSF102 and lots L1 through L9"}


def test_parse_reply_skips_fragments():
    good = 'thinking... {"all_units": false, "identifiers": ["V1000"]}'
    assert llm_extract.parse_reply(good)["identifiers"] == ["V1000"]
    assert llm_extract.parse_reply('{"all_units": [1, 2 {"serials": ["A1"]}') is None


def test_invented_values_are_dropped():
    ext = {"identifiers": ["V1000", "V9999"], "unit_scope": {"serials": ["VSF100", "VSF999"]}}
    scope = llm_extract.to_scope(ext, RECORD)
    assert scope.identifiers == {"V1000"}
    assert scope.units.serials == {"VSF100"}


def test_missing_extraction_falls_back_to_rules():
    scope = llm_extract.to_scope(None, RECORD)
    assert scope.source == "rules-fallback"
    assert {"VSF100", "VSF101", "VSF102"} <= scope.units.serials


def test_rules_reads_ranges():
    s = rules.parse("", "Serial Numbers: US00453441 through US00453910")
    assert s.units.serial_ranges == [("US00453441", "US00453910")]


def test_snippets_escape_html():
    out = snippets("<script>x</script> Model V1000 here", ["V1000"])
    assert "<script>" not in out[0] and "<mark>V1000</mark>" in out[0]
