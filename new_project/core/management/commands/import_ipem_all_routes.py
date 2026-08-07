"""Последовательный импорт всех IPEM-секторов в RouteSet."""

from __future__ import annotations

from collections.abc import Sequence

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

# Порядок как в PRODUCTION.md / FIRST_IMPORT.md.
DEFAULT_IPEM_IMPORT_COMMANDS: tuple[str, ...] = (
    "import_ipem_coal_2026_routes",
    "import_ipem_metallurgy_2026_routes",
    "import_ipem_fertilizers_routes",
    "import_ipem_forest_routes",
    "import_ipem_other_routes",
    "import_ipem_minstroy_routes",
)

OIL_IPEM_IMPORT_COMMAND = "import_ipem_oil_routes"


class Command(BaseCommand):
    help = (
        "По очереди вызывает импорт IPEM (уголь, металлургия, удобрения, "
        "лес, прочие, минстрой). Общие флаги пробрасываются в каждую команду; "
        "пути к XLSX — дефолты соответствующих команд."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--route-set-code",
            dest="route_set_code",
            default="RZD_2026",
            help="Код RouteSet с маршрутами РЖД (по умолчанию RZD_2026).",
        )
        parser.add_argument(
            "--scenario-id",
            dest="scenario_id",
            type=int,
            help=(
                "ID сценария: seed эластичности и привязка набора "
                "(пробрасывается в каждую команду)."
            ),
        )
        parser.add_argument(
            "--skip-elasticity",
            dest="skip_elasticity",
            action="store_true",
            help="Не загружать правила эластичности даже при --scenario-id.",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Только проверка резолва, без записи в БД.",
        )
        parser.add_argument(
            "--include-oil",
            dest="include_oil",
            action="store_true",
            help="Также вызвать import_ipem_oil_routes в конце.",
        )
        parser.add_argument(
            "--only",
            dest="only",
            nargs="+",
            metavar="COMMAND",
            help=(
                "Запустить только указанные команды "
                "(имена manage.py-команд). Игнорирует --include-oil."
            ),
        )

    def handle(self, *args, **options) -> None:
        commands = self._resolve_commands(
            only=options.get("only"),
            include_oil=bool(options.get("include_oil")),
        )
        if not commands:
            raise CommandError("Список команд для запуска пуст")

        kwargs: dict[str, object] = {
            "route_set_code": options["route_set_code"],
            "verbosity": options["verbosity"],
        }
        if options.get("scenario_id") is not None:
            kwargs["scenario_id"] = options["scenario_id"]
        if options.get("skip_elasticity"):
            kwargs["skip_elasticity"] = True
        if options.get("dry_run"):
            kwargs["dry_run"] = True

        total = len(commands)
        for index, name in enumerate(commands, start=1):
            self.stdout.write(self.style.NOTICE(f"[{index}/{total}] {name}"))
            self.stdout.flush()
            call_command(name, **kwargs)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: {total} IPEM-импорт(ов), "
                f"route_set={options['route_set_code']!r}"
                f"{', dry_run' if options.get('dry_run') else ''}."
            )
        )

    def _resolve_commands(
        self,
        *,
        only: Sequence[str] | None,
        include_oil: bool,
    ) -> tuple[str, ...]:
        if only:
            unknown = [
                name for name in only if name not in self._known_commands()
            ]
            if unknown:
                raise CommandError(
                    "Неизвестные команды в --only: "
                    + ", ".join(unknown)
                    + ". Допустимо: "
                    + ", ".join(self._known_commands())
                )
            return tuple(only)

        commands = list(DEFAULT_IPEM_IMPORT_COMMANDS)
        if include_oil:
            commands.append(OIL_IPEM_IMPORT_COMMAND)
        return tuple(commands)

    @staticmethod
    def _known_commands() -> tuple[str, ...]:
        return (*DEFAULT_IPEM_IMPORT_COMMANDS, OIL_IPEM_IMPORT_COMMAND)
