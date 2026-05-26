from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from core.models import (
    Cargo,
    MessageType,
    Route,
    RouteSet,
    ShipmentType,
    Shipper,
    Station,
    WagonKind,
)


def _decimal_to_api_str(value: Decimal) -> str:
    return format(value.normalize(), "f")


@dataclass
class RouteSetDTO:
    id: int
    name: str
    code: str
    routes_count: int
    created_at: Optional[str]
    updated_at: Optional[str]

    @classmethod
    def from_model(cls, route_set: RouteSet, *, routes_count: int) -> RouteSetDTO:
        return cls(
            id=route_set.id,
            name=route_set.name,
            code=route_set.code,
            routes_count=routes_count,
            created_at=route_set.created_at.isoformat() if route_set.created_at else None,
            updated_at=route_set.updated_at.isoformat() if route_set.updated_at else None,
        )

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "routes_count": self.routes_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class RouteSetListResultDTO:
    items: list[RouteSetDTO]
    total: int
    page: int
    page_size: int
    total_pages: int

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_api_dict() for item in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
        }


@dataclass
class CreateRouteSetDTO:
    name: str
    code: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name or not self.name.strip():
            errors.append("Название набора обязательно")
        if not self.code or not self.code.strip():
            errors.append("Код набора обязателен")
        return errors


@dataclass
class UpdateRouteSetDTO:
    name: Optional[str] = None
    code: Optional[str] = None


