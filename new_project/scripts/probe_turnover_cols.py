import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
import django
import sqlite3
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.management.rzd_paths import RZD_TABLE, get_rzd_db_path

conn = sqlite3.connect(get_rzd_db_path())
cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{RZD_TABLE}")')]
target = Decimal("3061.7")

for col in cols:
    cl = col.casefold()
    if not any(x in cl for x in ("грузоб", "цэкр", "груззоб", "epl", "оборот")):
        continue
    raw = conn.execute(f'SELECT SUM(CAST([{col}] AS REAL)) FROM [{RZD_TABLE}]').fetchone()[0]
    if raw is None:
        continue
    d = Decimal(str(raw))
    for div, label in [(Decimal("1e9"), "tkm->bln"), (Decimal("1e6"), "thousand_tkm->bln"), (Decimal("1e3"), "mln_tkm->bln")]:
        val = d / div
        delta = val - target
        mark = " ***" if abs(delta) < Decimal("0.15") else ""
        print(f"{col!r}: /{div} = {val:.4f}{mark}")
