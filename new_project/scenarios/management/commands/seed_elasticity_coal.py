from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from scenarios.domain.services.base_elasticity_seed import (
    ELASTICITY_SET_NAME,
    EXPORT_RULE_NAME,
    INTERNAL_RULE_NAME,
    seed_coal_elasticity_for_scenario,
)
from scenarios.models import Scenario

User = get_user_model()


class Command(BaseCommand):
    help = (
        f'Загружает кривую эластичности угля (лист «Уголь_коэфф») в набор '
        f'«{ELASTICITY_SET_NAME}» и при необходимости привязывает к сценарию.'
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--scenario-id",
            type=int,
            help="ID сценария (для определения автора набора и опциональной привязки).",
        )
        parser.add_argument(
            "--scenario-name",
            default="Базовый сценарий",
            help='Имя сценария, если не указан --scenario-id (по умолчанию «Базовый сценарий»).',
        )
        parser.add_argument(
            "--author-login",
            help="Автор набора, если сценарий не указан (по умолчанию — первый superuser).",
        )
        parser.add_argument(
            "--no-attach",
            action="store_true",
            help="Только создать/обновить набор и правило, не привязывать к сценарию.",
        )

    def handle(self, *args, **options) -> None:
        scenario = self._resolve_scenario(options)
        author = scenario.author if scenario is not None else self._resolve_author(options)
        attach = scenario is not None and not options.get("no_attach")

        if scenario is None:
            raise CommandError(
                "Укажите --scenario-id или --scenario-name, либо создайте сценарий заранее."
            )

        result = seed_coal_elasticity_for_scenario(
            scenario,
            author=author,
            attach=attach,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Набор «{ELASTICITY_SET_NAME}» (id={result.elasticity_set_id}): '
                f'«{EXPORT_RULE_NAME}» — {result.points_export} точек, '
                f'«{INTERNAL_RULE_NAME}» — {result.points_internal} точек'
                f"{', привязан к сценарию' if result.attached_to_scenario else ''}."
            )
        )

    def _resolve_scenario(self, options) -> Scenario | None:
        scenario_id = options.get("scenario_id")
        if scenario_id:
            scenario = Scenario.objects.filter(id=scenario_id).select_related("author").first()
            if scenario is None:
                raise CommandError(f"Сценарий id={scenario_id} не найден.")
            return scenario

        scenario_name = (options.get("scenario_name") or "").strip()
        if not scenario_name:
            return None
        return Scenario.objects.filter(name=scenario_name).select_related("author").first()

    def _resolve_author(self, options):
        login = (options.get("author_login") or "").strip()
        if login:
            user = User.objects.filter(login=login).first()
            if user is None:
                raise CommandError(f'Пользователь "{login}" не найден.')
            return user
        user = User.objects.filter(is_superuser=True).first()
        if user is None:
            raise CommandError("Superuser не найден. Укажите --author-login.")
        return user
