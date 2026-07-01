"""Разбивка причин пропуска строк при import_rzd_routes (без записи в БД)."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.domain.cargo.formatting import format_etsng_code  # noqa: E402
from core.management.rzd_paths import RZD_TABLE, get_rzd_db_path  # noqa: E402
from core.models import Cargo, Station  # noqa: E402

COL_INDEX = "index"
COL_CARGO_CODE = "Код груза"
COL_ORIGIN_ESR = "Код станц отпр РФ"
COL_DEST_ESR = "Код станц назн РФ"
COL_WAGON_KIND = "Род вагона"
COL_SHIPMENT_TYPE = "Категория отпр"


def _parse_int(value) -> int | None:
    if value is None:
        return None
    raw = str(value).strip().replace(" ", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _normalize_name(value: str) -> str:
    return (value or "").strip().casefold()


def main() -> None:
    db_path = get_rzd_db_path()
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        return

    cargo_codes = set(Cargo.objects.values_list("code", flat=True))
    station_esrs = set(Station.objects.values_list("esr_code", flat=True))

    conn = sqlite3.connect(db_path)
    sql = f"""
        SELECT
            [{COL_INDEX}],
            [{COL_CARGO_CODE}],
            [{COL_ORIGIN_ESR}],
            [{COL_DEST_ESR}],
            [{COL_WAGON_KIND}],
            [{COL_SHIPMENT_TYPE}]
        FROM [{RZD_TABLE}]
    """

    reasons: dict[str, int] = {}
    total = 0

    def bump(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    for row in conn.execute(sql):
        total += 1
        index_value, cargo_raw, origin_raw, dest_raw, wagon_raw, shipment_raw = row

        route_code = str(index_value).strip() if index_value is not None else ""
        if not route_code:
            bump("empty_index")
            continue

        cargo_code = format_etsng_code(cargo_raw)
        if not cargo_code:
            bump("invalid_cargo_code")
            continue
        if cargo_code not in cargo_codes:
            bump("cargo_not_found")
            continue

        origin_esr = _parse_int(origin_raw)
        dest_esr = _parse_int(dest_raw)
        if origin_esr is None or dest_esr is None:
            bump("invalid_station_esr")
            continue
        if origin_esr not in station_esrs or dest_esr not in station_esrs:
            bump("station_not_found")
            continue

        if not _normalize_name(wagon_raw):
            bump("missing_name")
            continue
        if not _normalize_name(shipment_raw):
            bump("missing_name")
            continue

    conn.close()

    skipped = sum(reasons.values())
    print(f"DB: {db_path}")
    print(f"Справочники: грузов {len(cargo_codes):,}, станций {len(station_esrs):,}")
    print(f"Строк в {RZD_TABLE}: {total:,}")
    print(f"Будет пропущено: {skipped:,} ({skipped / total * 100:.2f}%)")
    print(f"Будет импортировано: {total - skipped:,}")
    print()
    print("Причины (в порядке проверки импорта):")
    for reason, count in sorted(reasons.items(), key=lambda item: -item[1]):
        print(f"  {reason}: {count:,} ({count / total * 100:.2f}%)")


if __name__ == "__main__":
    main()
