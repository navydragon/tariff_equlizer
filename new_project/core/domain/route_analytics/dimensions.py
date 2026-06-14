from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DimensionSpec:
    code: str
    label: str
    orm_field: str
    empty_label: str = "—"
    empty_as_misc: bool = False


DIMENSIONS: dict[str, DimensionSpec] = {
    "cargo_group": DimensionSpec(
        code="cargo_group",
        label="Группа груза",
        orm_field="cargo__cargo_group__name",
    ),
    "cargo_code": DimensionSpec(
        code="cargo_code",
        label="Код груза",
        orm_field="cargo__code",
    ),
    "direction": DimensionSpec(
        code="direction",
        label="Направление",
        orm_field="origin_station__railroad__direction",
    ),
    "origin_railroad": DimensionSpec(
        code="origin_railroad",
        label="Дорога отправления",
        orm_field="origin_station__railroad__name",
    ),
    "destination_railroad": DimensionSpec(
        code="destination_railroad",
        label="Дорога назначения",
        orm_field="destination_station__railroad__name",
    ),
    "wagon_kind": DimensionSpec(
        code="wagon_kind",
        label="Род вагона",
        orm_field="wagon_kind__name",
    ),
    "shipment_type": DimensionSpec(
        code="shipment_type",
        label="Тип отправки",
        orm_field="shipment_type__name",
    ),
    "message_type": DimensionSpec(
        code="message_type",
        label="Вид сообщения",
        orm_field="message_type__name",
    ),
    "shipper_holding": DimensionSpec(
        code="shipper_holding",
        label="Холдинг",
        orm_field="shipper__holding",
        empty_label="Прочие",
        empty_as_misc=True,
    ),
    "shipper": DimensionSpec(
        code="shipper",
        label="Грузоотправитель",
        orm_field="shipper__name",
    ),
    "distance_belt": DimensionSpec(
        code="distance_belt",
        label="Пояс дальности",
        orm_field="distance_belt",
    ),
    "shipment_category": DimensionSpec(
        code="shipment_category",
        label="Категория отпр.",
        orm_field="shipment_category",
    ),
    "park_type": DimensionSpec(
        code="park_type",
        label="Тип парка",
        orm_field="park_type",
    ),
    "special_container_type": DimensionSpec(
        code="special_container_type",
        label="Вид спец. контейнера",
        orm_field="special_container_type",
    ),
}


VALID_METRICS = frozenset({"count", "money", "volume", "turnover"})


def get_dimension(code: str) -> DimensionSpec | None:
    return DIMENSIONS.get(code)
