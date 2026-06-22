from __future__ import annotations

import os
import shutil
import stat
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


def _rmtree_onerror(func, path: str, exc_info) -> None:
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
        func(path)
        return
    raise exc_info[1]


def clear_disk_cache_dir(root: Path) -> None:
    if root.is_dir():
        shutil.rmtree(root, onerror=_rmtree_onerror)
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

        parser.add_argument(
            "--warm-scenarios",
            action="store_true",
            help="После прогрева витрин прогреть KPI-снимки сценариев.",
        )
        parser.add_argument(
            "--skip-mask-prewarm",
            action="store_true",
            help="Не прогревать маски тарифных правил (быстрее; маски построятся при первом расчёте).",
        )

    def handle(self, *args, **options) -> None:
        if options["clear_only"] and options["warm_only"]:
            raise CommandError("Нельзя одновременно указывать --clear-only и --warm-only.")

        if not options["warm_only"]:
            try:
                self._clear_caches()
            except PermissionError as exc:
                service_user = os.environ.get("TARIFF_SERVICE_USER", "tariff")
                raise CommandError(
                    "Не удалось очистить дисковые кеши: нет прав на файлы, "
                    f"созданные пользователем сервиса ({service_user}). "
                    "Запустите команду от этого пользователя, например:\n"
                    f"  sudo -u {service_user} bash -c '"
                    "cd /opt/tariff_equlizer/new_project && "
                    "source .venv/bin/activate && "
                    "export DJANGO_SETTINGS_MODULE=config.settings_prod && "
                    "python manage.py refresh_deploy_caches'"
                ) from exc

        if not options["clear_only"]:
            self._warm_route_marts(
                route_set_id=options["route_set_id"],
                prewarm_masks=not options["skip_mask_prewarm"],
            )
            if options.get("warm_scenarios"):
                self._warm_scenario_snapshots(route_set_id=options["route_set_id"])

    def _clear_caches(self) -> None:
        self.stdout.write("==> Очищаем дисковые кеши и Redis/LocMem")
        roots = clear_all_deploy_caches()
        for root in roots:
            self.stdout.write(f"    {root}")
        self.stdout.write(self.style.SUCCESS("Кеши очищены."))

    def _warm_route_marts(
        self,
        *,
        route_set_id: int | None,
        prewarm_masks: bool,
    ) -> None:
        route_sets = self._route_sets_to_warm(route_set_id=route_set_id)
        if not route_sets:
            self.stdout.write("Нет наборов маршрутов для прогрева.")
            return

        self.stdout.write(f"==> Прогреваем route mart для {len(route_sets)} набор(ов)")
        for route_set in route_sets:
            self._warm_single_route_set(route_set, prewarm_masks=prewarm_masks)

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

    def _warm_single_route_set(
        self,
        route_set: RouteSet,
        *,
        prewarm_masks: bool,
    ) -> None:
        routes_count = Route.objects.filter(route_set_id=route_set.id).count()
        self.stdout.write(
            f"    [{route_set.id}] {route_set.code} — {routes_count} маршрутов…",
        )
        started = time.perf_counter()
        _df, _meta, timings = fetch_routes_dataframe_cached_timed(
            route_set.id,
            prewarm_masks=prewarm_masks,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        cache_hit = bool(timings.get("cache_hit"))
        timing_parts = []
        for label, key in (
            ("sql", "routes_sql_execute_ms"),
            ("copy", "routes_copy_read_ms"),
            ("fetch", "routes_fetch_ms"),
            ("arrow", "routes_arrow_parse_ms"),
            ("df", "dataframe_build_ms"),
            ("normalize", "normalize_ms"),
            ("sidecars", "sidecars_write_ms"),
            ("parquet", "parquet_write_ms"),
            ("masks", "masks_prewarm_ms"),
        ):
            value = timings.get(key)
            if isinstance(value, int):
                timing_parts.append(f"{label}={value} ms")
        masks_count = timings.get("rule_masks_prewarmed")
        if isinstance(masks_count, int) and masks_count:
            timing_parts.append(f"masks_count={masks_count}")
        timing_details = ", ".join(timing_parts)
        mart_path = timings.get("mart_cache_path", "—")
        if cache_hit:
            self.stdout.write(
                f"        cache hit за {elapsed_ms} ms ({timing_details})",
            )
        else:
            self.stdout.write(
                f"        готово за {elapsed_ms} ms ({timing_details})",
            )
        self.stdout.write(f"        {mart_path}")
        from calculations.domain.services.route_mask_cache import (
            mask_cache_dir,
            purge_stale_mask_cache_dirs,
        )

        removed_masks = purge_stale_mask_cache_dirs(
            route_set_id=route_set.id,
            keep_cache_dir=mask_cache_dir(route_set_id=route_set.id),
        )
        if removed_masks:
            self.stdout.write(f"        удалено устаревших mask dirs: {removed_masks}")

    def _warm_scenario_snapshots(self, *, route_set_id: int | None) -> None:
        from calculations.domain.services.scenario_effects_warm import (
            warm_scenario_kpi_snapshot,
        )
        from scenarios.models import Scenario

        qs = Scenario.objects.filter(route_set_id__isnull=False).order_by("id")
        if route_set_id is not None:
            qs = qs.filter(route_set_id=route_set_id)
        scenarios = list(qs)
        if not scenarios:
            self.stdout.write("Нет сценариев для прогрева KPI.")
            return

        self.stdout.write(f"==> Прогреваем KPI-снимки для {len(scenarios)} сценари(ев)")
        for scenario in scenarios:
            self.stdout.write(
                f"    scenario id={scenario.id} «{scenario.name}»…",
            )
            started = time.perf_counter()
            warm_scenario_kpi_snapshot(scenario_id=scenario.id)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.stdout.write(f"        готово за {elapsed_ms} ms")
