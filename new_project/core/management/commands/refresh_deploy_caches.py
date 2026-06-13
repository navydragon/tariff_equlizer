from __future__ import annotations

import shutil
import time
from pathlib import Path

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from calculations.domain.services.route_effects_loader import (
    fetch_routes_dataframe_cached_timed,
)
from calculations.domain.services.route_mart_store import route_mart_cache_root
from calculations.domain.services.route_mask_cache import route_mask_cache_root
from calculations.domain.services.scenario_compute_store import scenario_compute_cache_root
from core.models import Route, RouteSet


def clear_disk_cache_dir(root: Path) -> None:
    if root.is_dir():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


def clear_all_deploy_caches() -> list[Path]:
    roots = [
        route_mart_cache_root(),
        scenario_compute_cache_root(),
        route_mask_cache_root(),
    ]
    for root in roots:
        clear_disk_cache_dir(root)
    cache.clear()
    return roots


class Command(BaseCommand):
    help = (
        "Очищает все кеши (диск + Redis/LocMem) и прогревает parquet-витрины маршрутов."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--clear-only",
            action="store_true",
            help="Только очистить кеши, без прогрева витрин.",
        )
        parser.add_argument(
            "--warm-only",
            action="store_true",
            help="Только прогреть витрины (без очистки).",
        )
        parser.add_argument(
            "--route-set-id",
            type=int,
            default=None,
            help="Прогреть один набор маршрутов (по умолчанию — все непустые).",
        )

    def handle(self, *args, **options) -> None:
        if options["clear_only"] and options["warm_only"]:
            raise CommandError("Нельзя одновременно указывать --clear-only и --warm-only.")

        if not options["warm_only"]:
            self._clear_caches()

        if not options["clear_only"]:
            self._warm_route_marts(route_set_id=options["route_set_id"])

    def _clear_caches(self) -> None:
        self.stdout.write("==> Очищаем дисковые кеши и Redis/LocMem")
        roots = clear_all_deploy_caches()
        for root in roots:
            self.stdout.write(f"    {root}")
        self.stdout.write(self.style.SUCCESS("Кеши очищены."))

    def _warm_route_marts(self, *, route_set_id: int | None) -> None:
        route_sets = self._route_sets_to_warm(route_set_id=route_set_id)
        if not route_sets:
            self.stdout.write("Нет наборов маршрутов для прогрева.")
            return

        self.stdout.write(f"==> Прогреваем route mart для {len(route_sets)} набор(ов)")
        for route_set in route_sets:
            self._warm_single_route_set(route_set)

    def _route_sets_to_warm(self, *, route_set_id: int | None) -> list[RouteSet]:
        if route_set_id is not None:
            try:
                route_set = RouteSet.objects.get(pk=route_set_id)
            except RouteSet.DoesNotExist as exc:
                raise CommandError(f"RouteSet id={route_set_id} не найден.") from exc
            if Route.objects.filter(route_set_id=route_set.id).count() == 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"RouteSet {route_set.code} (id={route_set.id}) пуст — пропуск.",
                    ),
                )
                return []
            return [route_set]

        result: list[RouteSet] = []
        for route_set in RouteSet.objects.order_by("id"):
            if Route.objects.filter(route_set_id=route_set.id).exists():
                result.append(route_set)
        return result

    def _warm_single_route_set(self, route_set: RouteSet) -> None:
        routes_count = Route.objects.filter(route_set_id=route_set.id).count()
        self.stdout.write(
            f"    [{route_set.id}] {route_set.code} — {routes_count} маршрутов…",
        )
        started = time.perf_counter()
        _df, _meta, timings = fetch_routes_dataframe_cached_timed(route_set.id)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        load_ms = timings.get("routes_sql_execute_ms", 0)
        if isinstance(load_ms, str):
            load_ms = 0
        parquet_write_ms = timings.get("parquet_write_ms", 0)
        if isinstance(parquet_write_ms, str):
            parquet_write_ms = 0
        mart_path = timings.get("mart_cache_path", "—")
        self.stdout.write(
            f"        готово за {elapsed_ms} ms "
            f"(sql={load_ms} ms, parquet_write={parquet_write_ms} ms)",
        )
        self.stdout.write(f"        {mart_path}")
