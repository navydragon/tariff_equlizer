import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.domain.route.dto import CreateRouteSetDTO, RouteWriteDTO
from core.domain.route.services import RouteSetService
from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Region,
    Route,
    RouteSet,
    Shipper,
    ShipmentType,
    Station,
    WagonKind,
)

User = get_user_model()


class RouteTransportWorkApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(login="route_api_user", password="pass")
        self.client.force_login(self.user)

        self.route_set = RouteSet.objects.create(name="Test set", code="TST_RT")
        cargo_group = CargoGroup.objects.create(name="Group", code=10, position=1)
        self.cargo = Cargo.objects.create(
            code=3001,
            name="Test cargo",
            cargo_group=cargo_group,
        )
        railroad = RailRoad.objects.create(code="99", name="Road")
        region = Region.objects.create(
            short_name="T",
            full_name="Test region",
            type="область",
        )
        self.origin = Station.objects.create(
            esr_code=300001,
            short_name="A",
            full_name="Station A",
            region=region,
            railroad=railroad,
        )
        self.destination = Station.objects.create(
            esr_code=300002,
            short_name="B",
            full_name="Station B",
            region=region,
            railroad=railroad,
        )
        self.wagon_kind = WagonKind.objects.create(code="WK_T", name="Wagon")
        self.shipment_type = ShipmentType.objects.create(code="ST_T", name="Shipment")
        self.message_type = MessageType.objects.create(
            code="MT_T",
            name="Внутр. перевозки",
        )

    def _base_payload(self) -> dict:
        return {
            "route_set_id": self.route_set.id,
            "cargo_code": self.cargo.code,
            "origin_esr_code": self.origin.esr_code,
            "destination_esr_code": self.destination.esr_code,
            "wagon_kind_id": self.wagon_kind.id,
            "shipment_type_id": self.shipment_type.id,
            "message_type_id": self.message_type.id,
            "route_code": "API-TW-001",
        }

    def test_create_route_with_transport_work_indicators(self) -> None:
        payload = {
            **self._base_payload(),
            "transport_volume_tons": "12500000",
            "freight_turnover_tkm": "18750000000",
            "freight_charge_rub": "1500250",
        }
        response = self.client.post(
            reverse("route_create_api"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])
        item = data["item"]
        self.assertEqual(item["transport_volume_tons"], "12500000")
        self.assertEqual(item["freight_turnover_tkm"], "18750000000")
        self.assertEqual(item["freight_charge_rub"], "1500250")

    def test_create_route_without_transport_work_indicators(self) -> None:
        payload = self._base_payload()
        payload["route_code"] = "API-TW-002"
        response = self.client.post(
            reverse("route_create_api"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        item = response.json()["item"]
        self.assertIsNone(item["transport_volume_tons"])
        self.assertIsNone(item["freight_turnover_tkm"])
        self.assertIsNone(item["freight_charge_rub"])

    def test_update_distance_does_not_change_transport_work_indicators(self) -> None:
        route = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            route_code="API-TW-003",
            distance_loaded_km=100,
            transport_volume_tons=Decimal("5500000"),
            freight_turnover_tkm=Decimal("7250000000"),
            freight_charge_rub=Decimal("900000"),
        )

        update_payload = {
            **self._base_payload(),
            "route_code": route.route_code,
            "distance_loaded_km": "999",
        }
        response = self.client.post(
            reverse("route_update_api", kwargs={"pk": route.id}),
            data=json.dumps(update_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()["item"]
        self.assertEqual(item["distance_loaded_km"], 999)
        self.assertEqual(Decimal(item["transport_volume_tons"]), Decimal("5500000"))
        self.assertEqual(Decimal(item["freight_turnover_tkm"]), Decimal("7250000000"))
        self.assertEqual(Decimal(item["freight_charge_rub"]), Decimal("900000"))


class RouteListEconomicsFilterApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(login="route_econ_filter_user", password="pass")
        self.client.force_login(self.user)

        self.route_set = RouteSet.objects.create(name="Economics filter set", code="ECO_FLT")
        cargo_group = CargoGroup.objects.create(name="Group", code=12, position=1)
        self.cargo = Cargo.objects.create(
            code=3002,
            name="Filter cargo",
            cargo_group=cargo_group,
        )
        railroad = RailRoad.objects.create(code="98", name="Road")
        region = Region.objects.create(
            short_name="T",
            full_name="Test region",
            type="область",
        )
        self.origin = Station.objects.create(
            esr_code=300011,
            short_name="A",
            full_name="Station A",
            region=region,
            railroad=railroad,
        )
        self.destination = Station.objects.create(
            esr_code=300012,
            short_name="B",
            full_name="Station B",
            region=region,
            railroad=railroad,
        )
        self.wagon_kind = WagonKind.objects.create(code="WK_E", name="Wagon")
        self.shipment_type = ShipmentType.objects.create(code="ST_E", name="Shipment")
        self.message_type = MessageType.objects.create(
            code="MT_E",
            name="Внутр. перевозки",
        )

        self.route_with_price = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            route_code="ECO-WITH-PRICE",
            market_price_per_ton=Decimal("1500.00"),
        )
        self.route_without_price = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            route_code="ECO-NO-PRICE",
        )

    def test_list_with_economics_filled_returns_only_routes_with_market_price(self) -> None:
        response = self.client.get(
            reverse("route_list_api"),
            {
                "route_set_id": self.route_set.id,
                "economics_filled": "1",
                "page_size": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        ids = {item["id"] for item in data["items"]}
        self.assertEqual(ids, {self.route_with_price.id})

    def test_list_without_economics_filled_returns_all_routes(self) -> None:
        response = self.client.get(
            reverse("route_list_api"),
            {
                "route_set_id": self.route_set.id,
                "page_size": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        ids = {item["id"] for item in data["items"]}
        self.assertEqual(
            ids,
            {self.route_with_price.id, self.route_without_price.id},
        )


class RouteListHoldingFilterApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(login="route_holding_filter_user", password="pass")
        self.client.force_login(self.user)

        self.route_set = RouteSet.objects.create(name="Holding filter set", code="HOLD_FLT")
        cargo_group = CargoGroup.objects.create(name="Group H", code=13, position=1)
        self.cargo = Cargo.objects.create(
            code=3003,
            name="Holding cargo",
            cargo_group=cargo_group,
        )
        railroad = RailRoad.objects.create(code="97", name="Road H")
        region = Region.objects.create(
            short_name="H",
            full_name="Holding region",
            type="область",
        )
        self.origin = Station.objects.create(
            esr_code=300021,
            short_name="HA",
            full_name="Station HA",
            region=region,
            railroad=railroad,
        )
        self.destination = Station.objects.create(
            esr_code=300022,
            short_name="HB",
            full_name="Station HB",
            region=region,
            railroad=railroad,
        )
        self.wagon_kind = WagonKind.objects.create(code="WK_H", name="Wagon H")
        self.shipment_type = ShipmentType.objects.create(code="ST_H", name="Shipment H")
        self.message_type = MessageType.objects.create(
            code="MT_H",
            name="Внутр. перевозки H",
        )
        self.shipper_alpha = Shipper.objects.create(
            okpo=1001,
            inn="7701000001",
            name="Shipper Alpha",
            holding="Alpha Holding",
        )
        self.shipper_beta = Shipper.objects.create(
            okpo=1002,
            inn="7701000002",
            name="Shipper Beta",
            holding="Beta Holding",
        )
        self.route_alpha = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            shipper=self.shipper_alpha,
            route_code="HOLD-ALPHA",
            market_price_per_ton=Decimal("1200.00"),
        )
        self.route_beta = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            shipper=self.shipper_beta,
            route_code="HOLD-BETA",
            market_price_per_ton=Decimal("1300.00"),
        )

    def test_list_with_holding_filter(self) -> None:
        response = self.client.get(
            reverse("route_list_api"),
            {
                "route_set_id": self.route_set.id,
                "economics_filled": "1",
                "holding": "Alpha Holding",
                "page_size": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        ids = {item["id"] for item in data["items"]}
        self.assertEqual(ids, {self.route_alpha.id})
        self.assertIn("elapsed_ms", data)

    def test_route_list_api_query_count(self) -> None:
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                reverse("route_list_api"),
                {
                    "route_set_id": self.route_set.id,
                    "economics_filled": "1",
                    "holding": "Alpha Holding",
                    "page_size": "20",
                    "include_total": "0",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        route_queries = [
            q for q in ctx.captured_queries if '"core_route"' in q["sql"]
        ]
        self.assertEqual(len(route_queries), 1)

    def test_route_holding_options_api(self) -> None:
        response = self.client.get(
            reverse("route_holding_options_api"),
            {
                "route_set_id": self.route_set.id,
                "economics_filled": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        values = {item["value"] for item in data["items"]}
        self.assertEqual(values, {"Alpha Holding", "Beta Holding"})
        self.assertIn("elapsed_ms", data)

        search_response = self.client.get(
            reverse("route_holding_options_api"),
            {
                "route_set_id": self.route_set.id,
                "economics_filled": "1",
                "search": "alpha",
            },
        )
        search_data = search_response.json()
        self.assertTrue(search_data["success"])
        self.assertEqual(
            [item["value"] for item in search_data["items"]],
            ["Alpha Holding"],
        )

    def test_route_holding_options_api_excludes_routes_without_market_price(self) -> None:
        Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            shipper=Shipper.objects.create(
                okpo=1003,
                inn="7701000003",
                name="Shipper Gamma",
                holding="Gamma Holding",
            ),
            route_code="HOLD-GAMMA",
        )
        response = self.client.get(
            reverse("route_holding_options_api"),
            {
                "route_set_id": self.route_set.id,
                "economics_filled": "1",
            },
        )
        data = response.json()
        values = {item["value"] for item in data["items"]}
        self.assertNotIn("Gamma Holding", values)

    def test_route_holding_options_api_query_count(self) -> None:
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                reverse("route_holding_options_api"),
                {
                    "route_set_id": self.route_set.id,
                    "economics_filled": "1",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        route_queries = [
            q for q in ctx.captured_queries if '"core_route"' in q["sql"]
        ]
        self.assertEqual(len(route_queries), 1)


class RouteWriteDTOTests(TestCase):
    def setUp(self) -> None:
        self.route_set = RouteSet.objects.create(name="DTO set", code="DTO_RS")
        cargo_group = CargoGroup.objects.create(name="G", code=11, position=1)
        self.cargo = Cargo.objects.create(code=4001, name="Cargo", cargo_group=cargo_group)
        railroad = RailRoad.objects.create(code="88", name="RR")
        region = Region.objects.create(short_name="R", full_name="Reg", type="область")
        self.origin = Station.objects.create(
            esr_code=400001,
            short_name="O",
            full_name="Origin",
            region=region,
            railroad=railroad,
        )
        self.destination = Station.objects.create(
            esr_code=400002,
            short_name="D",
            full_name="Dest",
            region=region,
            railroad=railroad,
        )
        self.wagon_kind = WagonKind.objects.create(code="WK_D", name="W")
        self.shipment_type = ShipmentType.objects.create(code="ST_D", name="S")

    def test_from_request_data_parses_transport_work(self) -> None:
        write_dto, errors = RouteWriteDTO.from_request_data(
            {
                "route_set_id": self.route_set.id,
                "cargo_code": self.cargo.code,
                "origin_esr_code": self.origin.esr_code,
                "destination_esr_code": self.destination.esr_code,
                "wagon_kind_id": self.wagon_kind.id,
                "shipment_type_id": self.shipment_type.id,
                "transport_volume_tons": "1500000",
                "freight_turnover_tkm": "",
            }
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(write_dto)
        assert write_dto is not None
        self.assertEqual(write_dto.payload["transport_volume_tons"], Decimal("1500000"))
        self.assertIsNone(write_dto.payload["freight_turnover_tkm"])


class RouteSetServiceTests(TestCase):
    def test_create_set_rejects_duplicate_code(self) -> None:
        RouteSet.objects.create(name="Existing", code="DUP_CODE")
        service = RouteSetService()
        _item, errors = service.create_set(
            CreateRouteSetDTO(name="New", code="DUP_CODE"),
        )
        self.assertIn("Набор с таким кодом уже существует", errors)
