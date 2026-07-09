#!/usr/bin/env bash
set -euo pipefail

# Максимальный прогрев: route mart + KPI + compact + fallout (эластичность).
# Запускать на сервере из /opt/.../new_project.

cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# По умолчанию: не трогаем git pull/миграции/статику, а делаем только прогрев.
# Если хочется прогреть на чистых кешах — добавьте CLEAR=1.

CLEAR="${CLEAR:-}"

if [[ -n "${CLEAR}" ]]; then
  echo "==> Очистка кешей включена (CLEAR=1)"
  sudo bash deploy/update_prod.sh --warm-caches --warm-scenarios
else
  echo "==> Прогрев без очистки кешей"
  KEEP_DEPLOY_CACHES=1 WARM_DEPLOY_CACHES=1 WARM_DEPLOY_SCENARIOS=1 sudo bash deploy/update_prod.sh
fi

