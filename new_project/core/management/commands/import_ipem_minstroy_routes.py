from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.ipem_economics import import_ipem_minstroy_model_routes
from core.models import RouteSet
from scenarios.domain.services.ipem_minstroy_import import (
    import_ipem_minstroy_bundle,
)
from scenarios.models import Scenario


class Command(BaseCommand):
    help = (
        "Импорт model-маршрутов Минстроя из Минстрой_эластика.xlsx в "
        "RouteSet и связка operational-маршрутов РЖД через model_route_id. "
        "С --scenario-id также загружает правила эластичности (лист "
        "«Технический лист», cargo_group=7) и выводит статистику матчинга."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--file",
            dest="file_path",
            default="../data/ipem/Минстрой_эластика.xlsx",
            help="Путь к XLSX IPEM (минерально-строит.)",
        )
        parser.add_argument(
            "--route-set-code",
            dest="route_set_code",
            default="RZD_2026",
            help="Код RouteSet с маршрутами РЖД",
        )
        parser.add_argument(
            "--scenario-id",
            dest="scenario_id",
            type=int,
            help=(
                "ID сценария: загрузить правила эластичности из того же XLSX "
                "и привязать набор к сценарию (если ещё не привязан)"
            ),
        )
        parser.add_argument(
            "--skip-elasticity",
            dest="skip_elasticity",
            action="store_true",
            help="Не загружать правила эластичности даже при --scenario-id",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Только проверка резолва, без записи в БД",
        )

    def handle(self, *args, **options) -> None:
        xlsx_path = self._resolve_xlsx(options["file_path"])
        route_set_code: str = options["route_set_code"]
        route_set = self._resolve_route_set(route_set_code)

        dry_run: bool = bool(options["dry_run"])
        scenario_id = options.get("scenario_id")
        skip_elasticity: bool = bool(options.get("skip_elasticity"))
        use_bundle = scenario_id is not None and not skip_elasticity
        if scenario_id is not None and skip_elasticity:
            self._warn_skip_elasticity()

        routes_result, result = self._run_import(
            xlsx_path=xlsx_path,
            route_set=route_set,
            scenario_id=scenario_id,
            dry_run=dry_run,
            use_bundle=use_bundle,
        )

        self._print_warnings(routes_result)
        self._print_summary(
            routes_result=routes_result,
            result=result,
            route_set_code=route_set_code,
            dry_run=dry_run,
            use_bundle=use_bundle,
        )

    def _resolve_xlsx(self, raw_path: str) -> Path:
        xlsx_path = Path(raw_path)
        if not xlsx_path.is_absolute():
            xlsx_path = Path(settings.BASE_DIR) / xlsx_path
        if not xlsx_path.exists():
            raise CommandError(f"Файл не найден: {xlsx_path}")
        return xlsx_path

    def _resolve_route_set(self, route_set_code: str) -> RouteSet:
        try:
            return RouteSet.objects.get(code=route_set_code)
        except RouteSet.DoesNotExist as exc:
            raise CommandError(
                f"RouteSet с code={route_set_code!r} не найден",
            ) from exc

    def _warn_skip_elasticity(self) -> None:
        self.stdout.write(
            self.style.WARNING(
                "--skip-elasticity: импорт только model-маршрутов, "
                "набор эластичности не затрагивается",
            ),
        )

    def _progress(self, message: str) -> None:
        self.stdout.write(message)
        self.stdout.flush()

    def _resolve_scenario(self, scenario_id: int) -> Scenario:
        try:
            return Scenario.objects.select_related("author").get(
                id=scenario_id,
            )
        except Scenario.DoesNotExist as exc:
            raise CommandError(
                f"Сценарий id={scenario_id} не найден",
            ) from exc

    def _run_import(
        self,
        *,
        xlsx_path: Path,
        route_set: RouteSet,
        scenario_id: int | None,
        dry_run: bool,
        use_bundle: bool,
    ):
        with transaction.atomic():
            if use_bundle:
                assert scenario_id is not None
                scenario = self._resolve_scenario(int(scenario_id))
                result = import_ipem_minstroy_bundle(
                    scenario,
                    xlsx_path,
                    route_set,
                    dry_run=dry_run,
                    attach_elasticity=True,
                    progress=self._progress,
                )
                routes_result = result.routes
            else:
                routes_result = import_ipem_minstroy_model_routes(
                    xlsx_path,
                    route_set,
                    dry_run=dry_run,
                    progress=self._progress,
                )
                result = None

            if dry_run:
                transaction.set_rollback(True)

        return routes_result, result

    def _print_warnings(self, routes_result) -> None:
        for warning in routes_result.duplicate_link_key_warnings:
            self.stderr.write(self.style.WARNING(warning))
        for reason in routes_result.skip_reasons:
            self.stderr.write(self.style.WARNING(reason))

    def _print_summary(
        self,
        *,
        routes_result,
        result,
        route_set_code: str,
        dry_run: bool,
        use_bundle: bool,
    ) -> None:
        if result is not None and result.seed is not None:
            seed = result.seed
            self.stdout.write(
                self.style.SUCCESS(
                    "Эластичность (минстрой): "
                    f"set_id={seed.elasticity_set_id}, "
                    f"правил={seed.rules_upserted}, "
                    f"точек={seed.points_upserted}"
                    f"{', привязан к сценарию' if seed.attached_to_scenario else ''}."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Импорт model-маршрутов завершён (dry_run={dry_run}, "
                f"route_set={route_set_code!r}"
                f"{', bundle' if use_bundle else ''})"
            )
        )
        self.stdout.write(f"Строк IPEM: {routes_result.total_rows}")
        self.stdout.write(
            f"Создано model-маршрутов: {routes_result.created_model_routes}",
        )
        if not dry_run:
            self.stdout.write(
                f"Связано operational-маршрутов: "
                f"{routes_result.linked_operational_routes}"
            )
            self.stdout.write(
                "Разметка эластичности (итого): "
                f"direct_model={routes_result.elasticity_direct_model}, "
                f"holding_aggregate={routes_result.elasticity_holding_aggregate}, "
                f"cargo_group_aggregate="
                f"{routes_result.elasticity_cargo_group_aggregate}, "
                f"skip={routes_result.elasticity_skipped}"
            )
        self.stdout.write(f"Пропущено строк: {routes_result.skipped_rows}")

        if result is not None and not dry_run:
            matching = result.matching
            self.stdout.write(
                f"Матчинг эластичности: matched — {matching.matched}, "
                f"unmatched — {len(matching.unmatched_route_codes)}"
            )
            for route_code in matching.unmatched_route_codes:
                self.stderr.write(
                    self.style.WARNING(
                        f"Маршрут {route_code}: правило эластичности не найдено"
                    )
                )

