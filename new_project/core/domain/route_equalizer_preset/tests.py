from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.domain.route_equalizer_preset.dto import (
    SaveEqualizerPresetRequestDTO,
    SetEqualizerVariantRequestDTO,
    parse_save_request,
    parse_variant_request,
)
from core.domain.route_equalizer_preset.services import RouteEqualizerPresetService
from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Region,
    Route,
    RouteEqualizerPreset,
    RouteSet,
    ShipmentType,
    Station,
    WagonKind,
)

User = get_user_model()


class RouteEqualizerPresetServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(login="eq_preset_user", password="pass")
        self.route_set = RouteSet.objects.create(name="RS", code="RS_EQ_PRESET")
        self.route = self._create_route()
        self.service = RouteEqualizerPresetService()

    def _create_route(self) -> Route:
        cargo_group, _ = CargoGroup.objects.get_or_create(
            code=1,
            defaults={"name": "Group", "position": 1},
        )
        cargo, _ = Cargo.objects.get_or_create(
            code=3001,
            defaults={"name": "Cargo 3001", "cargo_group": cargo_group},
        )
        railroad, _ = RailRoad.objects.get_or_create(
            code="01",
            defaults={"name": "Road"},
        )
        region, _ = Region.objects.get_or_create(
            short_name="R",
            full_name="Region",
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
            code="MT_EQ",
            defaults={"name": "Внутр. перевозки"},
        )
        return Route.objects.create(
            route_set=self.route_set,
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            route_code="RC-EQ-001",
            production_cost_per_ton=Decimal("500.00"),
        )

    def test_get_preset_defaults_when_missing(self) -> None:
        result, errors = self.service.get_preset(
            user_id=self.user.id,
            route_id=self.route.id,
        )

        self.assertEqual(errors, [])
        assert result is not None
        self.assertEqual(result.variant, RouteEqualizerPreset.Variant.BASE)
        self.assertFalse(result.has_saved)
        self.assertEqual(result.overrides, {})

    def test_save_and_get_preset(self) -> None:
        request_dto = SaveEqualizerPresetRequestDTO(
            route_id=self.route.id,
            overrides={"cost": {2026: Decimal("800.00")}},
        )
        saved, errors = self.service.save_preset(
            user_id=self.user.id,
            request_dto=request_dto,
        )

        self.assertEqual(errors, [])
        assert saved is not None
        self.assertEqual(saved.variant, RouteEqualizerPreset.Variant.USER)
        self.assertTrue(saved.has_saved)
        self.assertEqual(saved.overrides["cost"]["2026"], "800.00")

        loaded, load_errors = self.service.get_preset(
            user_id=self.user.id,
            route_id=self.route.id,
        )
        self.assertEqual(load_errors, [])
        assert loaded is not None
        self.assertEqual(loaded.variant, RouteEqualizerPreset.Variant.USER)
        self.assertEqual(loaded.overrides, saved.overrides)

    def test_save_upserts_existing_preset(self) -> None:
        first = SaveEqualizerPresetRequestDTO(
            route_id=self.route.id,
            overrides={"cost": {2026: Decimal("700.00")}},
        )
        second = SaveEqualizerPresetRequestDTO(
            route_id=self.route.id,
            overrides={"oper": {2027: Decimal("120.00")}},
        )

        self.service.save_preset(user_id=self.user.id, request_dto=first)
        self.service.save_preset(user_id=self.user.id, request_dto=second)

        preset = RouteEqualizerPreset.objects.get(
            user_id=self.user.id,
            route_id=self.route.id,
        )
        self.assertEqual(preset.variant, RouteEqualizerPreset.Variant.USER)
        self.assertEqual(preset.overrides["oper"]["2027"], "120.00")
        self.assertNotIn("cost", preset.overrides)

    def test_set_variant_to_base_keeps_saved_overrides(self) -> None:
        self.service.save_preset(
            user_id=self.user.id,
            request_dto=SaveEqualizerPresetRequestDTO(
                route_id=self.route.id,
                overrides={"cost": {2026: Decimal("800.00")}},
            ),
        )

        result, errors = self.service.set_variant(
            user_id=self.user.id,
            request_dto=SetEqualizerVariantRequestDTO(
                route_id=self.route.id,
                variant=RouteEqualizerPreset.Variant.BASE,
            ),
        )

        self.assertEqual(errors, [])
        assert result is not None
        self.assertEqual(result.variant, RouteEqualizerPreset.Variant.BASE)
        self.assertTrue(result.has_saved)

        preset = RouteEqualizerPreset.objects.get(
            user_id=self.user.id,
            route_id=self.route.id,
        )
        self.assertEqual(preset.overrides["cost"]["2026"], "800.00")

    def test_set_variant_to_user_without_saved_preset_fails(self) -> None:
        result, errors = self.service.set_variant(
            user_id=self.user.id,
            request_dto=SetEqualizerVariantRequestDTO(
                route_id=self.route.id,
                variant=RouteEqualizerPreset.Variant.USER,
            ),
        )

        self.assertIsNone(result)
        self.assertEqual(errors, ["Пользовательский вариант не сохранён"])

    def test_get_preset_for_unknown_route(self) -> None:
        result, errors = self.service.get_preset(
            user_id=self.user.id,
            route_id=999999,
        )

        self.assertIsNone(result)
        self.assertEqual(errors, ["Маршрут не найден"])

    def test_parse_save_request_rejects_invalid_keys(self) -> None:
        dto, errors = parse_save_request(
            route_id=self.route.id,
            overrides_raw={"unknown": {"2026": "1"}},
        )

        self.assertIsNone(dto)
        self.assertEqual(errors, ["Нет значений для сохранения"])

    def test_parse_variant_request_rejects_invalid_variant(self) -> None:
        dto, errors = parse_variant_request(
            route_id=self.route.id,
            variant="custom",
        )

        self.assertIsNone(dto)
        self.assertIn("Некорректный variant", errors)
