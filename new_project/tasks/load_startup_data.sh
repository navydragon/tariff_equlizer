#!/usr/bin/env bash
set -euo pipefail

# Скрипт для загрузки стартовых данных (несколько Django management commands).
#
# Использование:
#   ADMIN_PASSWORD="211211" bash new_project/tasks/load_startup_data.sh
#
# Либо:
#   bash new_project/tasks/load_startup_data.sh "admin@emiit.ru" "admin@emiit.ru" "211211"
#
# Примечания:
# - Скрипт предполагает, что миграции уже применены (manage.py migrate).
# - import_* команды по умолчанию идемпотентны (без --clear).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

ADMIN_LOGIN="${1:-admin@emiit.ru}"
ADMIN_EMAIL="${2:-admin@emiit.ru}"
ADMIN_PASSWORD="${3:-${ADMIN_PASSWORD:-}}"

ROUTE_SET_CODE="${ROUTE_SET_CODE:-DEFAULT_ROUTE_SET}"
TOTAL_IPM_FILE="${TOTAL_IPM_FILE:-total_ipem.csv}"

GENERATE_RANDOM_ROUTES="${GENERATE_RANDOM_ROUTES:-0}"
RANDOM_ROUTES_COUNT="${RANDOM_ROUTES_COUNT:-100000}"

if [[ -z "${ADMIN_PASSWORD}" ]]; then
  echo "Ошибка: ADMIN_PASSWORD не задан."
  echo "Передайте 3-й аргумент или установите переменную окружения ADMIN_PASSWORD."
  exit 1
fi

if [[ -f ".venv/bin/activate" ]]; then
  # Linux/WSL
  source ".venv/bin/activate"
elif [[ -f ".venv/Scripts/activate" ]]; then
  # Git Bash on Windows
  source ".venv/Scripts/activate"
else
  echo "Ошибка: venv не найден (.venv)."
  exit 1
fi

echo "==> create_admin"
python manage.py create_admin \
  --login "${ADMIN_LOGIN}" \
  --email "${ADMIN_EMAIL}" \
  --password "${ADMIN_PASSWORD}"

echo "==> create_base_scenario"
python manage.py create_base_scenario

echo "==> import_railroads"
python manage.py import_railroads

echo "==> import_stations"
python manage.py import_stations

echo "==> import_cargo_groups"
python manage.py import_cargo_groups

echo "==> import_cargos"
python manage.py import_cargos

echo "==> init_route_refs"
python manage.py init_route_refs

echo "==> import_total_ipem"
python manage.py import_total_ipem \
  --file "${TOTAL_IPM_FILE}" \
  --route-set-code "${ROUTE_SET_CODE}" \
  --route-set-name "${ROUTE_SET_CODE}"

if [[ "${GENERATE_RANDOM_ROUTES}" == "1" ]]; then
  echo "==> generate_random_routes"
  python manage.py generate_random_routes \
    --route-set-code "${ROUTE_SET_CODE}" \
    --count "${RANDOM_ROUTES_COUNT}"
else
  echo "==> generate_random_routes: skipped (GENERATE_RANDOM_ROUTES=${GENERATE_RANDOM_ROUTES})"
fi

echo "Готово: стартовые данные загружены."

