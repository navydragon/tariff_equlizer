from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from core.domain.route_analytics.dimensions import LOADING_BASE_YEAR
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
    User,
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
            freight_charge_rub_plan_2026=Decimal("1100000.00"),
            transport_volume_tons_plan_2026=Decimal("1100.00"),
            freight_turnover_tkm_plan_2026=Decimal("5500000.00"),
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
            freight_charge_rub_plan_2026=Decimal("2200000.00"),
            transport_volume_tons_plan_2026=Decimal("2200.00"),
            freight_turnover_tkm_plan_2026=Decimal("11000000.00"),
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
            freight_charge_rub_plan_2026=Decimal("3300000.00"),
            transport_volume_tons_plan_2026=Decimal("3300.00"),
            freight_turnover_tkm_plan_2026=Decimal("16500000.00"),
            route_set=self.route_set,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
        )

    def _request(
        self,
        *,
        dimension: str,
        metric: str,
        kpi_year: int = LOADING_BASE_YEAR,
        dimension_inner: str = "none",
        parent_filter: str | None = None,
    ) -> RouteAnalyticsRequestDTO:
        return RouteAnalyticsRequestDTO(
            route_set_id=self.route_set.id,
            dimension=dimension,
            metric=metric,
            kpi_year=kpi_year,
            dimension_inner=dimension_inner,
            parent_filter=parent_filter,
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

    def test_aggregate_totals(self) -> None:
        result, errors = self.service.aggregate_totals(self.route_set.id)
        self.assertEqual(errors, [])
        assert result is not None
        self.assertEqual(result.route_set_code, "RS_ANALYTICS")
        cards_by_metric = {card.metric: card for card in result.cards}
        self.assertEqual(cards_by_metric["count"].value, Decimal("3"))
        self.assertEqual(cards_by_metric["count"].value_display, "3")
        self.assertEqual(cards_by_metric["money"].value, Decimal("6000000.00"))
        self.assertEqual(cards_by_metric["volume"].value, Decimal("6000.00"))
        self.assertEqual(cards_by_metric["turnover"].value, Decimal("30000000.00"))

    def test_aggregate_totals_missing_route_set(self) -> None:
        result, errors = self.service.aggregate_totals(999999)
        self.assertIsNone(result)
        self.assertIn("Набор маршрутов не найден", errors)

    def test_invalid_kpi_year(self) -> None:
        result, errors = self.service.aggregate_totals(self.route_set.id, kpi_year=2099)
        self.assertIsNone(result)
        self.assertIn("Некорректный kpi_year", errors)

        result, errors = self.service.aggregate(
            RouteAnalyticsRequestDTO(
                route_set_id=self.route_set.id,
                dimension="cargo_group",
                metric="money",
                kpi_year=2099,
            )
        )
        self.assertIsNone(result)
        self.assertIn("Некорректный kpi_year", errors)

    def test_excludes_ipem_model_routes_from_analytics(self) -> None:
        cargo = Cargo.objects.get(code=3001)
        origin = Station.objects.get(esr_code=300001)
        destination = Station.objects.get(esr_code=300002)
        wagon_kind = WagonKind.objects.get(code="WK3")
        shipment_type = ShipmentType.objects.get(code="ST3")
        message_type = MessageType.objects.get(code="MT3")

        Route.objects.create(
            route_set=self.route_set,
            route_code="RA-MODEL",
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            is_model=True,
            freight_charge_rub=Decimal("9000000.00"),
            transport_volume_tons=Decimal("9000.00"),
            freight_turnover_tkm=Decimal("90000000.00"),
        )

        totals, errors = self.service.aggregate_totals(self.route_set.id)
        self.assertEqual(errors, [])
        assert totals is not None
        cards_by_metric = {card.metric: card for card in totals.cards}
        self.assertEqual(cards_by_metric["count"].value, Decimal("3"))
        self.assertEqual(cards_by_metric["money"].value, Decimal("6000000.00"))
        self.assertEqual(cards_by_metric["turnover"].value, Decimal("30000000.00"))

        result, errors = self.service.aggregate(
            self._request(dimension="cargo_group", metric="count"),
        )
        self.assertEqual(errors, [])
        assert result is not None
        self.assertEqual(result.total, Decimal("3"))

    def test_inner_equals_outer_rejected(self) -> None:
        result, errors = self.service.aggregate(
            self._request(
                dimension="cargo_group",
                metric="count",
                dimension_inner="cargo_group",
            ),
        )
        self.assertIsNone(result)
        self.assertTrue(any("совпадать" in error for error in errors))

    def test_drilldown_by_parent_filter(self) -> None:
        result, errors = self.service.aggregate(
            self._request(
                dimension="cargo_group",
                metric="count",
                dimension_inner="shipper_holding",
                parent_filter="Уголь",
            ),
        )
        self.assertEqual(errors, [])
        assert result is not None
        data_rows = [row for row in result.rows if not row.is_total]
        labels = {row.label: row.value for row in data_rows}
        self.assertEqual(labels.get("Holding A"), Decimal("1"))
        self.assertEqual(labels.get("Прочие"), Decimal("1"))
        self.assertEqual(result.total, Decimal("2"))
        self.assertFalse(result.drilldown_enabled)
        self.assertEqual(result.parent_label, "Уголь")
        self.assertEqual(result.dimension, "shipper_holding")

    def test_aggregate_nested_with_subtotals(self) -> None:
        result, errors = self.service.aggregate_nested(
            self._request(
                dimension="cargo_group",
                metric="count",
                dimension_inner="shipper_holding",
            ),
        )
        self.assertEqual(errors, [])
        assert result is not None

        coal_detail = [
            row
            for row in result.rows
            if row.outer_label == "Уголь" and not row.is_subtotal and not row.is_total
        ]
        self.assertEqual(len(coal_detail), 2)

        coal_subtotal = next(
            row
            for row in result.rows
            if row.outer_label == "Уголь" and row.is_subtotal
        )
        self.assertEqual(coal_subtotal.value, Decimal("2"))
        self.assertEqual(coal_subtotal.inner_label, "ИТОГО")

        oil_subtotal = next(
            row
            for row in result.rows
            if row.outer_label == "Нефть" and row.is_subtotal
        )
        self.assertEqual(oil_subtotal.value, Decimal("1"))

        grand = next(row for row in result.rows if row.is_total)
        self.assertEqual(grand.value, Decimal("3"))
        self.assertEqual(result.dimension_inner_label, "Холдинг")

    def test_drilldown_enabled_when_inner_set(self) -> None:
        result, errors = self.service.aggregate(
            self._request(
                dimension="cargo_group",
                metric="count",
                dimension_inner="shipper_holding",
            ),
        )
        self.assertEqual(errors, [])
        assert result is not None
        self.assertTrue(result.drilldown_enabled)
        self.assertIsNone(result.parent_filter)


class RouteAnalyticsExportApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(login="ra_export_user", password="pass")
        self.client.force_login(self.user)
        self.route_set = RouteSet.objects.create(name="Export RS", code="RS_EXPORT")
        group, _ = CargoGroup.objects.get_or_create(
            code=20,
            defaults={"name": "Уголь", "position": 1},
        )
        cargo, _ = Cargo.objects.get_or_create(
            code=4001,
            defaults={"name": "Cargo Export", "cargo_group": group},
        )
        railroad, _ = RailRoad.objects.get_or_create(
            code="99",
            defaults={"name": "Road Export", "direction": "Запад"},
        )
        region, _ = Region.objects.get_or_create(
            short_name="RE",
            full_name="Region Export",
            type="область",
        )
        origin, _ = Station.objects.get_or_create(
            esr_code=400001,
            defaults={
                "short_name": "E1",
                "full_name": "Station E1",
                "region": region,
                "railroad": railroad,
            },
        )
        destination, _ = Station.objects.get_or_create(
            esr_code=400002,
            defaults={
                "short_name": "E2",
                "full_name": "Station E2",
                "region": region,
                "railroad": railroad,
            },
        )
        wagon_kind, _ = WagonKind.objects.get_or_create(
            code="WKX",
            defaults={"name": "Wagon X"},
        )
        shipment_type, _ = ShipmentType.objects.get_or_create(
            code="STX",
            defaults={"name": "Shipment X"},
        )
        message_type, _ = MessageType.objects.get_or_create(
            code="MTX",
            defaults={"name": "Внутр. перевозки"},
        )
        shipper = Shipper.objects.create(name="Shipper Export", holding="Holding X")
        Route.objects.create(
            route_set=self.route_set,
            route_code="EX-001",
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            shipper=shipper,
            freight_charge_rub=Decimal("1000000.00"),
            transport_volume_tons=Decimal("1000.00"),
            freight_turnover_tkm=Decimal("5000000.00"),
        )

    def test_export_flat_xlsx(self) -> None:
        url = reverse("route_analytics_export_api")
        response = self.client.get(
            url,
            {
                "route_set_id": self.route_set.id,
                "dimension": "cargo_group",
                "metric": "count",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "spreadsheetml.sheet",
            response["Content-Type"],
        )
        self.assertTrue(response.content[:2] == b"PK")

    def test_export_nested_xlsx(self) -> None:
        url = reverse("route_analytics_export_api")
        response = self.client.get(
            url,
            {
                "route_set_id": self.route_set.id,
                "dimension": "cargo_group",
                "dimension_inner": "shipper_holding",
                "metric": "count",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "spreadsheetml.sheet",
            response["Content-Type"],
        )
        self.assertTrue(response.content[:2] == b"PK")