@dataclass
class RouteDTO:
    id: int
    route_set_id: int
    route_set_code: str
    route_code: str
    distance_belt: str
    shipment_category: str
    park_type: str
    special_container_type: str
    cargo_group_cmtp: str
    cargo_code_izpod: str
    cargo_code: Optional[int]
    cargo_name: str
    origin_esr_code: Optional[int]
    origin_station_name: str
    destination_esr_code: Optional[int]
    destination_station_name: str
    origin_railroad_code: str
    origin_region_full_name: str
    origin_railroad_name: str
    origin_railroad_direction: str
    destination_railroad_code: str
    destination_region_full_name: str
    destination_railroad_name: str
    destination_railroad_direction: str
    wagon_kind_id: Optional[int]
    wagon_kind_name: str
    shipment_type_id: Optional[int]
    shipment_type_name: str
    message_type_id: Optional[int]
    message_type_name: str
    shipper_id: Optional[int]
    shipper_name: str
    shipper_holding: str
    shipper_okpo: Optional[int]
    shipper_inn: str
    distance_loaded_km: Optional[int]
    distance_empty_km: Optional[int]
    load_tons_per_wagon: Optional[str]
    delivery_time_loaded_days: Optional[int]
    delivery_time_empty_days: Optional[int]
    delivery_time_ops_days: Optional[int]
    rate_per_wagon_per_day: Optional[str]
    rzd_cost_loaded_per_ton: Optional[str]
    rzd_cost_empty_per_ton: Optional[str]
    rzd_cost_total_per_ton: Optional[str]
    operators_cost_per_ton: Optional[str]
    transshipment_cost_per_ton: Optional[str]
    excise_or_duty_per_ton: Optional[str]
    transport_total_cost_per_ton: Optional[str]
    production_cost_per_ton: Optional[str]
    total_cost_per_ton: Optional[str]
    market_price_per_ton: Optional[str]
    transport_volume_tons: Optional[str]
    freight_turnover_tkm: Optional[str]
    freight_charge_rub: Optional[str]

    @classmethod
    def from_model(cls, route: Route) -> RouteDTO:
        return cls(
            id=route.id,
            route_set_id=route.route_set_id,
            route_set_code=route.route_set.code if route.route_set_id else "",
            route_code=route.route_code,
            distance_belt=route.distance_belt,
            shipment_category=route.shipment_category,
            park_type=route.park_type,
            special_container_type=route.special_container_type,
            cargo_group_cmtp=route.cargo_group_cmtp,
            cargo_code_izpod=route.cargo_code_izpod,
            cargo_code=route.cargo.code if route.cargo_id else None,
            cargo_name=route.cargo.name if route.cargo_id else "",
            origin_esr_code=route.origin_station.esr_code
            if route.origin_station_id
            else None,
            origin_station_name=route.origin_station.full_name
            if route.origin_station_id
            else "",
            destination_esr_code=route.destination_station.esr_code
            if route.destination_station_id
            else None,
            destination_station_name=route.destination_station.full_name
            if route.destination_station_id
            else "",
            origin_railroad_code=route.origin_station.railroad.code
            if route.origin_station_id and route.origin_station.railroad_id
            else "",
            origin_region_full_name=route.origin_station.region.full_name
            if route.origin_station_id and route.origin_station.region_id
            else "",
            origin_railroad_name=route.origin_station.railroad.name
            if route.origin_station_id and route.origin_station.railroad_id
            else "",
            origin_railroad_direction=route.origin_station.railroad.direction
            if route.origin_station_id and route.origin_station.railroad_id
            else "",
            destination_railroad_code=route.destination_station.railroad.code
            if route.destination_station_id and route.destination_station.railroad_id
            else "",
            destination_region_full_name=route.destination_station.region.full_name
            if route.destination_station_id and route.destination_station.region_id
            else "",
            destination_railroad_name=route.destination_station.railroad.name
            if route.destination_station_id and route.destination_station.railroad_id
            else "",
            destination_railroad_direction=route.destination_station.railroad.direction
            if route.destination_station_id and route.destination_station.railroad_id
            else "",
            wagon_kind_id=route.wagon_kind_id,
            wagon_kind_name=route.wagon_kind.name if route.wagon_kind_id else "",
            shipment_type_id=route.shipment_type_id,
            shipment_type_name=route.shipment_type.name if route.shipment_type_id else "",
            message_type_id=route.message_type_id,
            message_type_name=route.message_type.name if route.message_type_id else "",
            shipper_id=route.shipper_id,
            shipper_name=route.shipper.name if route.shipper_id else "",
            shipper_holding=route.shipper.holding if route.shipper_id else "",
            shipper_okpo=route.shipper.okpo if route.shipper_id else None,
            shipper_inn=route.shipper.inn if route.shipper_id else "",
            distance_loaded_km=route.distance_loaded_km,
            distance_empty_km=route.distance_empty_km,
            load_tons_per_wagon=_decimal_to_api_str(route.load_tons_per_wagon)
            if route.load_tons_per_wagon is not None
            else None,
            delivery_time_loaded_days=route.delivery_time_loaded_days,
            delivery_time_empty_days=route.delivery_time_empty_days,
            delivery_time_ops_days=route.delivery_time_ops_days,
            rate_per_wagon_per_day=_decimal_to_api_str(route.rate_per_wagon_per_day)
            if route.rate_per_wagon_per_day is not None
            else None,
            rzd_cost_loaded_per_ton=_decimal_to_api_str(route.rzd_cost_loaded_per_ton)
            if route.rzd_cost_loaded_per_ton is not None
            else None,
            rzd_cost_empty_per_ton=_decimal_to_api_str(route.rzd_cost_empty_per_ton)
            if route.rzd_cost_empty_per_ton is not None
            else None,
            rzd_cost_total_per_ton=_decimal_to_api_str(route.rzd_cost_total_per_ton)
            if route.rzd_cost_total_per_ton is not None
            else None,
            operators_cost_per_ton=_decimal_to_api_str(route.operators_cost_per_ton)
            if route.operators_cost_per_ton is not None
            else None,
            transshipment_cost_per_ton=_decimal_to_api_str(route.transshipment_cost_per_ton)
            if route.transshipment_cost_per_ton is not None
            else None,
            excise_or_duty_per_ton=_decimal_to_api_str(route.excise_or_duty_per_ton)
            if route.excise_or_duty_per_ton is not None
            else None,
            transport_total_cost_per_ton=_decimal_to_api_str(route.transport_total_cost_per_ton)
            if route.transport_total_cost_per_ton is not None
            else None,
            production_cost_per_ton=_decimal_to_api_str(route.production_cost_per_ton)
            if route.production_cost_per_ton is not None
            else None,
            total_cost_per_ton=_decimal_to_api_str(route.total_cost_per_ton)
            if route.total_cost_per_ton is not None
            else None,
            market_price_per_ton=_decimal_to_api_str(route.market_price_per_ton)
            if route.market_price_per_ton is not None
            else None,
            transport_volume_tons=_decimal_to_api_str(route.transport_volume_tons)
            if route.transport_volume_tons is not None
            else None,
            freight_turnover_tkm=_decimal_to_api_str(route.freight_turnover_tkm)
            if route.freight_turnover_tkm is not None
            else None,
            freight_charge_rub=_decimal_to_api_str(route.freight_charge_rub)
            if route.freight_charge_rub is not None
            else None,
        )

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "route_set_id": self.route_set_id,
            "route_set_code": self.route_set_code,
            "route_code": self.route_code,
            "distance_belt": self.distance_belt,
            "shipment_category": self.shipment_category,
            "park_type": self.park_type,
            "special_container_type": self.special_container_type,
            "cargo_group_cmtp": self.cargo_group_cmtp,
            "cargo_code_izpod": self.cargo_code_izpod,
            "cargo_code": self.cargo_code,
            "cargo_name": self.cargo_name,
            "origin_esr_code": self.origin_esr_code,
            "origin_station_name": self.origin_station_name,
            "destination_esr_code": self.destination_esr_code,
            "destination_station_name": self.destination_station_name,
            "origin_railroad_code": self.origin_railroad_code,
            "origin_region_full_name": self.origin_region_full_name,
            "origin_railroad_name": self.origin_railroad_name,
            "origin_railroad_direction": self.origin_railroad_direction,
            "destination_railroad_code": self.destination_railroad_code,
            "destination_region_full_name": self.destination_region_full_name,
            "destination_railroad_name": self.destination_railroad_name,
            "destination_railroad_direction": self.destination_railroad_direction,
            "wagon_kind_id": self.wagon_kind_id,
            "wagon_kind_name": self.wagon_kind_name,
            "shipment_type_id": self.shipment_type_id,
            "shipment_type_name": self.shipment_type_name,
            "message_type_id": self.message_type_id,
            "message_type_name": self.message_type_name,
            "shipper_id": self.shipper_id,
            "shipper_name": self.shipper_name,
            "shipper_holding": self.shipper_holding,
            "shipper_okpo": self.shipper_okpo,
            "shipper_inn": self.shipper_inn,
            "distance_loaded_km": self.distance_loaded_km,
            "distance_empty_km": self.distance_empty_km,
            "load_tons_per_wagon": self.load_tons_per_wagon,
            "delivery_time_loaded_days": self.delivery_time_loaded_days,
            "delivery_time_empty_days": self.delivery_time_empty_days,
            "delivery_time_ops_days": self.delivery_time_ops_days,
            "rate_per_wagon_per_day": self.rate_per_wagon_per_day,
            "rzd_cost_loaded_per_ton": self.rzd_cost_loaded_per_ton,
            "rzd_cost_empty_per_ton": self.rzd_cost_empty_per_ton,
            "rzd_cost_total_per_ton": self.rzd_cost_total_per_ton,
            "operators_cost_per_ton": self.operators_cost_per_ton,
            "transshipment_cost_per_ton": self.transshipment_cost_per_ton,
            "excise_or_duty_per_ton": self.excise_or_duty_per_ton,
            "transport_total_cost_per_ton": self.transport_total_cost_per_ton,
            "production_cost_per_ton": self.production_cost_per_ton,
            "total_cost_per_ton": self.total_cost_per_ton,
            "market_price_per_ton": self.market_price_per_ton,
            "transport_volume_tons": self.transport_volume_tons,
            "freight_turnover_tkm": self.freight_turnover_tkm,
            "freight_charge_rub": self.freight_charge_rub,
        }


