import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


User = get_user_model()


class Command(BaseCommand):
    help = "Создает суперпользователя (админа)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--login",
            default="admin@emiit.ru",
            help="Логин (и USERNAME_FIELD) для админа.",
        )
        parser.add_argument(
            "--email",
            default="admin@emiit.ru",
            help="Email для админа.",
        )
        parser.add_argument(
            "--password",
            default=None,
            help=(
                "Пароль для админа. Если не задан, берется из ENV "
                "ADMIN_PASSWORD."
            ),
        )
        parser.add_argument(
            "--first-name",
            default="Admin",
            dest="first_name",
            help="Имя админа.",
        )
        parser.add_argument(
            "--last-name",
            default="Admin",
            dest="last_name",
            help="Фамилия админа.",
        )
        parser.add_argument(
            "--middle-name",
            default="",
            dest="middle_name",
            help="Отчество админа.",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Если пользователь уже существует — сбросить пароль и права.",
        )

    def handle(self, *args, **options):
        login = options["login"]
        email = options["email"]
        password = options["password"]
        if not password:
            password = os.environ.get("ADMIN_PASSWORD")

        if not password:
            raise RuntimeError(
                "Не задан password. Передайте его через --password "
                "или задайте переменную окружения ADMIN_PASSWORD."
            )

        first_name = options["first_name"]
        last_name = options["last_name"]
        middle_name = options["middle_name"]
        reset_password = options["reset_password"]

        user = User.objects.filter(login=login).first()
        if user and not reset_password:
            self.stdout.write(
                self.style.WARNING(
                    f"Пользователь с login={login} уже существует. Пропускаю."
                )
            )
            return

        if user and reset_password:
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.last_name = last_name
            user.first_name = first_name
            user.middle_name = middle_name
            if email:
                user.email = email
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Сброшен пароль админа: {user.login}")
            )
            return

        user = User.objects.create_superuser(
            login=login,
            password=password,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            email=email,
        )
        self.stdout.write(self.style.SUCCESS(f"Создан админ: {user.login}"))
