# Инструкция по сборке exe через PyInstaller

## Требования

- Python 3.14 (установлен в системе)
- Виртуальное окружение с установленными зависимостями

## Подготовка

### 1. Создание и активация виртуального окружения

```powershell
# Перейти в папку проекта
cd new_project

# Создать venv на Python 3.14
py -3.14 -m venv .venv

# Активировать venv
# В PowerShell:
.venv\Scripts\Activate.ps1

# В cmd:
.venv\Scripts\activate.bat
```

### 2. Установка зависимостей

```bash
pip install --upgrade pip
pip install django django-htmx pyinstaller
```

Или из файла `requirements.txt` (если создан):

```bash
pip install -r requirements.txt
```

### 3. Проверка работоспособности проекта

Перед сборкой убедитесь, что проект запускается:

```bash
# Применить миграции (если нужно)
python manage.py migrate

# Проверить конфигурацию
python manage.py check

# Запустить тестовый сервер
python run_app.py
```

## Сборка exe

### Базовая команда PyInstaller

Из корня проекта `new_project` выполните:

```powershell
.venv\Scripts\pyinstaller.exe --onefile --name tariff_equalizer --collect-all django --add-data "templates;templates" run_app.py
```

### Параметры команды

- `--onefile` — создать один исполняемый файл (все зависимости упакованы внутрь)
- `--name tariff_equalizer` — имя итогового exe-файла
- `--collect-all django` — автоматически собрать все модули Django (включая миграции, шаблоны, статику)
- `--add-data "templates;templates"` — добавить папку `templates` в exe (Windows-синтаксис: `источник;путь_внутри_пакета`)
- `run_app.py` — точка входа приложения

### Дополнительные опции (опционально)

Если нужно скрыть консольное окно (только GUI):

```powershell
.venv\Scripts\pyinstaller.exe --onefile --noconsole --name tariff_equalizer --collect-all django --add-data "templates;templates" run_app.py
```

Если нужно добавить иконку:

```powershell
.venv\Scripts\pyinstaller.exe --onefile --name tariff_equalizer --icon=icon.ico --collect-all django --add-data "templates;templates" run_app.py
```

### Результат сборки

После успешной сборки:

- **exe-файл**: `dist\tariff_equalizer.exe`
- **Временные файлы**: `build\tariff_equalizer\` (можно удалить)
- **Спецификация**: `tariff_equalizer.spec` (можно использовать для повторной сборки)

## Использование spec-файла

Если нужно изменить параметры сборки, можно отредактировать `tariff_equalizer.spec` и собрать через него:

```powershell
.venv\Scripts\pyinstaller.exe tariff_equalizer.spec
```

## Запуск exe

1. Скопируйте `dist\tariff_equalizer.exe` на флешку или в нужную папку
2. Запустите exe двойным кликом
3. Автоматически откроется браузер с адресом `http://127.0.0.1:8000/`
4. Django-сервер будет работать до закрытия окна консоли (или до закрытия процесса)

## Размер exe

Типичный размер exe для Django-приложения: **50-150 МБ** (зависит от версии Python и количества зависимостей).

## Ограничения

- **Платформа**: exe собран для той же ОС и архитектуры, на которой выполнялась сборка (Windows x64 → только Windows x64)
- **Python**: exe содержит встроенный Python-интерпретатор, не требует установки Python на целевой машине
- **Антивирус**: некоторые антивирусы могут блокировать самособранные exe — добавьте в исключения при необходимости

## Устранение проблем

### Ошибка "ModuleNotFoundError"

Если при запуске exe возникает ошибка о недостающих модулях, добавьте их явно в команду:

```powershell
.venv\Scripts\pyinstaller.exe --onefile --name tariff_equalizer --collect-all django --hidden-import=имя_модуля --add-data "templates;templates" run_app.py
```

### Статические файлы не загружаются

Если статические файлы (CSS/JS) не подгружаются, убедитесь, что они либо:
- Подключены через CDN (как в текущем проекте — Tabler и htmx через CDN)
- Или добавлены через `--add-data` и правильно настроен `STATIC_ROOT` в `settings.py`

### Порт 8000 занят

Если порт 8000 уже занят, измените порт в `run_app.py`:

```python
webbrowser.open("http://127.0.0.1:8001/", new=2)
execute_from_command_line([sys.argv[0], "runserver", "127.0.0.1:8001"])
```

## Быстрая команда для повторной сборки

Если нужно часто пересобирать, можно создать скрипт `build.bat`:

```batch
@echo off
call .venv\Scripts\activate.bat
pyinstaller.exe --onefile --name tariff_equalizer --collect-all django --add-data "templates;templates" run_app.py
pause
```

Или PowerShell-скрипт `build.ps1`:

```powershell
.venv\Scripts\Activate.ps1
pyinstaller.exe --onefile --name tariff_equalizer --collect-all django --add-data "templates;templates" run_app.py
Read-Host "Нажмите Enter для выхода"
```