@dataclass
class RouteListFiltersDTO:
    route_set_id: int
    page: int = 1
    page_size: int = 20
    search: Optional[str] = None
    origin_esr: Optional[str] = None
    destination_esr: Optional[str] = None
    include_total: bool = False
    economics_filled: bool = False


@dataclass
class RouteListResultDTO:
    items: list[RouteDTO]
    page: int
    page_size: int
    total: Optional[int] = None
    total_pages: Optional[int] = None
    has_next: Optional[bool] = None

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "items": [item.to_api_dict() for item in self.items],
            "page": self.page,
            "page_size": self.page_size,
        }
        if self.total is not None:
            payload["total"] = self.total
        if self.total_pages is not None:
            payload["total_pages"] = self.total_pages
        if self.has_next is not None:
            payload["has_next"] = self.has_next
        return payload


@dataclass
class RouteWriteDTO:
    """Поля для создания/обновления Route через ORM."""

    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request_data(cls, data: dict) -> tuple[Optional[RouteWriteDTO], list[str]]:
        errors: list[str] = []
        payload: dict[str, Any] = {}

        route_set_id = data.get("route_set_id")
        if route_set_id in (None, "", "null"):
            errors.append("Набор маршрутов обязателен")
        else:
            try:
                payload["route_set"] = RouteSet.objects.get(pk=int(route_set_id))
            except (ValueError, RouteSet.DoesNotExist):
                errors.append("Указан несуществующий набор маршрутов")

        cargo_code = data.get("cargo_code")
        if cargo_code in (None, "", "null"):
            errors.append("Код груза обязателен")
        else:
            try:
                payload["cargo"] = Cargo.objects.get(code=int(cargo_code))
            except (ValueError, Cargo.DoesNotExist):
                errors.append("Указан несуществующий груз (код ETSNG)")

        origin_esr = data.get("origin_esr_code")
        if origin_esr in (None, "", "null"):
            errors.append("Код ЕСР станции отправления обязателен")
        else:
            try:
                payload["origin_station"] = Station.objects.get(esr_code=int(origin_esr))
            except (ValueError, Station.DoesNotExist):
                errors.append("Указана несуществующая станция отправления")

        destination_esr = data.get("destination_esr_code")
        if destination_esr in (None, "", "null"):
            errors.append("Код ЕСР станции назначения обязателен")
        else:
            try:
                payload["destination_station"] = Station.objects.get(
                    esr_code=int(destination_esr)
                )
            except (ValueError, Station.DoesNotExist):
                errors.append("Указана несуществующая станция назначения")

        wagon_kind_id = data.get("wagon_kind_id")
        if wagon_kind_id in (None, "", "null"):
            errors.append("Род вагона обязателен")
        else:
            try:
                payload["wagon_kind"] = WagonKind.objects.get(pk=int(wagon_kind_id))
            except (ValueError, WagonKind.DoesNotExist):
                errors.append("Указан несуществующий род вагона")

        shipment_type_id = data.get("shipment_type_id")
        if shipment_type_id in (None, "", "null"):
            errors.append("Тип отправки обязателен")
        else:
            try:
                payload["shipment_type"] = ShipmentType.objects.get(
                    pk=int(shipment_type_id)
                )
            except (ValueError, ShipmentType.DoesNotExist):
                errors.append("Указан несуществующий тип отправки")

        message_type_id = data.get("message_type_id")
        if message_type_id not in (None, "", "null"):
            try:
                payload["message_type"] = MessageType.objects.get(pk=int(message_type_id))
            except (ValueError, MessageType.DoesNotExist):
                errors.append("Указан несуществующий вид сообщения")

        shipper_id = data.get("shipper_id")
        if shipper_id in (None, "", "null"):
            payload["shipper"] = None
        else:
            try:
                payload["shipper"] = Shipper.objects.get(pk=int(shipper_id))
            except (ValueError, Shipper.DoesNotExist):
                errors.append("Указан несуществующий грузоотправитель")

        payload["route_code"] = (data.get("route_code") or "").strip()

        for name in (
            "distance_belt",
            "shipment_category",
            "park_type",
            "special_container_type",
            "cargo_group_cmtp",
            "cargo_code_izpod",
        ):
            payload[name] = (data.get(name) or "").strip()

        def parse_int_field(field_name: str) -> int | None:
            raw = data.get(field_name)
            if raw in (None, "", "null"):
                return None
            try:
                return int(str(raw).replace(" ", ""))
            except (TypeError, ValueError):
                errors.append(f'Поле "{field_name}" должно быть целым числом')
                return None

        def parse_decimal_field(field_name: str):
            raw = data.get(field_name)
            if raw in (None, "", "null"):
                return None, None
            try:
                value = Decimal(str(raw).replace(" ", "").replace(",", "."))
                return value, None
            except (InvalidOperation, TypeError, ValueError):
                return None, f'Поле "{field_name}" должно быть числом'

        for name in (
            "distance_loaded_km",
            "distance_empty_km",
            "delivery_time_loaded_days",
            "delivery_time_empty_days",
            "delivery_time_ops_days",
        ):
            value = parse_int_field(name)
            if value is not None:
                payload[name] = value

        for name in (
            "load_tons_per_wagon",
            "rate_per_wagon_per_day",
            "rzd_cost_loaded_per_ton",
            "rzd_cost_empty_per_ton",
            "rzd_cost_total_per_ton",
            "operators_cost_per_ton",
            "transshipment_cost_per_ton",
            "excise_or_duty_per_ton",
            "transport_total_cost_per_ton",
            "production_cost_per_ton",
            "total_cost_per_ton",
            "market_price_per_ton",
        ):
            value, err = parse_decimal_field(name)
            if err:
                errors.append(err)
            if value is not None:
                payload[name] = value

        for name in (
            "transport_volume_tons",
            "freight_turnover_tkm",
            "freight_charge_rub",
        ):
            if name not in data:
                continue
            raw = data.get(name)
            if raw in (None, "", "null"):
                payload[name] = None
                continue
            value, err = parse_decimal_field(name)
            if err:
                errors.append(err)
            elif value is not None:
                payload[name] = value

        if errors:
            return None, errors
        return cls(payload=payload), []
