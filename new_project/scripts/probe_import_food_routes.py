import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

import sqlite3

from core.management.rzd_paths import RZD_TABLE, get_rzd_db_path

conn = sqlite3.connect(get_rzd_db_path())
T = RZD_TABLE

print("=== Виды перевозки (distinct) ===")
for (name,) in conn.execute(f'SELECT DISTINCT [Вид перевозки] FROM [{T}] ORDER BY 1'):
    print(f"  {name!r}")

print("\n=== Строк по видам (импорт / внутр) ===")
for pattern in ("%импорт%", "%Импорт%", "%внутр%", "%Внутр%"):
    cnt = conn.execute(
        f'SELECT COUNT(*) FROM [{T}] WHERE [Вид перевозки] LIKE ?',
        (pattern,),
    ).fetchone()[0]
    print(f"  LIKE {pattern!r}: {cnt:,}")

print("\n=== Топ cargo_code_3 для импортных перевозок ===")
rows = conn.execute(
    f"""
    SELECT [Код груза(3цифры)], COUNT(*) AS cnt
    FROM [{T}]
    WHERE [Вид перевозки] LIKE '%импорт%' OR [Вид перевозки] LIKE '%Импорт%'
    GROUP BY 1
    ORDER BY cnt DESC
    LIMIT 20
    """
).fetchall()
for code, cnt in rows:
    print(f"  {code!r}: {cnt:,}")

print("\n=== Примеры импорт + потребительские (группа/наименование) ===")
rows = conn.execute(
    f"""
    SELECT [Код груза], [Наим груза], [Вид перевозки], [Код груза(3цифры)]
    FROM [{T}]
    WHERE ([Вид перевозки] LIKE '%импорт%' OR [Вид перевозки] LIKE '%Импорт%')
      AND (
        [Группа груза] LIKE '%потреб%'
        OR [Группа груза (ЦМТП)] LIKE '%потреб%'
        OR [Наим груза] LIKE '%ПОТРЕБ%'
      )
    LIMIT 10
    """
).fetchall()
for row in rows:
    print(" ", row)

print("\n=== Примеры внутренние + продовольствие ===")
rows = conn.execute(
    f"""
    SELECT [Код груза], [Наим груза], [Вид перевозки], [Код груза(3цифры)]
    FROM [{T}]
    WHERE [Вид перевозки] LIKE '%внутр%'
      AND (
        [Группа груза] LIKE '%продов%'
        OR [Группа груза (ЦМТП)] LIKE '%продов%'
        OR [Наим груза] LIKE '%МОЛОК%'
        OR [Наим груза] LIKE '%МЯС%'
        OR [Наим груза] LIKE '%ЗЕРН%'
      )
    LIMIT 10
    """
).fetchall()
for row in rows:
    print(" ", row)
