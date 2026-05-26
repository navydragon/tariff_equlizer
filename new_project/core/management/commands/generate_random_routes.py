import random
from decimal import Decimal
from typing import List

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

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
            # QuerySet.delete может не давать надёжной инвалидации на уровне набора
            RouteSet.objects.filter(pk=route_set.pk).update(updated_at=timezone.now())

        self.stdout.write("Загрузка справочников...")
        cargos: List[Cargo] = list(Cargo.objects.all())
        stations: List[Station] = list(
            Station.objects.select_related("railroad", "region")
        )
        wagon_kinds: List[WagonKind] = list(WagonKind.objects.filter(is_active=True))
        shipment_types: List[ShipmentType] = list(
            ShipmentType.objects.filter(is_active=True)
        )
        message_types: List[MessageType] = list(MessageType.objects.all())
        shippers: List[Shipper] = list(Shipper.objects.all())

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

        self.stdout.write(
            f"Справочники: cargo={len(cargos)}, stations={len(stations)}, "
            f"wagon_kinds={len(wagon_kinds)}, shipment_types={len(shipment_types)}, "
            f"message_types={len(message_types)}, shippers={len(shippers)}"
        )

        existing_random_codes: set[str] = set()
        if not clear_existing:
            self.stdout.write("Загрузка существующих route_code (RND-*)...")
            existing_random_codes = set(
                Route.objects.filter(
                    route_set=route_set, route_code__startswith="RND-"
                ).values_list("route_code", flat=True)
            )
            self.stdout.write(f"Уже занято кодов: {len(existing_random_codes)}")

        created_total = 0
        batch: List[Route] = []
        progress_step = max(batch_size, count // 100) if count >= 100 else batch_size

        self.stdout.write("Генерация и вставка маршрутов (прогресс ниже)...")

        for i in range(count):
            route = self._build_random_route(
                index=i,
                route_set=route_set,
                cargos=cargos,
                stations=stations,
                wagon_kinds=wagon_kinds,
                shipment_types=shipment_types,
                message_types=message_types,
                shippers=shippers,
                existing_random_codes=existing_random_codes,
            )
            existing_random_codes.add(route.route_code)
            batch.append(route)

            if len(batch) >= batch_size:
                with transaction.atomic():
                    Route.objects.bulk_create(batch, batch_size=batch_size)
                created_total += len(batch)
                batch.clear()
                if created_total % progress_step == 0 or created_total == count:
                    self.stdout.write(
                        f"  … {created_total:,} / {count:,} "
                        f"({created_total * 100 // count}%)"
                    )

        if batch:
            with transaction.atomic():
                Route.objects.bulk_create(batch, batch_size=batch_size)
            created_total += len(batch)
            self.stdout.write(f"  … {created_total:,} / {count:,} (100%)")

        # bulk_create не триггерит сигналы — обновляем версию набора вручную
        RouteSet.objects.filter(pk=route_set.pk).update(updated_at=timezone.now())

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
        shippers: List[Shipper],
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

        route_code = (
            f"RND-{route_set.code}-{origin.esr_code}-"
            f"{destination.esr_code}-{index:07d}"
        )
        if route_code in existing_random_codes:
            suffix = 1
            while True:
                candidate = f"{route_code}-{suffix}"
                if candidate not in existing_random_codes:
                    route_code = candidate
                    break
                suffix += 1

        shipper_obj = random.choice(shippers) if shippers else None

        volume = Decimal(str(round(random.uniform(100_000, 30_000_000), 4)))
        factor = Decimal(str(round(random.uniform(0.1, 2.5), 4)))
        turnover = (volume * factor * Decimal("1000")).quantize(Decimal("0.0001"))
        rate = Decimal(str(round(random.uniform(80, 400), 2)))
        charge = (turnover * rate / Decimal("1000000")).quantize(Decimal("0.01"))
        transport_volume_tons = volume
        freight_turnover_tkm = turnover
        freight_charge_rub = charge

        return Route(
            route_set=route_set,
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            shipper=shipper_obj,
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
            transport_volume_tons=transport_volume_tons,
            freight_turnover_tkm=freight_turnover_tkm,
            freight_charge_rub=freight_charge_rub,
        )

