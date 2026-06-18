"""Проверка соответствия строк Уголь_эластика_2026.xlsx маршрутам RouteSet RZD_2026."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.management.ipem_economics import (  # noqa: E402
    build_ipem_coal_2026_overlap,
    write_overlap_csv,
)
from core.models import Route, RouteSet  # noqa: E402

DEFAULT_FILE = BASE_DIR.parent / "data" / "ipem" / "Уголь_эластика_2026.xlsx"
DEFAULT_OUTPUT = BASE_DIR / "scripts" / "ipem_coal_2026_rzd_overlap.csv"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сопоставление строк IPEM (Уголь_эластика_2026) с маршрутами RZD_2026",
    )
    parser.add_argument(
        "--file",
        dest="file_path",
        default=str(DEFAULT_FILE),
        help="Путь к XLSX IPEM",
    )
    parser.add_argument(
        "--route-set-code",
        dest="route_set_code",
        default="RZD_2026",
        help="Код RouteSet с маршрутами РЖД",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        default=str(DEFAULT_OUTPUT),
        help="Путь к выходному CSV-отчёту",
    )
    return parser.parse_args()


def _diagnose_zero_match(row) -> str:
    if row.resolve_status != "ok":
        return f"резолв: {row.resolve_status}"
    if row.rzd_match_count_broad == 0:
        return "нет маршрутов РЖД по тройке станции+груз"
    return (
        "есть маршруты по тройке "
        f"({row.rzd_match_count_broad}), но нет по строгому ключу "
        f"(вагон={row.wagon_kind_name or '?'}, вид={row.message_type_name or '?'})"
    )


def main() -> None:
    args = _parse_args()
    xlsx_path = Path(args.file_path)
    if not xlsx_path.is_absolute():
        xlsx_path = BASE_DIR / xlsx_path
    if not xlsx_path.exists():
        print(f"Файл не найден: {xlsx_path}")
        sys.exit(1)

    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path

    route_set = RouteSet.objects.filter(code=args.route_set_code).first()
    if route_set is None:
        codes = list(RouteSet.objects.values_list("code", flat=True)[:30])
        print(f"RouteSet {args.route_set_code!r} не найден. Доступные коды: {codes}")
        sys.exit(1)

    overlap_rows = build_ipem_coal_2026_overlap(xlsx_path, route_set)
    write_overlap_csv(output_path, overlap_rows)

    rzd_total = Route.objects.filter(route_set=route_set).count()
    total = len(overlap_rows)
    matched_strict = [r for r in overlap_rows if r.rzd_match_count > 0]
    zero_strict = [r for r in overlap_rows if r.rzd_match_count == 0]
    counts = [r.rzd_match_count for r in overlap_rows if r.rzd_match_count > 0]

    print("=== IPEM Уголь_эластика_2026 vs RZD_2026 ===")
    print(f"Маршрутов в {args.route_set_code}: {rzd_total:,}")
    print(f"Строк в IPEM: {total}")
    print()
    print(
        "Строгий ключ: ЕСР отпр. + ЕСР назн. + груз + род вагона + вид перевозки"
    )
    print(f"  строк IPEM с совпадением: {len(matched_strict)} / {total}")
    print(f"  строк IPEM без совпадения: {len(zero_strict)}")
    if counts:
        print(
            f"  rzd_match_count: min={min(counts)}, max={max(counts)}, "
            f"avg={sum(counts) / len(counts):.1f}"
        )
    print()
    print(f"Детальный отчёт: {output_path}")

    if zero_strict:
        print("\nСтроки без строгого совпадения:")
        for row in zero_strict:
            print(
                f"  #{row.ipem_row}: {row.origin_station_name} -> {row.dest_station_name}, "
                f"{row.cargo_name} ({row.cargo_code_raw}) - {_diagnose_zero_match(row)}"
            )


if __name__ == "__main__":
    main()
