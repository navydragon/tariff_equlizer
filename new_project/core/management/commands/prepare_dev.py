"""
Полная подготовка локальной/dev-среды: справочники, базовый сценарий, тестовые маршруты.
"""
import os
from collections.abc import Callable

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from core.management.reference_clear import clear_all_reference_data


class Command(BaseCommand):
    help = (
        "Подготавливает dev-среду: импорт справочников, базовый сценарий, "
        "случайные маршруты (по умолчанию 100 000)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--skip-admin",
            action="store_true",
            help="Не создавать суперпользователя (create_admin).",
        )
        parser.add_argument(
            "--login",
            default="admin",
            help="Логин админа для create_admin (по умолчанию admin).",
        )
        parser.add_argument(
            "--email",
            default="admin@emiit.ru",
            help="Email админа для create_admin.",
        )
        parser.add_argument(
            "--password",
            default=None,
            help="Пароль админа. Иначе ADMIN_PASSWORD из окружения или .env.",
        )
        parser.add_argument(
            "--route-set-code",
            default="DEFAULT_ROUTE_SET",
            help="Код набора маршрутов (по умолчанию DEFAULT_ROUTE_SET).",
        )
        parser.add_argument(
            "--routes-count",
            type=int,
            default=100_000,
            help="Сколько случайных маршрутов сгенерировать (по умолчанию 100000).",
        )
        parser.add_argument(
            "--skip-routes",
            action="store_true",
            help="Не генерировать случайные маршруты.",
        )
        parser.add_argument(
            "--clear-routes",
            action="store_true",
            help="Очистить маршруты в наборе перед генерацией.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Размер пакета для generate_random_routes (по умолчанию 1000).",
        )
        parser.add_argument(
            "--clear-references",
            action="store_true",
            help=(
                "Очистить справочники и маршруты перед импортом "
                "(--clear у import_* / init_route_refs; маршруты удаляются автоматически)."
            ),
        )

    def handle(self, *args, **options) -> None:
        password = options["password"] or os.environ.get("ADMIN_PASSWORD")
        if not options["skip_admin"] and not password:
            raise CommandError(
                "Задайте пароль админа: --password или переменную ADMIN_PASSWORD "
                "(в .env для manage.py)."
            )

        steps: list[tuple[str, Callable[[], None]]] = []

        if not options["skip_admin"]:
            steps.append(
                (
                    "create_admin",
                    lambda: call_command(
                        "create_admin",
                        login=options["login"],
                        email=options["email"],
                        password=password,
                        verbosity=options["verbosity"],
                    ),
                )
            )

        clear = options["clear_references"]
        import_kwargs = {"verbosity": options["verbosity"]}
        if clear:
            import_kwargs["clear"] = True
            steps.append(
                (
                    "clear_reference_dependencies",
                    lambda: self._clear_reference_dependencies(options["verbosity"]),
                )
            )

        steps.extend(
            [
                ("import_railroads", lambda: call_command("import_railroads", **import_kwargs)),
                ("import_regions", lambda: call_command("import_regions", **import_kwargs)),
                ("import_stations", lambda: call_command("import_stations", **import_kwargs)),
                ("import_cargo_groups", lambda: call_command("import_cargo_groups", verbosity=options["verbosity"])),
                (
                    "import_cargos",
                    lambda: call_command("import_cargos", **import_kwargs),
                ),
                (
                    "import_shippers",
                    lambda: call_command("import_shippers", **import_kwargs),
                ),
                (
                    "init_route_refs",
                    lambda: call_command(
                        "init_route_refs",
                        verbosity=options["verbosity"],
                        **({"clear": True} if clear else {}),
                    ),
                ),
                (
                    "create_base_scenario",
                    lambda: call_command("create_base_scenario", verbosity=options["verbosity"]),
                ),
            ]
        )

        if not options["skip_routes"]:
            route_kwargs = {
                "route_set_code": options["route_set_code"],
                "count": options["routes_count"],
                "batch_size": options["batch_size"],
                "verbosity": options["verbosity"],
            }
            if options["clear_routes"]:
                route_kwargs["clear_existing"] = True
            steps.append(
                (
                    "generate_random_routes",
                    lambda: call_command("generate_random_routes", **route_kwargs),
                )
            )

        total = len(steps)
        for index, (name, run_step) in enumerate(steps, start=1):
            self.stdout.write(self.style.NOTICE(f"[{index}/{total}] {name}"))
            run_step()

        self.stdout.write(self.style.SUCCESS("Подготовка dev-среды завершена."))

    def _clear_reference_dependencies(self, verbosity: int) -> None:
        counts = clear_all_reference_data()
        if verbosity < 1:
            return
        self.stdout.write(
            self.style.WARNING(
                "Зависимости справочников очищены: "
                f"маршрутов {counts.routes}, станций {counts.stations}, "
                f"регионов {counts.regions}, грузов {counts.cargos}, "
                f"дорог {counts.railroads}, родов вагона {counts.wagon_kinds}, "
                f"типов отправки {counts.shipment_types}, "
                f"видов сообщения {counts.message_types}."
            )
        )
