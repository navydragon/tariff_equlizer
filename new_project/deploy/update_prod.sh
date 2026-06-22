#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Использование: ./deploy/update_prod.sh [опции]

Опции:
  -n, --skip-cache-refresh   Не останавливать сервис, не очищать кеши
                             (только migrate + collectstatic + restart)
  --warm-caches              После очистки прогреть parquet-витрины (нужно много RAM;
                             на ~2M маршрутов без swap процесс может быть убит OOM)
  --keep-caches              Не очищать кеши перед прогревом (быстрый повторный warm,
                             если витрина на диске ещё актуальна)
  --warm-scenarios           После --warm-caches прогреть KPI-снимки сценариев
                             (первый заход в UI ~0.1 с вместо cold load)
  --skip-git-pull            Не выполнять git pull
  -h, --help                 Показать эту справку

Переменные окружения (эквивалент флагов):
  SKIP_CACHE_REFRESH=1       то же, что --skip-cache-refresh
  WARM_DEPLOY_CACHES=1       то же, что --warm-caches
  KEEP_DEPLOY_CACHES=1       то же, что --keep-caches
  WARM_DEPLOY_SCENARIOS=1    то же, что --warm-scenarios
  SKIP_GIT_PULL=1            то же, что --skip-git-pull
EOF
}

SKIP_CACHE_REFRESH="${SKIP_CACHE_REFRESH:-}"
WARM_DEPLOY_CACHES="${WARM_DEPLOY_CACHES:-}"
KEEP_DEPLOY_CACHES="${KEEP_DEPLOY_CACHES:-}"
WARM_DEPLOY_SCENARIOS="${WARM_DEPLOY_SCENARIOS:-}"
SKIP_GIT_PULL="${SKIP_GIT_PULL:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--skip-cache-refresh)
      SKIP_CACHE_REFRESH=1
      shift
      ;;
    --warm-caches)
      WARM_DEPLOY_CACHES=1
      shift
      ;;
    --keep-caches)
      KEEP_DEPLOY_CACHES=1
      shift
      ;;
    --warm-scenarios)
      WARM_DEPLOY_SCENARIOS=1
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

run_manage_as_service_user() {
  local manage_args="$1"
  if [[ "$(id -un)" == "$SERVICE_USER" ]]; then
    python manage.py $manage_args
  else
    sudo -u "$SERVICE_USER" bash -c "
      cd \"${PROJECT_DIR}\" &&
      source .venv/bin/activate &&
      export DJANGO_SETTINGS_MODULE=config.settings_prod &&
      python manage.py $manage_args
    "
  fi
}

if [[ -z "${SKIP_CACHE_REFRESH}" ]]; then
  if [[ -n "${WARM_DEPLOY_CACHES}" || -n "${WARM_DEPLOY_SCENARIOS}" || -z "${KEEP_DEPLOY_CACHES}" ]]; then
    echo "==> Останавливаем сервис (tariff-equlizer) перед обновлением кешей"
    sudo systemctl stop tariff-equlizer
  fi

  if [[ -z "${KEEP_DEPLOY_CACHES}" ]]; then
    echo "==> Очищаем дисковые кеши и Redis/LocMem (--clear-only)"
    run_manage_as_service_user "refresh_deploy_caches --clear-only"
  else
    echo "==> Очистка кешей пропущена (--keep-caches / KEEP_DEPLOY_CACHES=1)"
  fi

  if [[ -n "${WARM_DEPLOY_CACHES}" || -n "${WARM_DEPLOY_SCENARIOS}" ]]; then
    warm_args="--warm-only"
    if [[ -n "${WARM_DEPLOY_SCENARIOS}" ]]; then
      warm_args="${warm_args} --warm-scenarios"
    fi
    echo "==> Прогреваем кеши (refresh_deploy_caches ${warm_args})"
    if ! run_manage_as_service_user "refresh_deploy_caches ${warm_args}"; then
      echo "WARNING: прогрев кешей не завершился (часто OOM на больших наборах маршрутов)." >&2
      echo "         Сервис будет запущен; прогрейте вручную: refresh_deploy_caches ${warm_args}" >&2
    fi
  elif [[ -z "${KEEP_DEPLOY_CACHES}" ]]; then
    echo "==> Прогрев витрин пропущен (по умолчанию). Для прогрева: ./deploy/update_prod.sh --warm-caches"
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
