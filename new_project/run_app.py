import os
import sys
import webbrowser

import django
from django.core.management import call_command, execute_from_command_line


def main() -> None:
    """
    Точка входа:
    - настраивает Django
    - при запуске из exe (PyInstaller) открывает браузер и стартует runserver БЕЗ autoreload
    - при обычном запуске ведёт себя как dev-скрипт (runserver с autoreload)
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    # Проверяем, запущен ли код из PyInstaller exe
    # sys.frozen устанавливается PyInstaller при запуске из exe
    is_exe = getattr(sys, "frozen", False)

    if is_exe:
        # Открываем браузер только в exe-варианте
        webbrowser.open("http://127.0.0.1:8888/", new=2)
        # Инициализируем Django вручную, прежде чем вызывать команды управления
        django.setup()
        # Запускаем runserver без autoreload, чтобы избежать проблем с PyInstaller
        call_command("runserver", "127.0.0.1:8888", use_reloader=False)
    else:
        # Обычное поведение для разработки
        execute_from_command_line([sys.argv[0], "runserver", "127.0.0.1:8888"])


if __name__ == "__main__":
    main()

