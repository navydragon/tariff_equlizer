from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.ipem_economics import import_ipem_coal_2026_model_routes
from core.models import RouteSet
from scenarios.domain.services.base_elasticity_seed import (
    ELASTICITY_SET_NAME,
    EXPORT_RULE_NAME,
    INTERNAL_RULE_NAME,
)
from scenarios.domain.services.ipem_coal_import import import_ipem_coal_2026_bundle
from scenarios.models import Scenario


class Command(BaseCommand):
    help = (
        "Импорт model-маршрутов из Уголь_эластика_2026.xlsx в RouteSet "
        "и связка operational-маршрутов РЖД через model_route_id. "
        "С --scenario-id также загружает правила эластичности (лист Уголь_коэфф)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--file",
            dest="file_path",
            default="../data/ipem/Уголь_эластика_2026.xlsx",
            help="Путь к XLSX IPEM",
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
                "и привязать набор к сценарию"
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
        xlsx_path = Path(options["file_path"])
        if not xlsx_path.is_absolute():
            xlsx_path = Path(settings.BASE_DIR) / xlsx_path
        if not xlsx_path.exists():
            raise CommandError(f"Файл не найден: {xlsx_path}")

        route_set_code: str = options["route_set_code"]
        try:
            route_set = RouteSet.objects.get(code=route_set_code)
        except RouteSet.DoesNotExist as exc:
            raise CommandError(f"RouteSet с code={route_set_code!r} не найден") from exc

        dry_run: bool = bool(options["dry_run"])
        scenario_id = options.get("scenario_id")
        skip_elasticity: bool = bool(options.get("skip_elasticity"))
        use_bundle = scenario_id is not None and not skip_elasticity

        if scenario_id is not None and skip_elasticity:
            self.stdout.write(
                self.style.WARNING(
                    "--skip-elasticity: импорт только model-маршрутов, "
                    "набор эластичности не затрагивается"
                )
            )

        with transaction.atomic():
            def progress(message: str) -> None:
                self.stdout.write(message)
                self.stdout.flush()

            if use_bundle:
                try:
                    scenario = Scenario.objects.select_related("author").get(
                        id=scenario_id,
                    )
                except Scenario.DoesNotExist as exc:
                    raise CommandError(
                        f"Сценарий id={scenario_id} не найден"
                    ) from exc

                result = import_ipem_coal_2026_bundle(
                    scenario,
                    xlsx_path,
                    route_set,
                    dry_run=dry_run,
                    attach_elasticity=True,
                    progress=progress,
                )
                routes_result = result.routes
                if dry_run:
                    transaction.set_rollback(True)
            else:
                routes_result = import_ipem_coal_2026_model_routes(
                    xlsx_path,
                    route_set,
                    dry_run=dry_run,
                    progress=progress,
                )
                result = None
                if dry_run:
                    transaction.set_rollback(True)

        for warning in routes_result.duplicate_link_key_warnings:
            self.stderr.write(self.style.WARNING(warning))
        for reason in routes_result.skip_reasons:
            self.stderr.write(self.style.WARNING(reason))

        if result is not None and result.seed is not None:
            seed = result.seed
            self.stdout.write(
                self.style.SUCCESS(
                    f'Набор эластичности «{ELASTICITY_SET_NAME}» '
                    f"(id={seed.elasticity_set_id}): "
                    f'«{EXPORT_RULE_NAME}» — {seed.points_export} точек, '
                    f'«{INTERNAL_RULE_NAME}» — {seed.points_internal} точек'
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
            f"Создано model-маршрутов: {routes_result.created_model_routes}"
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
                f"cargo_group_aggregate={routes_result.elasticity_cargo_group_aggregate}, "
                f"skip={routes_result.elasticity_skipped}"
            )
        self.stdout.write(f"Пропущено строк: {routes_result.skipped_rows}")

        if result is not None and not dry_run:
            matching = result.matching
            self.stdout.write(
                f"Матчинг эластичности: «{EXPORT_RULE_NAME}» — "
                f"{matching.export_matched}, "
                f"«{INTERNAL_RULE_NAME}» — {matching.internal_matched}"
            )
            for route_code in matching.unmatched_route_codes:
                self.stderr.write(
                    self.style.WARNING(
                        f"Маршрут {route_code}: правило эластичности не найдено"
                    )
                )
