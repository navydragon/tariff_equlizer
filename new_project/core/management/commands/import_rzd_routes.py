"""Импорт маршрутов из SQLite-базы РЖД (таблица ИХ_ГП)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.management.reference_clear import clear_routes_for_route_set
from core.management.rzd_paths import RZD_TABLE, get_rzd_db_path
from core.models import (
    Cargo,
    MessageType,
    Route,
    RouteSet,
    ShipmentType,
    Shipper,
    Station,
    WagonKind,
)

# Колонки ИХ_ГП → поля Route (см. distinct-значения в БД РЖД).
COL_INDEX = "index"
COL_CARGO_CODE = "Код груза"
COL_ORIGIN_ESR = "Код станц отпр РФ"
COL_DEST_ESR = "Код станц назн РФ"
COL_WAGON_KIND = "Род вагона"
COL_MESSAGE_TYPE = "Вид перевозки"
COL_SHIPMENT_TYPE = "Категория отпр"  # в выгрузке: повагонная, маршрутная, …
COL_SHIPMENT_CATEGORY = "Тип парка"  # в выгрузке: груженые, порожние
COL_PARK_TYPE = "Вид спец контейнера"  # в выгрузке: универсальный, …
COL_DISTANCE_BELT = "Пояс дальности по 10_01"
COL_CARGO_GROUP_CMTP = "Группа груза (ЦМТП)"
COL_CARGO_CODE_IZPOD = "Код груза(изпод)"
COL_OKPO = "ОКПО_компании_отпр"
COL_INN = "ИНН_компании"
COL_SHIPPER_NAME = "Наименование_компании"
COL_HOLDING = "Холдинг"
COL_VOLUME_TONS = "Объем перевозок (т)"
COL_TURNOVER_TKM = "Грузооборот (т_км)"
COL_CHARGE_RUB = "Провозная плата (руб)"

DEFAULT_ROUTE_SET_CODE = "RZD_2026"
DEFAULT_ROUTE_SET_NAME = "РЖД 2026"

SELECT_SQL = f"""
    SELECT
        [{COL_INDEX}],
        [{COL_CARGO_CODE}],
        [{COL_ORIGIN_ESR}],
        [{COL_DEST_ESR}],
        [{COL_WAGON_KIND}],
        [{COL_MESSAGE_TYPE}],
        [{COL_SHIPMENT_TYPE}],
        [{COL_SHIPMENT_CATEGORY}],
        [{COL_PARK_TYPE}],
        [{COL_DISTANCE_BELT}],
        [{COL_CARGO_GROUP_CMTP}],
        [{COL_CARGO_CODE_IZPOD}],
        [{COL_OKPO}],
        [{COL_INN}],
        [{COL_SHIPPER_NAME}],
        [{COL_HOLDING}],
        [{COL_VOLUME_TONS}],
        [{COL_TURNOVER_TKM}],
        [{COL_CHARGE_RUB}]
    FROM [{RZD_TABLE}]
