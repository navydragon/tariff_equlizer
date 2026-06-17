from django.test import TestCase

from core.domain.cargo.ordering import (
    cargo_group_sort_key,
    clear_cargo_group_position_cache,
    normalize_filter_options,
    sort_cargo_group_names,
)
from core.models import CargoGroup


class CargoGroupOrderingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        groups = [
            (1, "Уголь каменный", 1),
            (2, "Кокс каменноугольный", 2),
            (3, "Нефтяные грузы", 3),
            (10, "Остальные грузы", 10),
            (11, "Грузы на своих осях", 11),
        ]
        for code, name, position in groups:
            CargoGroup.objects.update_or_create(
                code=code,
                defaults={"name": name, "position": position},
            )
        clear_cargo_group_position_cache()

    def test_sort_cargo_group_names_by_position(self) -> None:
        names = [
            "Остальные грузы",
            "Уголь каменный",
            "Нефтяные грузы",
            "Кокс каменноугольный",
            "—",
        ]
        self.assertEqual(
            sort_cargo_group_names(names),
            [
                "Уголь каменный",
                "Кокс каменноугольный",
                "Нефтяные грузы",
                "Остальные грузы",
                "—",
            ],
        )

    def test_unknown_name_sorted_before_sentinel(self) -> None:
        names = ["Неизвестная группа", "Уголь каменный", "—"]
        self.assertEqual(
            sort_cargo_group_names(names),
            ["Уголь каменный", "Неизвестная группа", "—"],
        )

    def test_cargo_group_sort_key_uses_position_from_db(self) -> None:
        self.assertLess(
            cargo_group_sort_key("Уголь каменный"),
            cargo_group_sort_key("Кокс каменноугольный"),
        )

    def test_normalize_filter_options_resorts_cached_alphabetical_list(self) -> None:
        cached = {
            "cargo_groups": [
                "—",
                "Остальные грузы",
                "Нефтяные грузы",
                "Уголь каменный",
                "Кокс каменноугольный",
            ],
            "holdings": ["Beta", "Alpha"],
        }
        normalized = normalize_filter_options(cached)
        self.assertEqual(
            normalized["cargo_groups"],
            [
                "Уголь каменный",
                "Кокс каменноугольный",
                "Нефтяные грузы",
                "Остальные грузы",
                "—",
            ],
        )
        self.assertEqual(normalized["holdings"], ["Beta", "Alpha"])
