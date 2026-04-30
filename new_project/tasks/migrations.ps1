$ErrorActionPreference = "Stop"

# Переходим в корень проекта (папка new_project)
Set-Location "$PSScriptRoot\.."

# Если используете PostgreSQL: создайте `new_project/.env` и включите `USE_POSTGRES=true`.

# Убеждаемся, что venv существует, при необходимости создаём
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Виртуальное окружение не найдено, создаю..."
    py -3.14 -m venv .venv
}

$python = ".\.venv\Scripts\python.exe"

Write-Host "Применяю миграции с помощью $python ..."

& $python manage.py makemigrations
& $python manage.py migrate

Write-Host "Миграции успешно применены."

