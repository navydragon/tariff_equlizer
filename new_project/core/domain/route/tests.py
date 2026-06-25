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
            is_model=True,
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

    def test_list_with_economics_filled_returns_only_model_routes(self) -> None:
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

    def test_list_with_is_model_only_returns_only_model_routes(self) -> None:
        response = self.client.get(
            reverse("route_list_api"),
            {
                "route_set_id": self.route_set.id,
                "is_model_only": "1",
                "page_size": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        ids = {item["id"] for item in data["items"]}
        self.assertEqual(ids, {self.route_with_price.id})
        self.assertTrue(data["items"][0]["is_model"])

    def test_list_includes_is_model_flag(self) -> None:
        response = self.client.get(
            reverse("route_list_api"),
            {
                "route_set_id": self.route_set.id,
                "page_size": "100",
            },
        )
        data = response.json()
        by_id = {item["id"]: item for item in data["items"]}
        self.assertTrue(by_id[self.route_with_price.id]["is_model"])
        self.assertFalse(by_id[self.route_without_price.id]["is_model"])


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
            is_model=True,
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
            is_model=True,
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

    def test_route_holding_options_api_excludes_operational_routes(self) -> None:
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
            market_price_per_ton=Decimal("1400.00"),
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


class RoutePickerCascadeApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = User.objects.create_user(login="route_picker_user", password="pass")
        self.client.force_login(self.user)

        self.route_set = RouteSet.objects.create(name="Picker cascade set", code="PICK_CAS")
        self.cargo_group_a = CargoGroup.objects.create(name="Group A", code=21, position=1)
        self.cargo_group_b = CargoGroup.objects.create(name="Group B", code=22, position=2)
        self.cargo_a = Cargo.objects.create(
            code="016101",
            name="Coal A",
            cargo_group=self.cargo_group_a,
        )
        self.cargo_b = Cargo.objects.create(
            code="016102",
            name="Coal B",
            cargo_group=self.cargo_group_b,
        )
        railroad = RailRoad.objects.create(code="91", name="Road P")
        region = Region.objects.create(
            short_name="P",
            full_name="Picker region",
            type="область",
        )
        self.origin = Station.objects.create(
            esr_code=910001,
            short_name="PA",
            full_name="Station PA",
            region=region,
            railroad=railroad,
        )
        self.destination = Station.objects.create(
            esr_code=910002,
            short_name="PB",
            full_name="Station PB",
            region=region,
            railroad=railroad,
        )
        self.wagon_kind = WagonKind.objects.create(code="WK_P", name="Wagon P")
        self.shipment_type = ShipmentType.objects.create(code="ST_P", name="Shipment P")
        self.message_internal = MessageType.objects.create(
            code="MT_INT",
            name="Внутр. перевозки",
        )
        self.message_export = MessageType.objects.create(
            code="MT_EXP",
            name="Экспорт",
        )
        self.shipper_alpha = Shipper.objects.create(
            okpo=2001,
            inn="7702000001",
            name="Shipper Alpha P",
            holding="Alpha Holding",
        )
        self.shipper_beta = Shipper.objects.create(
            okpo=2002,
            inn="7702000002",
            name="Shipper Beta P",
            holding="Beta Holding",
        )
        self.route_alpha_internal = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo_a,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_internal,
            shipper=self.shipper_alpha,
            route_code="PICK-ALPHA-INT",
            is_model=True,
            market_price_per_ton=Decimal("1200.00"),
        )
        self.route_alpha_export = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo_a,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_export,
            shipper=self.shipper_beta,
            route_code="PICK-BETA-EXP",
            is_model=True,
            market_price_per_ton=Decimal("1250.00"),
        )
        self.route_beta_internal = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo_b,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_internal,
            shipper=self.shipper_alpha,
            route_code="PICK-BETA-INT",
            is_model=True,
            market_price_per_ton=Decimal("1300.00"),
        )
        Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo_b,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_internal,
            shipper=self.shipper_beta,
            route_code="PICK-NONMODEL",
            is_model=False,
            market_price_per_ton=Decimal("1400.00"),
        )

    def test_picker_options_cargo_group(self) -> None:
        response = self.client.get(
            reverse("route_picker_options_api"),
            {
                "route_set_id": self.route_set.id,
                "dimension": "cargo_group",
                "economics_filled": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        values = {item["value"] for item in data["items"]}
        self.assertEqual(values, {"Group A", "Group B"})

    def test_picker_options_cargo_filtered_by_group(self) -> None:
        response = self.client.get(
            reverse("route_picker_options_api"),
            {
                "route_set_id": self.route_set.id,
                "dimension": "cargo",
                "cargo_group_name": "Group A",
                "economics_filled": "1",
            },
        )
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual([item["value"] for item in data["items"]], [self.cargo_a.code])

    def test_picker_options_transport_type_cargo_first_chain(self) -> None:
        response = self.client.get(
            reverse("route_picker_options_api"),
            {
                "route_set_id": self.route_set.id,
                "dimension": "transport_type",
                "cargo_group_name": "Group A",
                "cargo_code": self.cargo_a.code,
                "economics_filled": "1",
            },
        )
        data = response.json()
        self.assertTrue(data["success"])
        values = {item["value"] for item in data["items"]}
        self.assertEqual(values, {"Внутр. перевозки", "Экспорт"})

    def test_picker_options_holding_cargo_first_chain(self) -> None:
        response = self.client.get(
            reverse("route_picker_options_api"),
            {
                "route_set_id": self.route_set.id,
                "dimension": "holding",
                "cargo_group_name": "Group A",
                "cargo_code": self.cargo_a.code,
                "message_type_name": "Внутр. перевозки",
                "economics_filled": "1",
            },
        )
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(
            [item["value"] for item in data["items"]],
            ["Alpha Holding"],
        )

    def test_picker_options_holding_first_chain(self) -> None:
        transport_response = self.client.get(
            reverse("route_picker_options_api"),
            {
                "route_set_id": self.route_set.id,
                "dimension": "transport_type",
                "holding": "Alpha Holding",
                "economics_filled": "1",
            },
        )
        transport_data = transport_response.json()
        self.assertTrue(transport_data["success"])
        self.assertEqual(
            {item["value"] for item in transport_data["items"]},
            {"Внутр. перевозки"},
        )

        cargo_response = self.client.get(
            reverse("route_picker_options_api"),
            {
                "route_set_id": self.route_set.id,
                "dimension": "cargo",
                "holding": "Alpha Holding",
                "message_type_name": "Внутр. перевозки",
                "economics_filled": "1",
            },
        )
        cargo_data = cargo_response.json()
        self.assertTrue(cargo_data["success"])
        self.assertEqual(
            {item["value"] for item in cargo_data["items"]},
            {self.cargo_a.code, self.cargo_b.code},
        )

    def test_list_with_combined_cascade_filters(self) -> None:
        response = self.client.get(
            reverse("route_list_api"),
            {
                "route_set_id": self.route_set.id,
                "economics_filled": "1",
                "cargo_group_name": "Group A",
                "cargo_code": self.cargo_a.code,
                "message_type_name": "Экспорт",
                "holding": "Beta Holding",
                "page_size": "100",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        ids = {item["id"] for item in data["items"]}
        self.assertEqual(ids, {self.route_alpha_export.id})

    def test_picker_options_excludes_non_model_routes(self) -> None:
        response = self.client.get(
            reverse("route_picker_options_api"),
            {
                "route_set_id": self.route_set.id,
                "dimension": "holding",
                "economics_filled": "1",
            },
        )
        data = response.json()
        values = {item["value"] for item in data["items"]}
        self.assertNotIn("Gamma Holding", values)
        self.assertEqual(values, {"Alpha Holding", "Beta Holding"})

    def test_route_picker_options_api_query_count(self) -> None:
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                reverse("route_picker_options_api"),
                {
                    "route_set_id": self.route_set.id,
                    "dimension": "cargo_group",
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
    def test_list_sets_without_routes_count(self) -> None:
        RouteSet.objects.create(name="Alpha", code="A_TEST")
        RouteSet.objects.create(name="Beta", code="B_TEST")
        service = RouteSetService()

        result, errors = service.list_sets(include_routes_count=False)
        self.assertEqual(errors, [])
        self.assertIsNotNone(result)
        assert result is not None
        codes = {item.code for item in result.items}
        self.assertIn("A_TEST", codes)
        self.assertIn("B_TEST", codes)
        self.assertTrue(all(item.routes_count == 0 for item in result.items))

    def test_create_set_rejects_duplicate_code(self) -> None:
        RouteSet.objects.create(name="Existing", code="DUP_CODE")
        service = RouteSetService()
        _item, errors = service.create_set(
            CreateRouteSetDTO(name="New", code="DUP_CODE"),
        )
        self.assertIn("Набор с таким кодом уже существует", errors)