"""


def _normalize_name(value: str) -> str:
    return (value or "").strip().casefold()


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    raw = str(value).strip().replace(" ", "")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _normalize_inn(value: Any) -> str:
    raw = str(value).strip() if value is not None else ""
    if raw in ("-", "0"):
        return ""
    return raw


def _is_missing_ref(value: str) -> bool:
    v = (value or "").strip()
    return not v or v in ("-", "0")


def _parse_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    raw = str(value).strip().replace(" ", "").replace(",", ".")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = (
        "Импортирует маршруты из data/01_2026-05-19.db (ИХ_ГП) "
        f'в набор «{DEFAULT_ROUTE_SET_NAME}».'
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--db",
            type=str,
            default="",
            help="Путь к SQLite (по умолчанию data/01_2026-05-19.db)",
        )
        parser.add_argument(
            "--route-set-code",
            type=str,
            default=DEFAULT_ROUTE_SET_CODE,
            help=f"Код RouteSet (по умолчанию {DEFAULT_ROUTE_SET_CODE})",
        )
        parser.add_argument(
            "--route-set-name",
            type=str,
            default=DEFAULT_ROUTE_SET_NAME,
            help=f"Название RouteSet (по умолчанию {DEFAULT_ROUTE_SET_NAME})",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Удалить маршруты набора перед импортом",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            help="Размер пакета bulk_create",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Ограничить число строк из БД (0 = без ограничения)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Проверка без записи в БД",
        )
        parser.add_argument(
            "--backfill-shippers",
            action="store_true",
            help="Проставить грузоотправителей существующим маршрутам набора из БД РЖД",
        )

    def handle(self, *args, **options) -> None:
        db_path = Path(options["db"]) if options["db"] else get_rzd_db_path()
        if not db_path.is_absolute():
            db_path = Path(settings.BASE_DIR) / db_path
        if not db_path.exists():
            raise CommandError(f"Файл БД не найден: {db_path}")

        batch_size = max(1, int(options["batch_size"]))
        limit = int(options["limit"] or 0)
        dry_run = bool(options["dry_run"])
        route_set_code = (options["route_set_code"] or DEFAULT_ROUTE_SET_CODE).strip()
        route_set_name = (options["route_set_name"] or DEFAULT_ROUTE_SET_NAME).strip()

        self.stdout.write(
            self.style.NOTICE(
                f"Импорт из {db_path} -> RouteSet code={route_set_code!r}, "
                f"name={route_set_name!r} (dry_run={dry_run}, limit={limit or 'нет'})"
            )
        )

        caches = self._build_caches()

        with transaction.atomic():
            route_set, _ = RouteSet.objects.get_or_create(
                code=route_set_code,
                defaults={"name": route_set_name},
            )
            if route_set.name != route_set_name:
                route_set.name = route_set_name
                route_set.save(update_fields=["name"])

            if options.get("backfill_shippers"):
                stats = self._backfill_shippers(
                    db_path=db_path,
                    route_set=route_set,
                    caches=caches,
                    batch_size=batch_size,
                    dry_run=dry_run,
                )
                if dry_run:
                    transaction.set_rollback(True)
                self.stdout.write(
                    self.style.SUCCESS(
                        "Дозаполнение грузоотправителей завершено. "
                        f"Обработано: {stats['processed']}, обновлено: {stats['updated']}."
                    )
                )
                return

            if options.get("clear"):
                deleted = clear_routes_for_route_set(route_set.id)
                self.stdout.write(
                    self.style.WARNING(
                        f"Удалено маршрутов набора {route_set.code}: {deleted}"
                    )
                )

            stats = self._import_rows(
                db_path=db_path,
                route_set=route_set,
                caches=caches,
                batch_size=batch_size,
                limit=limit,
                dry_run=dry_run,
            )

            # bulk_create не триггерит сигналы — обновляем версию набора вручную
            if not dry_run:
                RouteSet.objects.filter(pk=route_set.pk).update(updated_at=timezone.now())

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "Импорт РЖД завершён. "
                f"Обработано: {stats['processed']}, создано: {stats['created']}, "
                f"пропущено: {stats['skipped']}."
            )
        )
        if stats["created_refs"]:
            self.stdout.write(
                self.style.WARNING(
                    "Автосоздано в справочниках: "
                    + ", ".join(f"{k}={v}" for k, v in stats["created_refs"].items())
                )
            )
        if stats["skip_reasons"]:
            self.stdout.write(self.style.WARNING("Причины пропуска:"))
            for reason, count in sorted(
                stats["skip_reasons"].items(), key=lambda x: -x[1]
            ):
                self.stdout.write(f"  {reason}: {count}")

    def _build_caches(self) -> dict[str, Any]:
        wagon_by_name = {
            _normalize_name(w.name): w for w in WagonKind.objects.all()
        }
        shipment_by_name = {
            _normalize_name(s.name): s for s in ShipmentType.objects.all()
        }
        message_by_name = {
            _normalize_name(m.name): m for m in MessageType.objects.all()
        }
        cargo_by_code = Cargo.objects.in_bulk()
        station_by_esr = Station.objects.in_bulk(field_name="esr_code")
        shipper_by_key: dict[tuple[Any, str, str], Shipper] = {}
        for shipper in Shipper.objects.all():
            key = (shipper.okpo, shipper.inn or "", shipper.name)
            shipper_by_key[key] = shipper

        return {
            "wagon_by_name": wagon_by_name,
            "shipment_by_name": shipment_by_name,
            "message_by_name": message_by_name,
            "cargo_by_code": cargo_by_code,
            "station_by_esr": station_by_esr,
            "shipper_by_key": shipper_by_key,
            "created_refs": {
                "wagon_kind": 0,
                "shipment_type": 0,
                "message_type": 0,
            },
        }

    def _resolve_shipper(
        self,
        row: sqlite3.Row,
        caches: dict[str, Any],
    ) -> Optional[Shipper]:
        shipper_name = (row[COL_SHIPPER_NAME] or "").strip()
        holding = (row[COL_HOLDING] or "").strip()
        okpo = _parse_int(row[COL_OKPO])
        inn = _normalize_inn(row[COL_INN])
        okpo_key = okpo if okpo is not None else 0

        if not _is_missing_ref(shipper_name):
            key = (okpo_key, inn, shipper_name)
            shipper = caches["shipper_by_key"].get(key)
            if shipper is None:
                shipper, created = Shipper.objects.get_or_create(
                    okpo=okpo_key,
                    inn=inn,
                    name=shipper_name,
                    defaults={
                        "holding": holding if not _is_missing_ref(holding) else "",
                    },
                )
                if not created and holding and not shipper.holding:
                    shipper.holding = holding
                    shipper.save(update_fields=["holding"])
                caches["shipper_by_key"][(shipper.okpo, shipper.inn or "", shipper.name)] = (
                    shipper
                )
            elif holding and not shipper.holding:
                shipper.holding = holding
                shipper.save(update_fields=["holding"])
            return shipper

        if not _is_missing_ref(holding):
            key = (okpo_key, inn, holding)
            shipper = caches["shipper_by_key"].get(key)
            if shipper is None:
                shipper, _ = Shipper.objects.get_or_create(
                    okpo=okpo_key,
                    inn=inn,
                    name=holding,
                    defaults={"holding": holding},
                )
                caches["shipper_by_key"][(shipper.okpo, shipper.inn or "", shipper.name)] = (
                    shipper
                )
            return shipper

        return None

    def _backfill_shippers(
        self,
        *,
        db_path: Path,
        route_set: RouteSet,
        caches: dict[str, Any],
        batch_size: int,
        dry_run: bool,
    ) -> dict[str, int]:
        routes = {
            route.route_code: route
            for route in Route.objects.filter(
                route_set=route_set,
                shipper__isnull=True,
            ).only("id", "route_code")
        }
        if not routes:
            return {"processed": 0, "updated": 0}

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        updates: list[Route] = []
        processed = 0
        route_codes = list(routes.keys())
        lookup_batch_size = 500
        select_by_index_sql = f"""
            SELECT
                [{COL_INDEX}],
                [{COL_OKPO}],
                [{COL_INN}],
                [{COL_SHIPPER_NAME}],
                [{COL_HOLDING}]
            FROM [{RZD_TABLE}]
            WHERE [{COL_INDEX}] IN ({{placeholders}})
        """

        try:
            for offset in range(0, len(route_codes), lookup_batch_size):
                chunk = route_codes[offset : offset + lookup_batch_size]
                placeholders = ",".join("?" * len(chunk))
                sql = select_by_index_sql.format(placeholders=placeholders)
                for row in conn.execute(sql, chunk):
                    route_code = (
                        str(row[COL_INDEX]).strip() if row[COL_INDEX] is not None else ""
                    )
                    route = routes.get(route_code)
                    if route is None:
                        continue
                    processed += 1
                    shipper = self._resolve_shipper(row, caches)
                    if shipper is None:
                        continue
                    route.shipper_id = shipper.id
                    updates.append(route)
        finally:
            conn.close()

        if updates and not dry_run:
            Route.objects.bulk_update(updates, ["shipper_id"], batch_size=batch_size)

        return {"processed": processed, "updated": len(updates)}

    def _resolve_ref(
        self,
        caches: dict[str, Any],
        model,
        cache_key: str,
        created_key: str,
        raw_name: str,
        *,
        required: bool,
    ):
        name = (raw_name or "").strip()
        norm = _normalize_name(name)
        if not norm:
            return None, ("missing_name" if required else None)

        cache: dict[str, Any] = caches[cache_key]
        obj = cache.get(norm)
        if obj is not None:
            return obj, None

        obj, was_created = model.objects.get_or_create(
            name=name,
            defaults={"position": len(cache) + 1, "is_active": True},
        )
        cache[norm] = obj
        if was_created:
            caches["created_refs"][created_key] += 1
        return obj, None

    def _import_rows(
        self,
        *,
        db_path: Path,
        route_set: RouteSet,
        caches: dict[str, Any],
        batch_size: int,
        limit: int,
        dry_run: bool,
    ) -> dict[str, Any]:
        processed = 0
        created = 0
        skipped = 0
        skip_reasons: dict[str, int] = {}
        batch: list[Route] = []

        def bump_skip(reason: str) -> None:
            nonlocal skipped
            skipped += 1
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            sql = SELECT_SQL
            if limit > 0:
                sql += f" LIMIT {int(limit)}"
            cursor = conn.execute(sql)

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break

                for row in rows:
                    processed += 1
                    if processed % 50000 == 0:
                        self.stdout.write(f"Обработано строк: {processed}…")

                    route = self._row_to_route(row, route_set, caches, bump_skip)
                    if route is None:
                        continue

                    batch.append(route)
                    if len(batch) >= batch_size:
                        if not dry_run:
                            Route.objects.bulk_create(batch, batch_size=batch_size)
                        created += len(batch)
                        batch.clear()

                if limit > 0:
                    break

            if batch:
                if not dry_run:
                    Route.objects.bulk_create(batch, batch_size=batch_size)
                created += len(batch)
                batch.clear()
        finally:
            conn.close()

        return {
            "processed": processed,
            "created": created,
            "skipped": skipped,
            "skip_reasons": skip_reasons,
            "created_refs": caches["created_refs"],
        }

    def _row_to_route(
        self,
        row: sqlite3.Row,
        route_set: RouteSet,
        caches: dict[str, Any],
        bump_skip,
    ) -> Optional[Route]:
        index_value = row[COL_INDEX]
        route_code = str(index_value).strip() if index_value is not None else ""
        if not route_code:
            bump_skip("empty_index")
            return None

        cargo_code = _parse_int(row[COL_CARGO_CODE])
        if cargo_code is None:
            bump_skip("invalid_cargo_code")
            return None
        cargo = caches["cargo_by_code"].get(cargo_code)
        if cargo is None:
            bump_skip("cargo_not_found")
            return None

        origin_esr = _parse_int(row[COL_ORIGIN_ESR])
        dest_esr = _parse_int(row[COL_DEST_ESR])
        if origin_esr is None or dest_esr is None:
            bump_skip("invalid_station_esr")
            return None
        origin = caches["station_by_esr"].get(origin_esr)
        destination = caches["station_by_esr"].get(dest_esr)
        if origin is None or destination is None:
            bump_skip("station_not_found")
            return None

        wagon, err = self._resolve_ref(
            caches,
            WagonKind,
            "wagon_by_name",
            "wagon_kind",
            row[COL_WAGON_KIND],
            required=True,
        )
        if err:
            bump_skip(err)
            return None

        shipment_type, err = self._resolve_ref(
            caches,
            ShipmentType,
            "shipment_by_name",
            "shipment_type",
            row[COL_SHIPMENT_TYPE],
            required=True,
        )
        if err:
            bump_skip(err)
            return None

        message_type, _ = self._resolve_ref(
            caches,
            MessageType,
            "message_by_name",
            "message_type",
            row[COL_MESSAGE_TYPE],
            required=False,
        )

        shipper = self._resolve_shipper(row, caches)

        volume = _parse_decimal(row[COL_VOLUME_TONS])
        turnover = _parse_decimal(row[COL_TURNOVER_TKM])
        charge = _parse_decimal(row[COL_CHARGE_RUB])

        izpod_raw = row[COL_CARGO_CODE_IZPOD]
        cargo_code_izpod = "" if izpod_raw is None else str(izpod_raw).strip()

        from core.domain.distance_belt import parse_distance_belt_midpoint

        distance_belt = (row[COL_DISTANCE_BELT] or "").strip()

        return Route(
            route_set=route_set,
            route_code=route_code,
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon,
            shipment_type=shipment_type,
            message_type=message_type,
            shipper=shipper,
            distance_belt=distance_belt,
            distance_belt_midpoint_km=parse_distance_belt_midpoint(distance_belt),
            shipment_category=(row[COL_SHIPMENT_CATEGORY] or "").strip(),
            park_type=(row[COL_PARK_TYPE] or "").strip(),
            special_container_type=(row[COL_PARK_TYPE] or "").strip(),
            # В выгрузке РЖД «Тип парка» = груженые/порожние → shipment_category;
            # «Вид спец контейнера» = универсальный/… → park_type и special_container_type.
            cargo_group_cmtp=(row[COL_CARGO_GROUP_CMTP] or "").strip(),
            cargo_code_izpod=cargo_code_izpod,
            transport_volume_tons=volume,
            freight_turnover_tkm=turnover,
            freight_charge_rub=charge,
        )
