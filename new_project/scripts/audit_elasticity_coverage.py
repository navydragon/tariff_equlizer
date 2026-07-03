"""Аудит разметки эластичности по operational-маршрутам набора."""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db.models import Count, Q

from core.models import CargoGroup, Route, RouteSet


def _pct(part: int, total: int) -> str:
    if total <= 0:
        return "0.00%"
    return f"{part * 100.0 / total:.2f}%"


def _print_route_set_summary(route_set: RouteSet) -> None:
    qs = Route.objects.filter(route_set=route_set, is_model=False)
    with_charge = qs.filter(freight_charge_rub__gt=0)
    total = with_charge.count()
    if total == 0:
        print(f"\n=== {route_set.code} — нет operational с charge > 0 ===")
        return

    skipped = with_charge.filter(skip_elasticity=True).count()
    active = with_charge.filter(skip_elasticity=False)
    active_count = active.count()

    print(f"\n=== {route_set.code} — {route_set.name} ===")
    print(f"operational с charge>0: {total:,}")
    print(f"skip_elasticity=True:    {skipped:,} ({_pct(skipped, total)})")
    print(f"skip_elasticity=False:   {active_count:,} ({_pct(active_count, total)})")

    print("\n--- elasticity_source (charge>0) ---")
    for row in (
        with_charge.values("elasticity_source")
        .annotate(n=Count("id"))
        .order_by("-n")
    ):
        source = row["elasticity_source"] or "—"
        print(f"  {source}: {row['n']:,} ({_pct(row['n'], total)})")

    static_eligible = with_charge.filter(
        skip_elasticity=False,
        transport_volume_tons__gt=0,
    ).exclude(elasticity_source=Route.ElasticitySource.NONE)
    static_count = static_eligible.count()
    print(
        f"\nstatic_eligible (~skip=False, volume>0, source!=none): "
        f"{static_count:,} ({_pct(static_count, total)})"
    )

    print("\n--- static_eligible по source ---")
    for row in (
        static_eligible.values("elasticity_source")
        .annotate(n=Count("id"))
        .order_by("-n")
    ):
        source = row["elasticity_source"] or "—"
        print(f"  {source}: {row['n']:,} ({_pct(row['n'], static_count)})")

    own_axles = CargoGroup.objects.filter(
        Q(name__icontains="своих осях") | Q(code=11),
    ).first()
    if own_axles:
        own_qs = with_charge.filter(cargo__cargo_group=own_axles)
        own_total = own_qs.count()
        own_skipped = own_qs.filter(skip_elasticity=True).count()
        own_active = own_qs.filter(skip_elasticity=False).count()
        print(f"\n--- «{own_axles.name}» (code={own_axles.code}) ---")
        print(f"  routes: {own_total:,}")
        print(f"  skip_elasticity=True:  {own_skipped:,} ({_pct(own_skipped, own_total)})")
        print(f"  skip_elasticity=False: {own_active:,} ({_pct(own_active, own_total)})")
        for row in (
            own_qs.values("elasticity_source")
            .annotate(n=Count("id"))
            .order_by("-n")
        ):
            source = row["elasticity_source"] or "—"
            print(f"    source {source}: {row['n']:,}")

    model_count = Route.objects.filter(
        route_set=route_set,
        is_model=True,
    ).count()
    print(f"\nmodel-маршрутов (пул экономики): {model_count:,}")

    loop_overhead = total - static_count
    print(
        f"\nОценка выигрыша от eligible-итерации (без initial>0): "
        f"пропуск ~{loop_overhead:,} итераций ({_pct(loop_overhead, total)})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Аудит skip_elasticity / elasticity_source по маршрутам",
    )
    parser.add_argument(
        "--route-set",
        default="RZD_2026",
        help="Код RouteSet (по умолчанию RZD_2026)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Показать все наборы маршрутов",
    )
    args = parser.parse_args()

    if args.all:
        route_sets = RouteSet.objects.order_by("code")
    else:
        route_sets = RouteSet.objects.filter(code=args.route_set)
        if not route_sets.exists():
            print(f"RouteSet {args.route_set!r} не найден")
            return

    for route_set in route_sets:
        _print_route_set_summary(route_set)


if __name__ == "__main__":
    main()
