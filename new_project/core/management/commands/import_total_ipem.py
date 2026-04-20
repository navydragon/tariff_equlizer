import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    Cargo,
    MessageType,
    RailRoad,
    Route,
    RouteSet,
    ShipmentType,
    Station,
    WagonKind,
)

try:
    from rapidfuzz import fuzz, process as rf_process
except ImportError:  # pragma: no cover
    fuzz = None
    rf_process = None


@dataclass
class CargoIndexItem:
    name: str
    cargo: Cargo


@dataclass
class StationIndexItem:
    full_name: str
    railroad_code: str
    station: Station


class Command(BaseCommand):
    help = (
        "Импортирует маршруты из CSV-файла total_ipem "
        "в модель Route с проверкой связей и логированием ошибок по полю index."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--file",
            dest="file_path",
            required=True,
            help="Путь к CSV-файлу total_ipem (разделитель ';')",
        )
        parser.add_argument(
            "--route-set-code",
            dest="route_set_code",
            required=True,
            help="Код RouteSet, в который будут импортированы маршруты",
        )
        parser.add_argument(
            "--route-set-name",
            dest="route_set_name",
            default="",
            help="Название RouteSet (если не существует). По умолчанию равно коду.",
        )
        parser.add_argument(
            "--similarity-threshold",
            dest="similarity_threshold",
            type=int,
            default=90,
            help="Порог схожести для нечеткого поиска Cargo/Station (0-100). "
            "По умолчанию 90.",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Только проверить CSV и вывести отчёт, без записи в базу данных.",
        )

    def handle(self, *args, **options) -> None:
        file_arg = options["file_path"]
        route_set_code: str = options["route_set_code"]
        route_set_name: str = options.get("route_set_name") or ""
        similarity_threshold: int = options.get("similarity_threshold") or 90
        dry_run: bool = bool(options.get("dry_run"))

        if not 0 <= similarity_threshold <= 100:
            raise CommandError("similarity-threshold должен быть в диапазоне 0..100")

        if fuzz is None or rf_process is None:
            raise CommandError(
                "Библиотека rapidfuzz не установлена. "
                "Добавьте rapidfuzz в зависимости проекта."
            )

        csv_path = Path(file_arg)
        if not csv_path.is_absolute():
            csv_path = Path(settings.BASE_DIR) / csv_path

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        if not route_set_name:
            route_set_name = route_set_code

        self.stdout.write(
            self.style.NOTICE(
                f"Старт импорта total_ipem из {csv_path} в RouteSet "
                f"code={route_set_code!r} (dry_run={dry_run})"
            )
        )

        with transaction.atomic():
            route_set, _ = RouteSet.objects.get_or_create(
                code=route_set_code,
                defaults={"name": route_set_name},
            )

            cargo_index = self._build_cargo_index()
            station_index = self._build_station_index()
            wagon_by_name = self._build_simple_dict(WagonKind.objects.all())
            shipment_by_name = self._build_simple_dict(ShipmentType.objects.all())
            message_by_name = self._build_simple_dict(MessageType.objects.all())

            (
                total_rows,
                created_count,
                skipped_count,
                error_items,
            ) = self._import_routes_from_csv(
                csv_path=csv_path,
                route_set=route_set,
                similarity_threshold=similarity_threshold,
                dry_run=dry_run,
                cargo_index=cargo_index,
                station_index=station_index,
                wagon_by_name=wagon_by_name,
                shipment_by_name=shipment_by_name,
                message_by_name=message_by_name,
            )

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "Импорт total_ipem завершён. "
                f"Всего строк: {total_rows}, создано маршрутов: {created_count}, "
                f"пропущено: {skipped_count}."
            )
        )

        if error_items:
            self.stdout.write(self.style.WARNING("Список ошибок импорта:"))
            for index_value, reasons in error_items:
                joined = "; ".join(reasons)
                self.stdout.write(f"index={index_value}: {joined}")

    def _normalize_name(self, value: str) -> str:
        return (value or "").strip().casefold()

    def _build_cargo_index(self) -> List[CargoIndexItem]:
        items: List[CargoIndexItem] = []
        for cargo in Cargo.objects.all():
            items.append(CargoIndexItem(name=self._normalize_name(cargo.name), cargo=cargo))
        return items

    def _build_station_index(self) -> List[StationIndexItem]:
        items: List[StationIndexItem] = []
        stations = Station.objects.select_related("railroad")
        for st in stations:
            railroad_code = st.railroad.code if st.railroad_id else ""
            items.append(
                StationIndexItem(
                    full_name=self._normalize_name(st.full_name),
                    railroad_code=(railroad_code or "").strip(),
                    station=st,
                )
            )
        return items

    def _build_simple_dict(self, qs: Iterable[Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for obj in qs:
            key = self._normalize_name(getattr(obj, "name", ""))
            if key:
                result[key] = obj
        return result

    def _match_cargo_fuzzy(
        self,
        raw_name: str,
        cargo_index: List[CargoIndexItem],
        similarity_threshold: int,
    ) -> Optional[Cargo]:
        name_norm = self._normalize_name(raw_name)
        if not name_norm:
            return None

        choices = [item.name for item in cargo_index]
        best = rf_process.extractOne(
            name_norm,
            choices,
            scorer=fuzz.WRatio,
            score_cutoff=similarity_threshold,
        )
        if not best:
            return None

        _, _, idx = best
        if idx is None:
            return None
        return cargo_index[idx].cargo

    def _match_station_by_esr_or_fuzzy(
        self,
        raw_esr: str,
        raw_station_name: str,
        raw_railroad_code: str,
        station_index: List[StationIndexItem],
        similarity_threshold: int,
    ) -> Optional[Station]:
        esr_clean = (raw_esr or "").replace(" ", "")
        if esr_clean:
            try:
                esr_code = int(esr_clean)
                try:
                    return Station.objects.get(esr_code=esr_code)
                except Station.DoesNotExist:
                    pass
            except ValueError:
                pass

        name_norm = self._normalize_name(raw_station_name)
        if not name_norm:
            return None

        railroad_code = (raw_railroad_code or "").strip()
        candidates = station_index
        if railroad_code:
            candidates = [
                item for item in station_index if item.railroad_code == railroad_code
            ]

        if not candidates:
            return None

        choices = [item.full_name for item in candidates]
        best = rf_process.extractOne(
            name_norm,
            choices,
            scorer=fuzz.WRatio,
            score_cutoff=similarity_threshold,
        )
        if not best:
            return None

        _, _, idx = best
        if idx is None:
            return None
        return candidates[idx].station

    def _import_routes_from_csv(
        self,
        csv_path: Path,
        route_set: RouteSet,
        similarity_threshold: int,
        dry_run: bool,
        cargo_index: List[CargoIndexItem],
        station_index: List[StationIndexItem],
        wagon_by_name: Dict[str, WagonKind],
        shipment_by_name: Dict[str, ShipmentType],
        message_by_name: Dict[str, MessageType],
    ) -> Tuple[int, int, int, List[Tuple[Any, List[str]]]]:
        """
        Читает CSV и создаёт маршруты. Возвращает:
        (общее число строк, создано, пропущено, список (index, [ошибки])).
        """
        from decimal import Decimal, InvalidOperation

        total_rows = 0
        created_count = 0
        skipped_count = 0
        error_items: List[Tuple[Any, List[str]]] = []

        with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")

            expected_fields = {
                "index",
                "Груз",
                "Холдинг грузоотправителя",
                "Грузоотправитель",
                "Дорога отправления",
                "Станция отправления",
                "Код ЕСР станции отправления",
                "Дорога назначения",
                "Станция назначения",
                "Код ЕСР станции назначения",
                "КЛЮЧ_КОД_МАРШРУТА",
                "Полувагоны",
            }

            if not reader.fieldnames:
                raise CommandError("CSV не содержит заголовка")

            missing = expected_fields.difference(reader.fieldnames)
            if missing:
                # Не все поля строго обязательны, но базовый заголовок должен совпадать.
                self.stderr.write(
                    self.style.WARNING(
                        "Предупреждение: в заголовке CSV отсутствуют поля: "
                        f"{', '.join(sorted(missing))}. Импорт всё равно будет выполнен."
                    )
                )

            for row in reader:
                total_rows += 1
                index_value = row.get("index")
                reasons: List[str] = []

                raw_cargo_name = (row.get("Груз") or "").strip()
                cargo = self._match_cargo_fuzzy(
                    raw_cargo_name, cargo_index, similarity_threshold
                )
                if cargo is None:
                    reasons.append(f"Не найден груз по имени '{raw_cargo_name}'")

                origin_station = self._match_station_by_esr_or_fuzzy(
                    raw_esr=row.get("Код ЕСР станции отправления") or "",
                    raw_station_name=row.get("Станция отправления") or "",
                    raw_railroad_code=row.get("Дорога отправления") or "",
                    station_index=station_index,
                    similarity_threshold=similarity_threshold,
                )
                if origin_station is None:
                    reasons.append("Не найдена станция отправления")

                destination_station = self._match_station_by_esr_or_fuzzy(
                    raw_esr=row.get("Код ЕСР станции назначения") or "",
                    raw_station_name=row.get("Станция назначения") or "",
                    raw_railroad_code=row.get("Дорога назначения") or "",
                    station_index=station_index,
                    similarity_threshold=similarity_threshold,
                )
                if destination_station is None:
                    reasons.append("Не найдена станция назначения")

                wagon_raw = (row.get("Род вагона") or "").strip()
                wagon = wagon_by_name.get(self._normalize_name(wagon_raw))
                if wagon is None:
                    reasons.append(f"Не найден Род вагона '{wagon_raw}'")

                shipment_raw = (row.get("Тип отправки") or "").strip()
                shipment = shipment_by_name.get(self._normalize_name(shipment_raw))
                if shipment is None:
                    reasons.append(f"Не найден Тип отправки '{shipment_raw}'")

                # Тип сообщения сопоставляем по колонке "vid" из CSV
                message_raw = (row.get("vid") or "").strip()
                message: Optional[MessageType] = None
                if message_raw:
                    message = message_by_name.get(self._normalize_name(message_raw))
                    if message is None:
                        reasons.append(f"Не найден Тип сообщения '{message_raw}'")

                def _parse_int(field: str) -> Optional[int]:
                    raw = (row.get(field) or "").replace(" ", "")
                    if not raw:
                        return None
                    try:
                        return int(raw)
                    except ValueError:
                        reasons.append(f"Поле '{field}' должно быть целым числом")
                        return None

                def _parse_decimal(field: str) -> Optional[Decimal]:
                    raw = (row.get(field) or "").strip()
                    if not raw:
                        return None
                    try:
                        return Decimal(raw.replace(" ", "").replace(",", "."))
                    except (InvalidOperation, ValueError):
                        reasons.append(f"Поле '{field}' должно быть числом")
                        return None

                distance_loaded_km = _parse_int("Расстояние перевозки (гружёный рейс), км")
                distance_empty_km = _parse_int("Расстояние перевозки (порожний рейс), км")

                load_tons_per_wagon = _parse_decimal("Загрузка в вагон, т.")

                delivery_time_loaded_days = _parse_int("Срок доставки, гружёный рейс")
                delivery_time_empty_days = _parse_int("Срок доставки,порожний рейс")
                delivery_time_ops_days = _parse_int("Срок доставки, погр./выгр.")

                rate_per_wagon_per_day = _parse_decimal(
                    "Ставка на вагон, руб. за вагон в сутки"
                )
                rzd_cost_loaded_per_ton = _parse_decimal(
                    'Расходы по оплате услуг ОАО "РЖД", руб. за тонну (груженый пробег)'
                )
                rzd_cost_empty_per_ton = _parse_decimal(
                    'Расходы по оплате услуг ОАО "РЖД", руб. за тонну (порожний пробег)'
                )
                rzd_cost_total_per_ton = _parse_decimal(
                    'Расходы по оплате услуг ОАО "РЖД", руб. за тонну (итого)'
                )
                operators_cost_per_ton = _parse_decimal(
                    "Расходы по оплате услуг операторов_2024, руб. за тонну"
                )
                transshipment_cost_per_ton = _parse_decimal(
                    "Расходы на перевалку_2024, руб. за тонну"
                )
                excise_or_duty_per_ton = _parse_decimal("Акциз/пошлина")
                transport_total_cost_per_ton = _parse_decimal(
                    "Общие транспортные расходы, руб. за тонну"
                )
                production_cost_per_ton = _parse_decimal(
                    "Себестоимость добычи/производства, руб. т."
                )
                total_cost_per_ton = _parse_decimal("Общие расходы, руб. за тонну")
                market_price_per_ton = _parse_decimal(
                    "Стоимость 1 тонны на рынке, руб./т."
                )

                route_code = (row.get("КЛЮЧ_КОД_МАРШРУТА") or "").strip()
                shipper_holding = (row.get("Холдинг грузоотправителя") or "").strip()
                shipper = (row.get("Грузоотправитель") or "").strip()

                if not route_code:
                    reasons.append("Пустой КЛЮЧ_КОД_МАРШРУТА")

                if Route.objects.filter(route_set=route_set, route_code=route_code).exists():
                    reasons.append(
                        f"Маршрут с route_code='{route_code}' уже существует в данном RouteSet"
                    )

                if reasons:
                    skipped_count += 1
                    error_items.append((index_value, reasons))
                    continue

                if dry_run:
                    created_count += 1
                    continue

                Route.objects.create(
                    route_set=route_set,
                    cargo=cargo,
                    origin_station=origin_station,
                    destination_station=destination_station,
                    wagon_kind=wagon,
                    shipment_type=shipment,
                    message_type=message,
                    shipper_holding=shipper_holding,
                    shipper=shipper,
                    route_code=route_code,
                    distance_loaded_km=distance_loaded_km,
                    distance_empty_km=distance_empty_km,
                    load_tons_per_wagon=load_tons_per_wagon,
                    delivery_time_loaded_days=delivery_time_loaded_days,
                    delivery_time_empty_days=delivery_time_empty_days,
                    delivery_time_ops_days=delivery_time_ops_days,
                    rate_per_wagon_per_day=rate_per_wagon_per_day,
                    rzd_cost_loaded_per_ton=rzd_cost_loaded_per_ton,
                    rzd_cost_empty_per_ton=rzd_cost_empty_per_ton,
                    rzd_cost_total_per_ton=rzd_cost_total_per_ton,
                    operators_cost_per_ton=operators_cost_per_ton,
                    transshipment_cost_per_ton=transshipment_cost_per_ton,
                    excise_or_duty_per_ton=excise_or_duty_per_ton,
                    transport_total_cost_per_ton=transport_total_cost_per_ton,
                    production_cost_per_ton=production_cost_per_ton,
                    total_cost_per_ton=total_cost_per_ton,
                    market_price_per_ton=market_price_per_ton,
                )

                created_count += 1

        return total_rows, created_count, skipped_count, error_items


