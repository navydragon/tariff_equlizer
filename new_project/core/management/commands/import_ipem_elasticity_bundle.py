from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.ipem_economics import (
    import_ipem_coal_2026_model_routes,
    import_ipem_metallurgy_2026_model_routes,
)
from core.models import RouteSet
from scenarios.domain.services.ipem_elasticity_seed import (
    seed_ipem_elasticity_for_scenario,
)
from scenarios.models import Scenario


class Command(BaseCommand):
    help = (
        "Единый импорт IPEM: сначала seed правил эластичности из листа "
        "«Технический лист», затем импорт model-маршрутов из одного или "
        "нескольких XLSX (уголь/металлургия) "
        "и разметка operational-маршрутов по источнику эластичности."
    )

    def add_arguments(self, parser) -> None:
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
            required=True,
            help=(
                "ID сценария: загрузить/обновить набор эластичности и привязать "
                "к сценарию"
            ),
        )
        parser.add_argument(
            "--elasticity-file",
            dest="elasticity_file_path",
            default="../data/ipem/Металлургия_эластика.xlsx",
            help="XLSX с листом «Технический лист» (единый источник кривых)",
        )
        parser.add_argument(
            "--seed-elasticity-only",
            dest="seed_only",
            action="store_true",
            help=(
                "Только загрузить правила эластичности, "
                "не импортировать model-маршруты"
            ),
        )
        parser.add_argument(
            "--file",
            dest="file_paths",
            action="append",
            default=[],
            help=(
                "Путь к XLSX IPEM с model-маршрутами. "
                "Можно указывать несколько раз."
            ),
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Только проверка резолва, без записи в БД",
        )

    def handle(self, *args, **options) -> None:
        prev_disable_warm = bool(getattr(settings, "DISABLE_AUTO_WARM", False))
        settings.DISABLE_AUTO_WARM = True
        try:
            route_set_code: str = options["route_set_code"]
            try:
                route_set = RouteSet.objects.get(code=route_set_code)
            except RouteSet.DoesNotExist as exc:
                raise CommandError(
                    f"RouteSet с code={route_set_code!r} не найден",
                ) from exc

            scenario_id = int(options["scenario_id"])
            try:
                scenario = Scenario.objects.select_related("author").get(id=scenario_id)
            except Scenario.DoesNotExist as exc:
                raise CommandError(f"Сценарий id={scenario_id} не найден") from exc

            elasticity_path = Path(options["elasticity_file_path"])
            if not elasticity_path.is_absolute():
                elasticity_path = Path(settings.BASE_DIR) / elasticity_path
            if not elasticity_path.exists():
                raise CommandError(f"Файл не найден: {elasticity_path}")

            file_paths: list[str] = options.get("file_paths") or []
            seed_only: bool = bool(options.get("seed_only"))
            dry_run: bool = bool(options.get("dry_run"))

            if not seed_only and not file_paths:
                raise CommandError(
                    "Нужно указать хотя бы один --file, "
                    "либо использовать --seed-elasticity-only"
                )

            def progress(message: str) -> None:
                self.stdout.write(message)
                self.stdout.flush()

            with transaction.atomic():
                seed_result = seed_ipem_elasticity_for_scenario(
                    scenario,
                    author=scenario.author,
                    attach=True,
                    xlsx_path=elasticity_path,
                )
                scenario.refresh_from_db(fields=["elasticity_set_id"])

                routes_results = []
                if not seed_only:
                    for raw_path in file_paths:
                        xlsx_path = Path(raw_path)
                        if not xlsx_path.is_absolute():
                            xlsx_path = Path(settings.BASE_DIR) / xlsx_path
                        if not xlsx_path.exists():
                            raise CommandError(f"Файл не найден: {xlsx_path}")

                        name = xlsx_path.name.casefold()
                        if "уголь" in name:
                            routes_results.append(
                                (
                                    "coal",
                                    import_ipem_coal_2026_model_routes(
                                        xlsx_path,
                                        route_set,
                                        dry_run=dry_run,
                                        assign_elasticity_sources=False,
                                        progress=progress,
                                    ),
                                )
                            )
                        elif "металл" in name or "металлург" in name:
                            routes_results.append(
                                (
                                    "metallurgy",
                                    import_ipem_metallurgy_2026_model_routes(
                                        xlsx_path,
                                        route_set,
                                        dry_run=dry_run,
                                        assign_elasticity_sources=False,
                                        progress=progress,
                                    ),
                                )
                            )
                        else:
                            raise CommandError(
                                f"Не удалось определить тип файла по имени "
                                f"{xlsx_path.name!r}. "
                                "Поддерживаются уголь и металлургия."
                            )

                if dry_run:
                    transaction.set_rollback(True)

            attached_suffix = (
                ", привязан к сценарию" if seed_result.attached_to_scenario else ""
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Эластичность: "
                    f"set_id={seed_result.elasticity_set_id}, "
                    f"правил={seed_result.rules_upserted}, "
                    f"точек={seed_result.points_upserted}"
                    f"{attached_suffix}."
                )
            )

            if seed_only:
                self.stdout.write(
                    self.style.SUCCESS("Готово: только seed эластичности."),
                )
                return

            for kind, rr in routes_results:
                for warning in rr.duplicate_link_key_warnings:
                    self.stderr.write(self.style.WARNING(f"[{kind}] {warning}"))
                for reason in rr.skip_reasons:
                    self.stderr.write(self.style.WARNING(f"[{kind}] {reason}"))

                self.stdout.write(
                    self.style.SUCCESS(
                        f"[{kind}] импорт завершён "
                        f"(dry_run={dry_run}, route_set={route_set_code!r})"
                    )
                )
                self.stdout.write(f"[{kind}] строк IPEM: {rr.total_rows}")
                self.stdout.write(
                    f"[{kind}] создано model-маршрутов: {rr.created_model_routes}"
                )
                self.stdout.write(f"[{kind}] пропущено строк: {rr.skipped_rows}")
                if not dry_run:
                    self.stdout.write(
                        f"[{kind}] связано operational-маршрутов: "
                        f"{rr.linked_operational_routes}"
                    )

            if not dry_run:
                from scenarios.domain.services.operational_elasticity import (
                    assign_operational_elasticity_sources,
                )

                stats = assign_operational_elasticity_sources(
                    route_set,
                    progress=progress,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        "Разметка эластичности (итог): "
                        f"direct_model={stats.direct_model}, "
                        f"holding_aggregate={stats.holding_aggregate}, "
                        f"cargo_group_aggregate={stats.cargo_group_aggregate}, "
                        f"skip={stats.skipped}"
                    )
                )
        finally:
            settings.DISABLE_AUTO_WARM = prev_disable_warm
