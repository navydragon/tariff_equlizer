import tempfile
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from calculations.domain.services.route_mart_store import ROUTE_MART_REFS_VERSION_CODE
from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Region,
    Route,
    RouteSet,
    Setting,
    ShipmentType,
    Station,
    WagonKind,
)


class RefreshDeployCachesTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.cache_dirs = {
            "ROUTE_MART_CACHE_DIR": str(base / "route_mart"),
            "SCENARIO_COMPUTE_CACHE_DIR": str(base / "scenario_compute"),
            "ROUTE_MASK_CACHE_DIR": str(base / "route_masks"),
        }
        self.settings_override = override_settings(**self.cache_dirs)
        self.settings_override.enable()

        self.route_set = RouteSet.objects.create(code="CACHE_RS", name="Cache test")
        cargo_group = CargoGroup.objects.create(name="G", code=77, position=1)
        cargo = Cargo.objects.create(code=77001, name="Cargo", cargo_group=cargo_group)
        railroad = RailRoad.objects.create(code="88", name="Road")
        region = Region.objects.create(
            short_name="R",
            full_name="Region",
            type="область",
        )
        origin = Station.objects.create(
            esr_code=333333,
            short_name="A",
            full_name="Station A",
            region=region,
            railroad=railroad,
        )
        destination = Station.objects.create(
            esr_code=444444,
            short_name="B",
            full_name="Station B",
            region=region,
            railroad=railroad,
        )
        wagon_kind = WagonKind.objects.create(code="WK_C", name="Wagon")
        shipment_type = ShipmentType.objects.create(code="ST_C", name="Shipment")
        message_type = MessageType.objects.create(code="MT_C", name="Internal")

        Route.objects.create(
            route_set=self.route_set,
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            route_code="CACHE-001",
            freight_charge_rub="1000.00",
        )

        Setting.objects.update_or_create(
            code=ROUTE_MART_REFS_VERSION_CODE,
            defaults={"description": "Route mart refs version", "value": "42"},
        )
        cache.set(ROUTE_MART_REFS_VERSION_CODE, "stale", timeout=3600)
        cache.set("scenario_effects:1:1:abc", {"payload": True}, timeout=3600)

        stale_file = Path(self.cache_dirs["ROUTE_MART_CACHE_DIR"]) / "stale.parquet"
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text("stale", encoding="utf-8")

        stale_compute = (
            Path(self.cache_dirs["SCENARIO_COMPUTE_CACHE_DIR"]) / "1" / "deadbeef"
        )
        stale_compute.mkdir(parents=True)
        (stale_compute / "baseline_rub.npy").write_bytes(b"stale")

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.temp_dir.cleanup()

    def test_refresh_deploy_caches_clears_and_warms(self) -> None:
        call_command("refresh_deploy_caches", verbosity=0)

        self.assertFalse(
            (Path(self.cache_dirs["ROUTE_MART_CACHE_DIR"]) / "stale.parquet").exists(),
        )
        self.assertFalse(
            (
                Path(self.cache_dirs["SCENARIO_COMPUTE_CACHE_DIR"])
                / "1"
                / "deadbeef"
                / "baseline_rub.npy"
            ).exists(),
        )
        self.assertIsNone(cache.get("scenario_effects:1:1:abc"))

        mart_root = Path(self.cache_dirs["ROUTE_MART_CACHE_DIR"]) / str(self.route_set.id)
        parquet_files = list(mart_root.glob("*.parquet"))
        self.assertEqual(len(parquet_files), 1)
        self.assertGreater(parquet_files[0].stat().st_size, 0)

        self.assertEqual(cache.get(ROUTE_MART_REFS_VERSION_CODE), "42")

    def test_clear_only_skips_warm(self) -> None:
        call_command("refresh_deploy_caches", clear_only=True, verbosity=0)

        mart_root = Path(self.cache_dirs["ROUTE_MART_CACHE_DIR"]) / str(self.route_set.id)
        self.assertFalse(list(mart_root.glob("*.parquet")))

    def test_warm_only_keeps_other_cache_dirs_but_builds_mart(self) -> None:
        call_command("refresh_deploy_caches", warm_only=True, verbosity=0)

        self.assertTrue(
            (
                Path(self.cache_dirs["SCENARIO_COMPUTE_CACHE_DIR"])
                / "1"
                / "deadbeef"
                / "baseline_rub.npy"
            ).exists(),
        )

        mart_root = Path(self.cache_dirs["ROUTE_MART_CACHE_DIR"]) / str(self.route_set.id)
        self.assertEqual(len(list(mart_root.glob("*.parquet"))), 1)
