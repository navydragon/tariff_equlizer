#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "$PROJECT_DIR"

if [[ ! -d ".git" ]]; then
  echo "ERROR: Не найден .git в ${PROJECT_DIR}. Запустите скрипт в каталоге проекта." >&2
  exit 1
fi

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERROR: Не найдено виртуальное окружение: ${PROJECT_DIR}/.venv/bin/activate" >&2
  exit 1
fi

echo "==> Обновляем код (git pull)"
git pull

echo "==> Активируем venv"
# shellcheck disable=SC1091
source ".venv/bin/activate"

echo "==> Обновляем зависимости (pip install -r requirements.txt)"
pip install -r requirements.txt

echo "==> Применяем миграции и собираем статику (settings_prod)"
export DJANGO_SETTINGS_MODULE="config.settings_prod"
python manage.py migrate
python manage.py collectstatic --noinput

echo "==> Перезапускаем сервис (tariff-equlizer)"
sudo systemctl restart tariff-equlizer

echo "==> Готово. Статус сервиса:"
sudo systemctl --no-pager --full status tariff-equlizer || true

