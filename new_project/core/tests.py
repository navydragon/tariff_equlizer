from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from core.domain.services.app_settings import (
    SHARE_MODE_ALL,
    SHARE_MODE_OWN,
    SHARE_SCENARIOS_CODE,
    AppSettingsService,
)
from core.export.formatting import format_value_for_excel
from core.models import Setting


class ExcelExportFormattingTests(SimpleTestCase):
    def test_decimal_string_uses_comma(self) -> None:
        self.assertEqual(format_value_for_excel("1.234"), "1,234")
        self.assertEqual(format_value_for_excel("10.0"), "10,0")

    def test_integer_unchanged(self) -> None:
        self.assertEqual(format_value_for_excel("100"), "100")
        self.assertEqual(format_value_for_excel(42), 42)

    def test_text_unchanged(self) -> None:
        self.assertEqual(format_value_for_excel("ИТОГО"), "ИТОГО")
        self.assertEqual(format_value_for_excel("Группа груза"), "Группа груза")

    def test_decimal_type_uses_comma(self) -> None:
        self.assertEqual(format_value_for_excel(Decimal("0.100")), "0,100")

    def test_already_comma_unchanged(self) -> None:
        self.assertEqual(format_value_for_excel("1,234"), "1,234")


class AppSettingsServiceTests(TestCase):
    def setUp(self) -> None:
        Setting.objects.filter(code=SHARE_SCENARIOS_CODE).delete()

    def test_default_share_mode_is_all_without_db_row(self) -> None:
        service = AppSettingsService()
        self.assertEqual(service.get_share_scenarios_mode(), SHARE_MODE_ALL)
        self.assertTrue(service.can_read_user_resource(owner_id=1, user_id=2))

    def test_own_mode_denies_foreign_read(self) -> None:
        Setting.objects.create(
            code=SHARE_SCENARIOS_CODE,
            description="",
            value=SHARE_MODE_OWN,
        )
        service = AppSettingsService()
        self.assertEqual(service.get_share_scenarios_mode(), SHARE_MODE_OWN)
        self.assertFalse(service.can_read_user_resource(owner_id=1, user_id=2))
        self.assertTrue(service.can_read_user_resource(owner_id=1, user_id=1))

    def test_unknown_value_treated_as_own(self) -> None:
        Setting.objects.create(
            code=SHARE_SCENARIOS_CODE,
            description="",
            value="invalid",
        )
        self.assertEqual(AppSettingsService().get_share_scenarios_mode(), SHARE_MODE_OWN)

    def test_write_always_requires_same_owner(self) -> None:
        self.assertTrue(
            AppSettingsService.can_write_user_resource(owner_id=1, user_id=1),
        )
        self.assertFalse(
            AppSettingsService.can_write_user_resource(owner_id=1, user_id=2),
        )


class ImportSettingsCommandTests(TestCase):
    def test_import_settings_creates_share_scenarios(self) -> None:
        out = StringIO()
        call_command("import_settings", stdout=out)
        setting = Setting.objects.get(code=SHARE_SCENARIOS_CODE)
        self.assertEqual(setting.value, SHARE_MODE_ALL)
        self.assertTrue(setting.description)
