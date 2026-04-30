#!/usr/bin/env bash
set -euo pipefail

# Скрипт для создания админа:
#   ./tasks/create_admin.sh [login] [email] [password]
#
# Если password не задан аргументом — возьмём из переменной окружения ADMIN_PASSWORD.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

LOGIN="${1:-admin@emiit.ru}"
EMAIL="${2:-admin@emiit.ru}"
PASSWORD="${3:-${ADMIN_PASSWORD:-}}"

if [[ -z "${PASSWORD}" ]]; then
  echo "Ошибка: пароль не задан. Передайте 3-й аргумент или задайте ADMIN_PASSWORD."
  exit 1
fi

if [[ -f ".venv/bin/activate" ]]; then
  # Обычно для Linux/WSL
  source ".venv/bin/activate"
elif [[ -f ".venv/Scripts/activate" ]]; then
  # Обычно для Git Bash на Windows
  source ".venv/Scripts/activate"
else
  echo "Ошибка: venv не найден (.venv)."
  exit 1
fi

python manage.py create_admin --login "${LOGIN}" --email "${EMAIL}" --password "${PASSWORD}"

