"""Сравнение total_ipem.csv с маршрутами RouteSet RZD_2026 в БД."""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from core.models import Route, RouteSet  # noqa: E402

OUT_PATH = BASE_DIR / "scripts" / "ipem_rzd_overlap.csv"


def main() -> None:
    csv_path = BASE_DIR / "total_ipem.csv"
    ipem_rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            origin = (row.get("Код ЕСР станции отправления") or "").strip().replace(" ", "")
            dest = (row.get("Код ЕСР станции назначения") or "").strip().replace(" ", "")
            ipem_rows.append(
                {
                    "index": row.get("index"),
                    "key": (row.get("КЛЮЧ_КОД_МАРШРУТА") or "").strip(),
                    "origin": origin,
                    "dest": dest,
                    "cargo_name": (row.get("Груз") or "").strip(),
                    "message_type": (row.get("Вид сообщения") or "").strip(),
                }
            )

    route_set = RouteSet.objects.filter(code="RZD_2026").first()
    if route_set is None:
        codes = list(RouteSet.objects.values_list("code", flat=True)[:30])
        print("RouteSet RZD_2026 не найден. Доступные коды:", codes)
        return

    base_qs = Route.objects.filter(route_set=route_set)
    rzd_total = base_qs.count()
    ipem_keys = {r["key"] for r in ipem_rows if r["key"]}
    direct_codes = set(
        base_qs.filter(route_code__in=ipem_keys).values_list("route_code", flat=True)
    )

    unique_pairs: dict[tuple[int, int], int] = {}
    for r in ipem_rows:
        if not (r["origin"].isdigit() and r["dest"].isdigit()):
            continue
        pair = (int(r["origin"]), int(r["dest"]))
        if pair not in unique_pairs:
            cnt = base_qs.filter(
                origin_station__esr_code=pair[0],
                destination_station__esr_code=pair[1],
            ).count()
            unique_pairs[pair] = cnt

    matched_rows: list[dict] = []
    unmatched_rows: list[dict] = []
    for r in ipem_rows:
        in_rzd = False
        rzd_count = 0
        if r["origin"].isdigit() and r["dest"].isdigit():
            pair = (int(r["origin"]), int(r["dest"]))
            rzd_count = unique_pairs.get(pair, 0)
            in_rzd = rzd_count > 0
        row_out = {**r, "in_rzd": in_rzd, "rzd_routes_count": rzd_count}
        (matched_rows if in_rzd else unmatched_rows).append(row_out)

    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "index",
                "key",
                "origin",
                "dest",
                "cargo_name",
                "message_type",
                "in_rzd",
                "rzd_routes_count",
            ],
            delimiter=";",
        )
        w.writeheader()
        w.writerows(matched_rows + unmatched_rows)

    matched_pairs = sum(1 for v in unique_pairs.values() if v > 0)

    print("=== IPEM vs RZD_2026 ===")
    print(f"Маршрутов в RZD_2026: {rzd_total:,}")
    print(f"Строк в total_ipem.csv: {len(ipem_rows)}")
    print(f"Уникальных пар ЕСР: {len(unique_pairs)}")
    print()
    print("Критерий совпадения: та же пара станций (ЕСР отпр. - ЕСР назн.)")
    print("  есть хотя бы один маршрут в RZD_2026")
    print(f"  уникальных пар IPEM найдено в РЖД: {matched_pairs} / {len(unique_pairs)}")
    print(f"  строк IPEM с совпадением: {len(matched_rows)} / {len(ipem_rows)}")
    print(f"  строк IPEM без совпадения: {len(unmatched_rows)}")
    print()
    print(
        f"Совпадение route_code (КЛЮЧ_КОД_МАРШРУТА = route_code в РЖД): "
        f"{len(direct_codes)} — ожидаемо 0, у РЖД route_code = index из SQLite"
    )
    print()
    print(f"Детальный отчёт: {OUT_PATH}")
    if unmatched_rows:
        print("\nПримеры без совпадения в РЖД:")
        for r in unmatched_rows[:10]:
            print(f"  {r['index']}: {r['key']} — {r['cargo_name'][:45]}")


if __name__ == "__main__":
    main()
