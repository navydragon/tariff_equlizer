"""Аудит покрытия is_consumer_goods по маршрутам RZD_2026."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db.models import Count

from core.domain.cargo.etsng_categories import (
    CONSUMER_GOODS_POSITIONS,
    classify_cargo_flags,
)
from core.domain.cargo.formatting import format_etsng_code
from core.models import Cargo, CargoGroup, Route, RouteSet

EXAMPLE_CODE = "042201"


def main() -> None:
    print("=== classify_cargo_flags ===")
    print(f"{EXAMPLE_CODE}: {classify_cargo_flags(EXAMPLE_CODE)}")
    print(f"position 042 in CONSUMER: {'042' in CONSUMER_GOODS_POSITIONS}")

    rs = RouteSet.objects.filter(code="RZD_2026").first()
    if not rs:
        print("RZD_2026 not found")
        return

    qs = Route.objects.filter(route_set=rs, is_model=False)
    total = qs.count()
    consumer = qs.filter(cargo__is_consumer_goods=True).count()
    print(f"\n=== RZD operational ===")
    print(f"total: {total:,}")
    print(f"is_consumer_goods=True: {consumer:,} ({consumer / total * 100:.2f}%)")

    formatted = format_etsng_code(EXAMPLE_CODE)
    cargo = Cargo.objects.filter(code=formatted).first()
    if cargo:
        routes = qs.filter(cargo=cargo).count()
        print(f"\n=== {formatted} {cargo.name} ===")
        print(f"is_consumer_goods={cargo.is_consumer_goods}, group={cargo.cargo_group}")
        print(f"routes with this cargo: {routes:,}")
    else:
        print(f"\nCargo {formatted} not in DB")

    print("\n=== By cargo group (consumer flagged routes) ===")
    for row in (
        qs.filter(cargo__is_consumer_goods=True)
        .values("cargo__cargo_group__name")
        .annotate(n=Count("id"))
        .order_by("-n")[:12]
    ):
        name = row["cargo__cargo_group__name"] or "—"
        print(f"  {name}: {row['n']:,}")

    own_axles = CargoGroup.objects.filter(name__icontains="своих осях").first()
    if own_axles:
        own_qs = qs.filter(cargo__cargo_group=own_axles)
        print(f"\n=== Группа «{own_axles.name}» ===")
        print(f"routes: {own_qs.count():,}")
        print(
            f"consumer flagged: {own_qs.filter(cargo__is_consumer_goods=True).count():,}"
        )
        print(
            f"position 042 routes in group: "
            f"{own_qs.filter(cargo__code__startswith='042').count():,}"
        )

    print("\n=== Top positions (cargo_code_3) among consumer routes ===")
    for row in (
        qs.filter(cargo__is_consumer_goods=True)
        .values("cargo_code_3")
        .annotate(n=Count("id"))
        .order_by("-n")[:15]
    ):
        print(f"  {row['cargo_code_3']}: {row['n']:,}")

    print(f"\nCONSUMER positions count: {len(CONSUMER_GOODS_POSITIONS)}")


if __name__ == "__main__":
    main()
