"""Последовательный импорт всех IPEM-секторов в RouteSet."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Порядок как в FIRST_IMPORT.md.
DEFAULT_IPEM_IMPORT_COMMANDS: tuple[str, ...] = (
    "import_ipem_coal_2026_routes",
    "import_ipem_metallurgy_2026_routes",
    "import_ipem_fertilizers_routes",
    "import_ipem_forest_routes",
    "import_ipem_other_routes",
    "import_ipem_minstroy_routes",
    "import_ipem_oil_routes",
)


class Command(BaseCommand):
    help = (
        "По очереди вызывает импорт IPEM (уголь, металлургия, удобрения, "
        "лес, прочие, минстрой, нефть). Каждый сектор — отдельный процесс "
        "(чтобы не копить RAM и не ловить OOM). Общие флаги пробрасываются "
        "в каждую команду; пути к XLSX — дефолты соответствующих команд."
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
            "--only",
            dest="only",
            nargs="+",
            metavar="COMMAND",
            help=(
                "Запустить только указанные команды "
                "(имена manage.py-команд)."
            ),
        )

    def handle(self, *args, **options) -> None:
        commands = self._resolve_commands(only=options.get("only"))
        if not commands:
            raise CommandError("Список команд для запуска пуст")

        manage_py = Path(settings.BASE_DIR) / "manage.py"
        if not manage_py.is_file():
            raise CommandError(f"manage.py не найден: {manage_py}")

        total = len(commands)
        for index, name in enumerate(commands, start=1):
            self.stdout.write(self.style.NOTICE(f"[{index}/{total}] {name}"))
            self.stdout.flush()
            argv = self._build_subprocess_argv(
                manage_py=manage_py,
                command=name,
                options=options,
            )
            completed = subprocess.run(argv, check=False)
            if completed.returncode != 0:
                raise CommandError(
                    f"{name} завершилась с кодом {completed.returncode} "
                    f"(шаг {index}/{total}). "
                    "Можно продолжить с --only оставшихся команд."
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: {total} IPEM-импорт(ов), "
                f"route_set={options['route_set_code']!r}"
                f"{', dry_run' if options.get('dry_run') else ''}."
            )
        )

    def _build_subprocess_argv(
        self,
        *,
        manage_py: Path,
        command: str,
        options: dict,
    ) -> list[str]:
        argv = [sys.executable, str(manage_py), command]
        argv.extend(["--route-set-code", str(options["route_set_code"])])
        if options.get("scenario_id") is not None:
            argv.extend(["--scenario-id", str(options["scenario_id"])])
        if options.get("skip_elasticity"):
            argv.append("--skip-elasticity")
        if options.get("dry_run"):
            argv.append("--dry-run")
        verbosity = int(options.get("verbosity") or 1)
        if verbosity != 1:
            argv.extend(["-v", str(verbosity)])
        return argv

    def _resolve_commands(
        self,
        *,
        only: Sequence[str] | None,
    ) -> tuple[str, ...]:
        if only:
            unknown = [
                name for name in only if name not in DEFAULT_IPEM_IMPORT_COMMANDS
            ]
            if unknown:
                raise CommandError(
                    "Неизвестные команды в --only: "
                    + ", ".join(unknown)
                    + ". Допустимо: "
                    + ", ".join(DEFAULT_IPEM_IMPORT_COMMANDS)
                )
            return tuple(only)

        return DEFAULT_IPEM_IMPORT_COMMANDS
