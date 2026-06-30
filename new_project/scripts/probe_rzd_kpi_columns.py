"""Сравнение SUM по кандидатам колонок ИХ_ГП с эталоном заказчика."""

from __future__ import annotations

import sqlite3
import sys
import os
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.management.rzd_paths import RZD_TABLE, get_rzd_db_path  # noqa: E402

TARGET = {
    "money_bln_rub": Decimal("2832.7"),
    "volume_mln_t": Decimal("1108.5"),
    "turnover_bln_tkm": Decimal("3061.7"),
}

KEYWORDS = (
    "доход",
    "объем",
    "перевоз",
    "грузооборот",
    "груззоборот",
    "провоз",
    "погруз",
    "2026",
    "руб",
    "тонн",
    "т_км",
    "ткм",
    "цэкр",
)


def _sum_col(conn: sqlite3.Connection, col: str) -> Decimal | None:
    try:
        row = conn.execute(
            f'SELECT SUM(CAST([{col}] AS REAL)) FROM [{RZD_TABLE}]'
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None or row[0] is None:
        return Decimal("0")
    return Decimal(str(row[0]))


def _as_money_bln(raw: Decimal, unit: str) -> Decimal:
    if unit == "rub":
        return raw / Decimal("1000000000")
    if unit == "thousand_rub":
        return raw / Decimal("1000000")
    return raw


def _as_volume_mln(raw: Decimal, unit: str) -> Decimal:
    if unit == "t":
        return raw / Decimal("1000000")
    if unit == "thousand_t":
        return raw / Decimal("1000")
    return raw


def _as_turnover_bln(raw: Decimal, unit: str) -> Decimal:
    if unit == "tkm":
        return raw / Decimal("1000000000")
    if unit == "thousand_tkm":
        return raw / Decimal("1000000")
    return raw


def main() -> None:
    db_path = get_rzd_db_path()
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{RZD_TABLE}")')]
    relevant = [c for c in cols if any(k in c.casefold() for k in KEYWORDS)]

    print(f"DB: {db_path}")
    print(f"Table: {RZD_TABLE}")
    print("Target:", TARGET)
    print()
    print("Relevant columns:")
    for col in relevant:
        print(f"  - {col}")
    print()

    current = {
        "Объем перевозок (т)": ("volume", "t"),
        "Грузооборот (т_км)": ("turnover", "tkm"),
        "Провозная плата (руб)": ("money", "rub"),
    }

    print("=== Current import columns ===")
    for col, (kind, unit) in current.items():
        raw = _sum_col(conn, col)
        if raw is None:
            print(f"{col}: <missing>")
            continue
        if kind == "volume":
            display = _as_volume_mln(raw, unit)
            label = "млн т"
        elif kind == "turnover":
            display = _as_turnover_bln(raw, unit)
            label = "млрд т·км"
        else:
            display = _as_money_bln(raw, unit)
            label = "млрд руб"
        print(f"{col}: raw={raw} -> {display:.2f} {label}")

    print()
    print("=== Year-specific / legacy-style candidates ===")
    candidates: list[tuple[str, str, str]] = []
    for col in relevant:
        cl = col.casefold()
        if "доход" in cl or "провоз" in cl:
            if "тыс" in cl:
                candidates.append((col, "money", "thousand_rub"))
            else:
                candidates.append((col, "money", "rub"))
        elif "объем" in cl or "перевоз" in cl or "погруз" in cl:
            if "тыс" in cl and "т" in cl:
                candidates.append((col, "volume", "thousand_t"))
            else:
                candidates.append((col, "volume", "t"))
        elif "грузооборот" in cl or "груззоборот" in cl or "цэкр" in cl:
            if "тыс" in cl:
                candidates.append((col, "turnover", "thousand_tkm"))
            else:
                candidates.append((col, "turnover", "tkm"))

    for col, kind, unit in candidates:
        raw = _sum_col(conn, col)
        if raw is None:
            continue
        if kind == "volume":
            display = _as_volume_mln(raw, unit)
            target = TARGET["volume_mln_t"]
            label = "млн т"
        elif kind == "turnover":
            display = _as_turnover_bln(raw, unit)
            target = TARGET["turnover_bln_tkm"]
            label = "млрд т·км"
        else:
            display = _as_money_bln(raw, unit)
            target = TARGET["money_bln_rub"]
            label = "млрд руб"
        delta = display - target
        mark = " *** MATCH" if abs(delta) < Decimal("0.15") else ""
        print(f"{col}: {display:.2f} {label} (delta {delta:+.2f}){mark}")

    print()
    print("=== All 2026 / turnover-related columns ===")
    for col in cols:
        if "2026" not in col and "груз" not in col.casefold() and "цэкр" not in col.casefold():
            continue
        raw = _sum_col(conn, col)
        if raw is None or raw == 0:
            continue
        print(f"{col}: raw={raw}")
        print(f"  /1e9 -> {_as_turnover_bln(raw, 'tkm'):.4f} bln tkm")
        print(f"  /1e6 -> {_as_turnover_bln(raw, 'thousand_tkm'):.4f} bln tkm (if col is thousand tkm)")

    conn.close()


if __name__ == "__main__":
    main()
