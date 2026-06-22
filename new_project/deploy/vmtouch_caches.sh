#!/usr/bin/env bash
# Прогрев kernel page cache для дисковых кэшей (после простоя / reboot).
# Cron: 0 */3 * * * root /opt/tariff_equlizer/new_project/deploy/vmtouch_caches.sh >> /var/log/tariff-vmtouch.log 2>&1
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CACHE_ROOT="${PROJECT_DIR}/cache"
LOG_TAG="${LOG_TAG:-tariff-vmtouch}"
VMTOUCH="${VMTOUCH:-$(command -v vmtouch || true)}"

if [[ -z "${VMTOUCH}" ]]; then
  echo "$(date -Is) [${LOG_TAG}] ERROR: vmtouch not found (apt install vmtouch)" >&2
  exit 1
fi

for dir in route_mart scenario_compute; do
  path="${CACHE_ROOT}/${dir}"
  if [[ -d "${path}" ]]; then
    echo "$(date -Is) [${LOG_TAG}] touching ${path}"
    "${VMTOUCH}" -t "${path}"
  fi
done
