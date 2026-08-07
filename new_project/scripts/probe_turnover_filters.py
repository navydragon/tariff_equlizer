import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import sqlite3
from decimal import Decimal
from core.management.rzd_paths import RZD_TABLE, get_rzd_db_path

conn = sqlite3.connect(get_rzd_db_path())
T = RZD_TABLE
target = Decimal("3061.7")

queries = {
    "2026 Грузоб,ткм all": f'SELECT SUM(CAST([2026 Грузоб,ткм] AS REAL)) FROM [{T}]',
    "Грузооборот (т_км) all": f'SELECT SUM(CAST([Грузооборот (т_км)] AS REAL)) FROM [{T}]',
    "2026 Грузоб,ткм груженые": f"""SELECT SUM(CAST([2026 Грузоб,ткм] AS REAL)) FROM [{T}]
        WHERE [Тип парка] LIKE '%груж%'""",
    "Грузооборот груженые": f"""SELECT SUM(CAST([Грузооборот (т_км)] AS REAL)) FROM [{T}]
        WHERE [Тип парка] LIKE '%груж%'""",
    "2026 Грузоб,ткм not empty": f"""SELECT SUM(CAST([2026 Грузоб,ткм] AS REAL)) FROM [{T}]
        WHERE [2026 Грузоб,ткм] IS NOT NULL AND [2026 Грузоб,ткм] != 0""",
}

for label, sql in queries.items():
    raw = conn.execute(sql).fetchone()[0] or 0
    bln = Decimal(str(raw)) / Decimal("1000000000")
    print(f"{label}: {bln:.4f} bln (delta {bln-target:+.4f})")
