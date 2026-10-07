"""Print the review queue for the bundled demo inventory."""
import csv
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from recalltrace.pipeline import Engine  # noqa: E402

t0 = time.time()
eng = Engine(ROOT)
t1 = time.time()
rows = list(csv.DictReader(open(ROOT / "data/demo/clinic_inventory.csv")))
for f in eng.review(rows):
    r = rows[f.row]
    others = [(o["record"], o["verdict"]) for o in f.others[:3]]
    print(f'{r["asset_tag"]} {r["manufacturer"]} {r["device"]} | {f.status} | {f.record} | {f.identity} | {f.scope} | others={others}')
t2 = time.time()
eng.review(rows)
print(f"load {t1 - t0:.1f}s, first review {t2 - t1:.1f}s, cached review {time.time() - t2:.1f}s")
