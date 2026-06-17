"""
Прогрев scenario_compute (KPI + compact на диске) после деплоя.

Пример на prod:
  export DJANGO_SETTINGS_MODULE=config.settings_prod
  python scripts/warm_scenario_compute.py --route-set-id 2
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import django

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from calculations.domain.services.scenario_compute_warm import warm_scenario_compute


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Прогрев scenario_compute для сценариев (KPI + compact).",
    )
    parser.add_argument("--route-set-id", type=int, default=None)
    parser.add_argument("--scenario-id", type=int, default=None)
    parser.add_argument(
        "--compact-timeout",
        type=int,
        default=180,
        help="Секунд ждать compact на диске (по умолчанию 180).",
    )
    args = parser.parse_args()

    if args.route_set_id is None and args.scenario_id is None:
        parser.error("Укажите --route-set-id или --scenario-id.")

    failed = warm_scenario_compute(
        route_set_id=args.route_set_id,
        scenario_id=args.scenario_id,
        compact_timeout_s=float(args.compact_timeout),
    )
    if failed:
        print(f"ERROR: прогрев не завершён для {failed} сценариев.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
