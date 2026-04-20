$ErrorActionPreference = "Stop"

# Переходим в корень проекта (папка new_project)
Set-Location "$PSScriptRoot\.."

# Путь к Python из виртуального окружения
$python = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Виртуальное окружение .venv не найдено. Сначала запустите tasks\migrations.ps1 или создайте venv."
    exit 1
}

Write-Host "Запускаю dev-сервер через $python run_app.py ..."

& $python run_app.py

