from decimal import Decimal

from django.test import TestCase

from core.domain.route_analytics.dto import RouteAnalyticsRequestDTO
from core.domain.route_analytics.services import RouteAnalyticsService
from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Region,
    Route,
    RouteSet,
    ShipmentType,
    Shipper,
    Station,
    WagonKind,
)


class RouteAnalyticsServiceTests(TestCase):
    def setUp(self) -> None:
        self.route_set = RouteSet.objects.create(name="Analytics RS", code="RS_ANALYTICS")
        self.service = RouteAnalyticsService()
        self._create_fixtures()

    def _create_fixtures(self) -> None:
        group_a, _ = CargoGroup.objects.get_or_create(
            code=10,
            defaults={"name": "Уголь", "position": 1},
        )
        group_b, _ = CargoGroup.objects.get_or_create(
            code=11,
            defaults={"name": "Нефть", "position": 2},
        )
        cargo_a, _ = Cargo.objects.get_or_create(
            code=3001,
            defaults={"name": "Cargo A", "cargo_group": group_a},
        )
        cargo_b, _ = Cargo.objects.get_or_create(
            code=3002,
            defaults={"name": "Cargo B", "cargo_group": group_b},
        )
        railroad, _ = RailRoad.objects.get_or_create(
            code="02",
            defaults={"name": "Road", "direction": "Запад"},
        )
        region, _ = Region.objects.get_or_create(
            short_name="RA",
            full_name="Region A",
            type="область",
        )
        origin, _ = Station.objects.get_or_create(
            esr_code=300001,
            defaults={
                "short_name": "A",
                "full_name": "Station A",
                "region": region,
                "railroad": railroad,
            },
        )
        destination, _ = Station.objects.get_or_create(
            esr_code=300002,
            defaults={
                "short_name": "B",
                "full_name": "Station B",
                "region": region,
                "railroad": railroad,
            },
        )
        wagon_kind, _ = WagonKind.objects.get_or_create(
            code="WK3",
            defaults={"name": "Wagon"},
        )
        shipment_type, _ = ShipmentType.objects.get_or_create(
            code="ST3",
            defaults={"name": "Shipment"},
        )
        message_type, _ = MessageType.objects.get_or_create(
            code="MT3",
            defaults={"name": "Внутр. перевозки"},
        )
        shipper_with_holding = Shipper.objects.create(
            name="Shipper A",
            holding="Holding A",
        )
        shipper_without_holding = Shipper.objects.create(
            name="Shipper B",
            holding="",
        )

        base_kwargs = dict(
            route_set=self.route_set,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            freight_charge_rub=Decimal("1000000.00"),
            transport_volume_tons=Decimal("1000.00"),
            freight_turnover_tkm=Decimal("5000000.00"),
        )

        Route.objects.create(
            cargo=cargo_a,
            shipper=shipper_with_holding,
            route_code="RA-001",
            **base_kwargs,
        )
        Route.objects.create(
            cargo=cargo_a,
            shipper=shipper_without_holding,
            route_code="RA-002",
            freight_charge_rub=Decimal("2000000.00"),
            transport_volume_tons=Decimal("2000.00"),
            freight_turnover_tkm=Decimal("10000000.00"),
            route_set=self.route_set,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
        )
        Route.objects.create(
            cargo=cargo_b,
            shipper=shipper_with_holding,
            route_code="RA-003",
            freight_charge_rub=Decimal("3000000.00"),
            transport_volume_tons=Decimal("3000.00"),
            freight_turnover_tkm=Decimal("15000000.00"),
            route_set=self.route_set,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
        )

    def _request(self, *, dimension: str, metric: str) -> RouteAnalyticsRequestDTO:
        return RouteAnalyticsRequestDTO(
            route_set_id=self.route_set.id,
            dimension=dimension,
            metric=metric,
        )

    def test_count_by_cargo_group(self) -> None:
        result, errors = self.service.aggregate(self._request(dimension="cargo_group", metric="count"))
        self.assertEqual(errors, [])
        assert result is not None
        data_rows = [row for row in result.rows if not row.is_total]
        self.assertEqual(len(data_rows), 2)
        coal = next(row for row in data_rows if row.label == "Уголь")
        self.assertEqual(coal.value, Decimal("2"))
        self.assertEqual(result.total, Decimal("3"))

    def test_money_by_cargo_group(self) -> None:
        result, errors = self.service.aggregate(self._request(dimension="cargo_group", metric="money"))
        self.assertEqual(errors, [])
        assert result is not None
        coal = next(row for row in result.rows if row.label == "Уголь" and not row.is_total)
        oil = next(row for row in result.rows if row.label == "Нефть" and not row.is_total)
        self.assertEqual(coal.value, Decimal("3000000.00"))
        self.assertEqual(oil.value, Decimal("3000000.00"))
        self.assertEqual(result.total, Decimal("6000000.00"))

    def test_empty_holding_maps_to_misc(self) -> None:
        result, errors = self.service.aggregate(
            self._request(dimension="shipper_holding", metric="count"),
        )
        self.assertEqual(errors, [])
        assert result is not None
        labels = {row.label for row in result.rows if not row.is_total}
        self.assertIn("Holding A", labels)
        self.assertIn("Прочие", labels)

    def test_invalid_dimension(self) -> None:
        result, errors = self.service.aggregate(
            RouteAnalyticsRequestDTO(
                route_set_id=self.route_set.id,
                dimension="unknown",
                metric="count",
            )
        )
        self.assertIsNone(result)
        self.assertTrue(errors)

    def test_invalid_metric(self) -> None:
        result, errors = self.service.aggregate(
            RouteAnalyticsRequestDTO(
                route_set_id=self.route_set.id,
                dimension="cargo_group",
                metric="unknown",
            )
        )
        self.assertIsNone(result)
        self.assertTrue(errors)

    def test_missing_route_set(self) -> None:
        result, errors = self.service.aggregate(
            RouteAnalyticsRequestDTO(
                route_set_id=999999,
                dimension="cargo_group",
                metric="count",
            )
        )
        self.assertIsNone(result)
        self.assertIn("Набор маршрутов не найден", errors)
