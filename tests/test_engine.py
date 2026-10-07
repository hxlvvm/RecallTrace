import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recalltrace.pipeline import MISMATCH, MISSING, NEED_MODEL, NONE_FOUND, REVIEW, Engine  # noqa: E402

ENGINE = Engine(ROOT)


def status(**row):
    return ENGINE.review_row(0, row).status


def test_demo_outcomes():
    rows = {r["asset_tag"]: r for r in csv.DictReader(open(ROOT / "data/demo/clinic_inventory.csv"))}
    got = {k: ENGINE.review_row(0, r).status for k, r in rows.items()}
    assert got["RT-0005"] == REVIEW          # serial listed in the recall
    assert got["RT-0006"] == MISSING         # lot-limited recall, no lot recorded
    assert got["RT-0008"] == NEED_MODEL      # no model number
    assert got["RT-0011"] == NONE_FOUND      # not in the snapshot
    assert got["RT-0016"] == MISMATCH        # serial not on the list


def test_editing_serial_changes_verdict():
    base = dict(manufacturer="Masimo", device="Rad-G", ref="9847")
    assert status(**base, serial="6000062125") == REVIEW
    assert status(**base, serial="6000062118") == MISMATCH
    assert status(**base) == MISSING
