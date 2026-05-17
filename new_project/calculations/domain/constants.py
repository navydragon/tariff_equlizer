from __future__ import annotations

GROUP_BY_CHOICES = frozenset(
    {
        "cargo_group",
        "cargo_code",
        "direction",
        "wagon_kind",
        "transport_type",
        "shipment_category",
        "park_type",
        "holding",
    },
)
GROUP_BY_INNER_CHOICES = GROUP_BY_CHOICES | frozenset({"none"})

CUBE_GROUP_BY_CHOICES = GROUP_BY_CHOICES | frozenset({"tariff_decision"})
CUBE_GROUP_BY_INNER_CHOICES = GROUP_BY_CHOICES | frozenset({"none"})

# Обратная совместимость для блока эффектов (3 измерения).
EFFECTS_GROUP_BY_CHOICES = frozenset({"cargo_group", "holding", "transport_type"})
EFFECTS_GROUP_BY_INNER_CHOICES = EFFECTS_GROUP_BY_CHOICES | frozenset({"none"})

GROUP_BY_LABELS: dict[str, str] = {
    "cargo_group": "Группа груза",
    "cargo_code": "Код груза",
    "direction": "Направления",
    "wagon_kind": "Род вагона",
    "transport_type": "Вид перевозки",
    "shipment_category": "Категория отпр.",
    "park_type": "Тип парка",
    "holding": "Холдинг",
    "tariff_decision": "Тарифные решения",
}
