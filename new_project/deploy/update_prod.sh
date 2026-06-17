#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Использование: ./deploy/update_prod.sh [опции]

Опции:
  -n, --skip-cache-refresh   Не останавливать сервис, не очищать кеши и не прогревать
                             parquet-витрины маршрутов (только migrate + collectstatic + restart)
  --skip-git-pull            Не выполнять git pull
  -h, --help                 Показать эту справку

Переменные окружения (эквивалент флагов):
  SKIP_CACHE_REFRESH=1       то же, что --skip-cache-refresh
  SKIP_GIT_PULL=1            то же, что --skip-git-pull
EOF
}

SKIP_CACHE_REFRESH="${SKIP_CACHE_REFRESH:-}"
SKIP_GIT_PULL="${SKIP_GIT_PULL:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--skip-cache-refresh)
      SKIP_CACHE_REFRESH=1
      shift
      ;;
    --skip-git-pull)
      SKIP_GIT_PULL=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: неизвестный аргумент: $1" >&2
      echo "Подсказка: ./deploy/update_prod.sh --help" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "$PROJECT_DIR"

GIT_ROOT=""
_dir="$PROJECT_DIR"
for _ in {1..5}; do
  if [[ -d "${_dir}/.git" ]]; then
    GIT_ROOT="$_dir"
    break
  fi
  _dir="$(dirname "$_dir")"
done

if [[ -z "${SKIP_GIT_PULL}" && -n "$GIT_ROOT" ]]; then
  echo "==> Обновляем код (git pull в ${GIT_ROOT})"
  (cd "$GIT_ROOT" && git pull)
elif [[ -n "${SKIP_GIT_PULL}" ]]; then
  echo "==> git pull пропущен (--skip-git-pull / SKIP_GIT_PULL=1)"
else
  echo "WARNING: .git не найден рядом с проектом. git pull пропущен."
  echo "         Ищем от ${PROJECT_DIR} вверх до 5 уровней."
fi

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERROR: Не найдено виртуальное окружение: ${PROJECT_DIR}/.venv/bin/activate" >&2
  exit 1
fi

echo "==> Активируем venv"
# shellcheck disable=SC1091
source ".venv/bin/activate"

echo "==> Обновляем зависимости (pip install -r requirements.txt)"
pip install -r requirements.txt

echo "==> Применяем миграции и собираем статику (settings_prod)"
export DJANGO_SETTINGS_MODULE="config.settings_prod"
python manage.py migrate
python manage.py collectstatic --noinput

SERVICE_USER="${TARIFF_SERVICE_USER:-tariff}"

if [[ -z "${SKIP_CACHE_REFRESH}" ]]; then
  echo "==> Останавливаем сервис (tariff-equlizer) перед обновлением кешей"
  sudo systemctl stop tariff-equlizer

  echo "==> Очищаем кеши и прогреваем витрины маршрутов"
  if [[ "$(id -un)" == "$SERVICE_USER" ]]; then
    python manage.py refresh_deploy_caches
  else
    sudo -u "$SERVICE_USER" bash -c "
      cd \"${PROJECT_DIR}\" &&
      source .venv/bin/activate &&
      export DJANGO_SETTINGS_MODULE=config.settings_prod &&
      python manage.py refresh_deploy_caches
    "
  fi

  echo "==> Запускаем сервис (tariff-equlizer)"
  sudo systemctl start tariff-equlizer
else
  echo "==> Обновление кешей пропущено (--skip-cache-refresh / SKIP_CACHE_REFRESH=1)"
  echo "==> Перезапускаем сервис (tariff-equlizer)"
  sudo systemctl restart tariff-equlizer
fi

echo "==> Готово. Статус сервиса:"
sudo systemctl --no-pager --full status tariff-equlizer || true
