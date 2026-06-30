"""Проверка видимости маршрутов импорт/продовольствие в поиске."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

import sqlite3

from django.db.models import Count, Q

from core.domain.route.repositories import RouteRepository
from core.management.rzd_paths import RZD_TABLE, get_rzd_db_path
from core.models import MessageType, Route, RouteSet

# Топ-3 цифровые коды из Импорт в SQLite (потребительские/прочие — уточнить у заказчика список).
SAMPLE_IMPORT_CODE_3 = ("042", "046", "041")
SAMPLE_FOOD_CODE_3 = ("011", "012", "013", "014", "015")  # хлеб/продовольствие — пример


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def sqlite_counts(code_3: str, message_like: str) -> int:
    conn = sqlite3.connect(get_rzd_db_path())
    sql = f"""
        SELECT COUNT(*)
        FROM [{RZD_TABLE}]
        WHERE CAST([Код груза(3цифры)] AS TEXT) = ?
          AND [Вид перевозки] LIKE ?
    """
    return conn.execute(sql, (code_3, message_like)).fetchone()[0]


def django_counts(route_set_id: int, code_3: str, message_name: str) -> dict[str, int]:
    base = Route.objects.filter(
        route_set_id=route_set_id,
        cargo_code_3=code_3,
        message_type__name=message_name,
    )
    return {
        "all": base.count(),
        "operational": base.filter(is_model=False).count(),
        "model": base.filter(is_model=True).count(),
    }


def search_simulation(route_set_id: int, query: str, *, economics_filled: bool) -> int:
  from core.domain.route.dto import RouteListFiltersDTO
  from core.domain.route.services import RouteService

  filters = RouteListFiltersDTO(
      route_set_id=route_set_id,
      page=1,
      page_size=100,
      search=query,
      economics_filled=economics_filled,
  )
  result, errors = RouteService().list_routes(filters)
  if errors:
      print(f"  search {query!r} economics_filled={economics_filled}: ERR {errors}")
      return 0
  assert result is not None
  print(
      f"  search {query!r} economics_filled={economics_filled}: "
      f"{len(result.items)} на странице, total={result.total}"
  )
  return result.total


def main() -> None:
    rs = RouteSet.objects.filter(code="RZD_2026").first()
    if not rs:
        print("RouteSet RZD_2026 не найден")
        return

    _section("Справочник видов сообщения")
    for mt in MessageType.objects.order_by("name"):
        cnt = Route.objects.filter(route_set=rs, message_type=mt).count()
        print(f"  {mt.name}: {cnt:,} маршрутов")

    _section("SQLite: импорт, код 042")
    print(f"  строк: {sqlite_counts('042', '%Импорт%'):,}")

    _section("Django RZD_2026: код 042 + Импорт")
    print(" ", django_counts(rs.id, "042", "Импорт"))

    _section("Симуляция route_list_api (код груза 042101)")
    search_simulation(rs.id, "042101", economics_filled=False)
    search_simulation(rs.id, "042101", economics_filled=True)
    search_simulation(rs.id, "042", economics_filled=False)
    search_simulation(rs.id, "042", economics_filled=True)

    _section("Фильтр cascade: message_type=Импорт + cargo_code_3 через cargo_id")
    import_routes = Route.objects.filter(
        route_set=rs,
        message_type__name="Импорт",
        cargo_code_3__in=SAMPLE_IMPORT_CODE_3,
        is_model=False,
    ).count()
    print(f"  operational импорт {SAMPLE_IMPORT_CODE_3}: {import_routes:,}")

    internal_food = Route.objects.filter(
        route_set=rs,
        message_type__name="Внутр. перевозки",
        cargo_code_3__in=SAMPLE_FOOD_CODE_3,
        is_model=False,
    ).count()
    print(f"  operational внутр. продовольствие (пример кодов): {internal_food:,}")

    _section("Поиск по _build_search_query для цифрового кода 042")
    repo = RouteRepository()
    q = repo._build_search_query("042")
    cnt = Route.objects.filter(route_set=rs, is_model=False).filter(q).count()
    print(f"  operational, search='042': {cnt:,} (ожидается 0, если 042 не ЕСР)")


if __name__ == "__main__":
    main()
