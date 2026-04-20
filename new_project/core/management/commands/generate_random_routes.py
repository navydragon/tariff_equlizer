import random
from decimal import Decimal
from typing import List

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    Cargo,
    MessageType,
    Route,
    RouteSet,
    ShipmentType,
    Station,
    WagonKind,
)


class Command(BaseCommand):
    help = "Генерирует случайные маршруты Route для заданного RouteSet."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=100000,
            help="Сколько маршрутов создать (по умолчанию 100000).",
        )
        parser.add_argument(
            "--route-set-code",
            dest="route_set_code",
            required=True,
            help="Код RouteSet, в который будут добавлены маршруты.",
        )
        parser.add_argument(
            "--route-set-name",
            dest="route_set_name",
            default="",
            help="Название RouteSet, если он будет создан (по умолчанию равно коду).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Размер партии для bulk_create (по умолчанию 1000).",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Удалить существующие маршруты в данном RouteSet перед генерацией.",
        )

    def handle(self, *args, **options) -> None:
        count: int = options["count"]
        route_set_code: str = options["route_set_code"]
        route_set_name: str = options.get("route_set_name") or route_set_code
        batch_size: int = options["batch_size"]
        clear_existing: bool = bool(options.get("clear_existing"))

        if count <= 0:
            raise CommandError("Параметр --count должен быть положительным.")
        if batch_size <= 0:
            raise CommandError("Параметр --batch-size должен быть положительным.")

        self.stdout.write(
            self.style.NOTICE(
                f"Генерация {count} случайных маршрутов "
                f"в RouteSet code={route_set_code!r} (batch_size={batch_size}, "
                f"clear_existing={clear_existing})"
            )
        )

        with transaction.atomic():
            route_set, _ = RouteSet.objects.get_or_create(
                code=route_set_code,
                defaults={"name": route_set_name},
            )

            if clear_existing:
                deleted_count, _ = Route.objects.filter(route_set=route_set).delete()
                self.stdout.write(
                    self.style.WARNING(
                        f"Удалено существующих маршрутов в RouteSet {route_set.code}: "
                        f"{deleted_count}"
                    )
                )

            cargos: List[Cargo] = list(Cargo.objects.all())
            stations: List[Station] = list(
                Station.objects.select_related("railroad", "region")
            )
            wagon_kinds: List[WagonKind] = list(
                WagonKind.objects.filter(is_active=True)
            )
            shipment_types: List[ShipmentType] = list(
                ShipmentType.objects.filter(is_active=True)
            )
            message_types: List[MessageType] = list(MessageType.objects.all())

            if not cargos:
                raise CommandError("Справочник Cargo пуст. Нечего выбирать.")
            if not stations:
                raise CommandError("Справочник Station пуст. Нечего выбирать.")
            if not wagon_kinds:
                raise CommandError("Справочник WagonKind пуст. Нечего выбирать.")
            if not shipment_types:
                raise CommandError("Справочник ShipmentType пуст. Нечего выбирать.")
            if not message_types:
                raise CommandError("Справочник MessageType пуст. Нечего выбирать.")

            existing_random_codes = set(
                Route.objects.filter(route_set=route_set, route_code__startswith="RND-")
                .values_list("route_code", flat=True)
            )

            created_total = 0
            batch: List[Route] = []

            for i in range(count):
                route = self._build_random_route(
                    index=i,
                    route_set=route_set,
                    cargos=cargos,
                    stations=stations,
                    wagon_kinds=wagon_kinds,
                    shipment_types=shipment_types,
                    message_types=message_types,
                    existing_random_codes=existing_random_codes,
                )
                existing_random_codes.add(route.route_code)
                batch.append(route)

                if len(batch) >= batch_size:
                    Route.objects.bulk_create(batch, batch_size=batch_size)
                    created_total += len(batch)
                    batch.clear()

            if batch:
                Route.objects.bulk_create(batch, batch_size=batch_size)
                created_total += len(batch)

        self.stdout.write(
            self.style.SUCCESS(
                f"Генерация маршрутов завершена. "
                f"Создано {created_total} маршрутов в наборе {route_set_code!r}."
            )
        )

    def _build_random_route(
        self,
        index: int,
        route_set: RouteSet,
        cargos: List[Cargo],
        stations: List[Station],
        wagon_kinds: List[WagonKind],
        shipment_types: List[ShipmentType],
        message_types: List[MessageType],
        existing_random_codes: set[str],
    ) -> Route:
        cargo = random.choice(cargos)
        origin = random.choice(stations)
        destination = random.choice(stations)

        attempts = 0
        while destination.esr_code == origin.esr_code and attempts < 10:
            destination = random.choice(stations)
            attempts += 1

        wagon_kind = random.choice(wagon_kinds)
        shipment_type = random.choice(shipment_types)
        message_type = random.choice(message_types)

        distance_loaded_km = random.randint(50, 7000)
        distance_empty_km = random.randint(50, 7000)
        load_tons_per_wagon = Decimal(str(round(random.uniform(50, 80), 2)))

        delivery_time_loaded_days = random.randint(1, 40)
        delivery_time_empty_days = random.randint(1, 40)
        delivery_time_ops_days = random.randint(1, 5)

        rate_per_wagon_per_day = Decimal(str(round(random.uniform(5000, 20000), 2)))

        rzd_cost_loaded_per_ton = Decimal(str(round(random.uniform(500, 5000), 2)))
        rzd_cost_empty_per_ton = Decimal(str(round(random.uniform(200, 3000), 2)))
        rzd_cost_total_per_ton = (
            rzd_cost_loaded_per_ton + rzd_cost_empty_per_ton
        ).quantize(Decimal("0.01"))

        operators_cost_per_ton = Decimal(str(round(random.uniform(300, 3000), 2)))
        transshipment_cost_per_ton = Decimal(str(round(random.uniform(100, 1500), 2)))
        excise_or_duty_per_ton = Decimal(str(round(random.uniform(0, 1000), 2)))

        transport_total_cost_per_ton = (
            rzd_cost_total_per_ton
            + operators_cost_per_ton
            + transshipment_cost_per_ton
            + excise_or_duty_per_ton
        ).quantize(Decimal("0.01"))

        production_cost_per_ton = Decimal(str(round(random.uniform(500, 3000), 2)))

        total_cost_per_ton = (
            production_cost_per_ton + transport_total_cost_per_ton
        ).quantize(Decimal("0.01"))

        margin = Decimal(str(round(random.uniform(0.05, 0.3), 4)))
        market_price_per_ton = (
            total_cost_per_ton * (Decimal("1.0") + margin)
        ).quantize(Decimal("0.01"))

        base_code = f"RND-{route_set.code}-{origin.esr_code}-{destination.esr_code}-{index}"
        route_code = base_code
        suffix = 1
        while route_code in existing_random_codes:
            suffix += 1
            route_code = f"{base_code}-{suffix}"

        shipper_holding = f"Холдинг {random.randint(1, 1000)}"
        shipper = f"Грузоотправитель {random.randint(1, 1000)}"

        return Route(
            route_set=route_set,
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
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

