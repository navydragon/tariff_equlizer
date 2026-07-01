"""Сопоставление total_ipem с маршрутами РЖД и поля экономики."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from core.domain.cargo.formatting import (
    cargo_code_3_from_etsng,
    cargo_code_lookup_keys,
    format_etsng_code,
    parse_etsng_code,
)
from core.models import Cargo, MessageType, Route, RouteSet, ShipmentType, Shipper, Station, WagonKind

try:
    from rapidfuzz import fuzz, process as rf_process
except ImportError:  # pragma: no cover
    fuzz = None
    rf_process = None

IPEM_ECONOMICS_ROUTE_FIELDS: tuple[str, ...] = (
    "operators_cost_per_ton",
    "transshipment_cost_per_ton",
    "excise_or_duty_per_ton",
    "transport_total_cost_per_ton",
    "production_cost_per_ton",
    "total_cost_per_ton",
    "market_price_per_ton",
)

IPEM_RZD_COST_ROUTE_FIELDS: tuple[str, ...] = (
    "rzd_cost_loaded_per_ton",
    "rzd_cost_empty_per_ton",
    "rzd_cost_total_per_ton",
)

# Все поля, которые переносятся из IPEM в маршруты RZD_2026
IPEM_APPLY_ROUTE_FIELDS: tuple[str, ...] = (
    *IPEM_RZD_COST_ROUTE_FIELDS,
    *IPEM_ECONOMICS_ROUTE_FIELDS,
)

IPEM_COLUMN_BY_ROUTE_FIELD: dict[str, str] = {
    "rzd_cost_loaded_per_ton": (
        'Расходы по оплате услуг ОАО "РЖД", руб. за тонну (груженый пробег)'
    ),
    "rzd_cost_empty_per_ton": (
        'Расходы по оплате услуг ОАО "РЖД", руб. за тонну (порожний пробег)'
    ),
    "rzd_cost_total_per_ton": (
        'Расходы по оплате услуг ОАО "РЖД", руб. за тонну (итого)'
    ),
    "operators_cost_per_ton": "Расходы по оплате услуг операторов_2024, руб. за тонну",
    "transshipment_cost_per_ton": "Расходы на перевалку_2024, руб. за тонну",
    "excise_or_duty_per_ton": "Акциз/пошлина",
    "transport_total_cost_per_ton": "Общие транспортные расходы, руб. за тонну ",
    "production_cost_per_ton": "Себестоимость добычи/производства, руб. т.",
    "total_cost_per_ton": "Общие расходы, руб. за тонну",
    "market_price_per_ton": "Стоимость 1 тонны на рынке, руб./т.",
}

EXPORT_CSV_COLUMNS: tuple[str, ...] = (
    "ipem_index",
    "ipem_key",
    "origin_esr",
    "dest_esr",
    "cargo_name",
    "cargo_id",
    "cargo_code",
    *IPEM_APPLY_ROUTE_FIELDS,
    "rzd_match_count",
)

IPEM_COAL_2026_SHEET = "Уголь_эластика"
IPEM_COAL_2026_HEADER_ROW = 2
IPEM_COAL_CARGO_GROUP_CODE = 1

IPEM_COAL_2026_OVERLAP_COLUMNS: tuple[str, ...] = (
    "ipem_row",
    "сцеп_цены",
    "код_груза",
    "наим_груза",
    "станц_отпр",
    "станц_назн",
    "дор_отпр",
    "дор_наз",
    "род_вагона",
    "вид_перевозки",
    "origin_esr",
    "dest_esr",
    "cargo_code",
    "wagon_kind_name",
    "message_type_name",
    "resolve_status",
    "rzd_match_count",
    "rzd_match_count_broad",
)

IPEM_COAL_2026_COLUMN_BY_ROUTE_FIELD: dict[str, str] = {
    "rzd_cost_loaded_per_ton": (
        "Расходы по оплате услуг ОАО 'РЖД', руб. за тонну гружёный рейс"
    ),
    "rzd_cost_empty_per_ton": (
        "Расходы по оплате услуг ОАО 'РЖД', руб. за тонну порожний рейс"
    ),
    "rzd_cost_total_per_ton": (
        "Расходы по оплате услуг ОАО 'РЖД', руб. за тонну общая стоимость"
    ),
    "operators_cost_per_ton": "Расходы по оплате услуг операторов, руб. за тонну",
    "transshipment_cost_per_ton": "Расходы на перевалку, руб. за тонну",
    "excise_or_duty_per_ton": "Акциз/пошлина",
    "transport_total_cost_per_ton": "Общие транспортные расходы, руб. за тонну ",
    "production_cost_per_ton": "Себестоимость добычи/производства, руб. т.",
    "total_cost_per_ton": "Общие расходы, руб. за тонну",
    "market_price_per_ton": "Стоимость 1 тонны на рынке, руб./т.",
}

MODEL_ROUTE_LINK_KEY_FIELDS: tuple[str, ...] = (
    "origin_station_id",
    "destination_station_id",
    "cargo_id",
    "wagon_kind_id",
    "shipment_type_id",
)


@dataclass
class CargoIndexItem:
    name: str
    cargo: Cargo


@dataclass
class IpemMatchRecord:
    ipem_index: str
    ipem_key: str
    origin_esr: int
    dest_esr: int
    cargo_name: str
    cargo_id: str
    cargo_code: str
    economics: dict[str, Optional[Decimal]]
    rzd_match_count: int = 0


@dataclass
class IpemMatchBuildResult:
    matched: list[IpemMatchRecord] = field(default_factory=list)
    skipped_no_cargo: int = 0
    skipped_no_esr: int = 0
    skipped_no_rzd: int = 0
    total_ipem_rows: int = 0
    duplicate_triple_warnings: list[str] = field(default_factory=list)


@dataclass
class IpemRzdOverlapRow:
    ipem_row: int
    price_chain: str
    cargo_code_raw: str
    cargo_name: str
    origin_station_name: str
    dest_station_name: str
    origin_railroad: str
    dest_railroad: str
    wagon_kind_raw: str
    message_type_raw: str
    origin_esr: Optional[int]
    dest_esr: Optional[int]
    cargo_code: str
    wagon_kind_name: str
    message_type_name: str
    resolve_status: str
    rzd_match_count: int
    rzd_match_count_broad: int


@dataclass
class IpemCoal2026ResolvedRow:
    ipem_row: int
    route_code: str
    origin: Station
    destination: Station
    cargo: Cargo
    wagon_kind: WagonKind
    shipment_type: ShipmentType
    message_type: Optional[MessageType]
    shipper: Optional[Shipper]
    economics: dict[str, Optional[Decimal]]
    transport_volume_tons: Optional[Decimal]
    freight_turnover_tkm: Optional[Decimal]
    freight_charge_rub: Optional[Decimal]
    distance_belt_midpoint_km: Optional[int]
    load_tons_per_wagon: Optional[Decimal]
    delivery_time_loaded_days: Optional[int]
    delivery_time_empty_days: Optional[int]
    delivery_time_ops_days: Optional[int]
    rate_per_wagon_per_day: Optional[Decimal]
    enterprise_load_coefficient: Optional[Decimal] = None
    cargo_code_izpod: str = ""
    cargo_group_izpod: str = ""
    cargo_code_3: str = ""
    cargo_code_izpod_3: str = ""


@dataclass
class IpemCoal2026ImportResult:
    total_rows: int = 0
    created_model_routes: int = 0
    linked_operational_routes: int = 0
    elasticity_direct_model: int = 0
    elasticity_holding_aggregate: int = 0
    elasticity_cargo_group_aggregate: int = 0
    elasticity_skipped: int = 0
    skipped_rows: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    duplicate_link_key_warnings: list[str] = field(default_factory=list)


def normalize_name(value: str) -> str:
    return (value or "").strip().casefold()


def parse_cargo_izpod_fields_from_ipem_row(
    row: dict[str, str],
    cargo: Cargo,
) -> dict[str, str]:
    cargo_code_raw = (row.get("Код груза") or cargo.code or "").strip()
    cargo_group = (row.get("Группа груза") or "").strip()
    if not cargo_group and cargo.cargo_group_id:
        cargo_group = cargo.cargo_group.name
    return {
        "cargo_code_izpod": "",
        "cargo_group_izpod": cargo_group,
        "cargo_code_3": cargo_code_3_from_etsng(cargo_code_raw),
        "cargo_code_izpod_3": "",
    }


CARGO_IZPOD_ROUTE_FIELDS: tuple[str, ...] = (
    "cargo_code_izpod",
    "cargo_group_izpod",
    "cargo_code_3",
    "cargo_code_izpod_3",
)

IPEM_COAL_ECONOMICS_DEFAULT_ZERO_FIELDS: tuple[str, ...] = (
    "transshipment_cost_per_ton",
    "excise_or_duty_per_ton",
)


def require_rapidfuzz() -> None:
    if rf_process is None or fuzz is None:
        raise RuntimeError(
            "Библиотека rapidfuzz не установлена. Добавьте rapidfuzz в зависимости проекта."
        )


def build_cargo_index() -> list[CargoIndexItem]:
    return [
        CargoIndexItem(name=normalize_name(cargo.name), cargo=cargo)
        for cargo in Cargo.objects.all()
    ]


def match_cargo_fuzzy(
    raw_name: str,
    cargo_index: list[CargoIndexItem],
    similarity_threshold: int,
) -> Optional[Cargo]:
    require_rapidfuzz()
    name_norm = normalize_name(raw_name)
    if not name_norm:
        return None

    choices = [item.name for item in cargo_index]
    best = rf_process.extractOne(
        name_norm,
        choices,
        scorer=fuzz.WRatio,
        score_cutoff=similarity_threshold,
    )
    if not best:
        return None

    _, _, idx = best
    if idx is None:
        return None
    return cargo_index[idx].cargo


def parse_decimal_cell(raw: str) -> Optional[Decimal]:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return Decimal(value.replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def parse_enterprise_load_coefficient(row: dict[str, str]) -> Optional[Decimal]:
    raw = (
        row.get("Коэффициент загрузки предприятия")
        or row.get("Unnamed: 45")
        or ""
    )
    return parse_decimal_cell(raw)


def parse_ipem_economics_row(row: dict[str, str]) -> dict[str, Optional[Decimal]]:
    economics: dict[str, Optional[Decimal]] = {}
    for route_field, ipem_column in IPEM_COLUMN_BY_ROUTE_FIELD.items():
        raw = row.get(ipem_column)
        if raw is None:
            raw = row.get(ipem_column.strip())
        if raw is None and route_field == "transport_total_cost_per_ton":
            raw = row.get("Общие транспортные расходы, руб. за тонну")
        economics[route_field] = parse_decimal_cell(raw or "")
    return economics


def parse_esr_from_row(row: dict[str, str]) -> tuple[Optional[int], Optional[int]]:
    origin_raw = (row.get("Код ЕСР станции отправления") or "").replace(" ", "")
    dest_raw = (row.get("Код ЕСР станции назначения") or "").replace(" ", "")
    try:
        origin = int(origin_raw) if origin_raw else None
    except ValueError:
        origin = None
    try:
        dest = int(dest_raw) if dest_raw else None
    except ValueError:
        dest = None
    return origin, dest


def count_rzd_routes(
    route_set: RouteSet,
    *,
    origin_esr: int,
    dest_esr: int,
    cargo_id: str | int,
    wagon_kind_id: Optional[int] = None,
    message_type_id: Optional[int] = None,
) -> int:
    qs = Route.objects.operational().filter(
        route_set=route_set,
        origin_station__esr_code=origin_esr,
        destination_station__esr_code=dest_esr,
        cargo_id=format_etsng_code(cargo_id),
    )
    if wagon_kind_id is not None:
        qs = qs.filter(wagon_kind_id=wagon_kind_id)
    if message_type_id is not None:
        qs = qs.filter(message_type_id=message_type_id)
    return qs.count()


def _ipem_cell_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd

        if pd.isna(value):
            return ""
    except ImportError:
        pass
    if isinstance(value, float) and value != value:
        return ""
    return str(value).strip()


def resolve_station_by_ipem_name(
    station_name: str,
    railroad_code: str = "",
) -> tuple[Optional[Station], Optional[str]]:
    name = (station_name or "").strip()
    if not name:
        return None, "no_station"

    railroad_code = (railroad_code or "").strip()
    qs = Station.objects.filter(short_name__iexact=name)
    if railroad_code:
        qs_rr = qs.filter(railroad__code=railroad_code)
        rr_count = qs_rr.count()
        if rr_count == 1:
            return qs_rr.first(), None
        if rr_count > 1:
            return None, "ambiguous_station"

    count = qs.count()
    if count == 1:
        return qs.first(), None
    if count == 0:
        return None, "no_station"
    return None, "ambiguous_station"


def resolve_cargo_by_etsng(raw_code: Any) -> Optional[Cargo]:
    code = format_etsng_code(raw_code)
    if not code:
        return None
    for candidate in cargo_code_lookup_keys(raw_code):
        cargo = Cargo.objects.filter(code=candidate).first()
        if cargo is not None and format_etsng_code(cargo.code) == code:
            return cargo
    return None


def resolve_wagon_kind(
    raw_name: str,
    wagons: Optional[list[WagonKind]] = None,
) -> tuple[Optional[WagonKind], Optional[str]]:
    name_norm = normalize_name(raw_name)
    if not name_norm:
        return None, "no_wagon"

    if wagons is None:
        wagons = list(WagonKind.objects.all())

    exact_matches = [w for w in wagons if normalize_name(w.name) == name_norm]
    if len(exact_matches) == 1:
        return exact_matches[0], None
    if len(exact_matches) > 1:
        return None, "ambiguous_wagon"

    prefix_matches = [
        w
        for w in wagons
        if normalize_name(w.name).startswith(name_norm)
        or name_norm.startswith(normalize_name(w.name).rstrip("ы"))
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0], None
    if len(prefix_matches) > 1:
        return None, "ambiguous_wagon"
    return None, "no_wagon"


def resolve_message_type(
    raw_name: str,
    message_by_name: Optional[dict[str, MessageType]] = None,
) -> tuple[Optional[MessageType], Optional[str]]:
    name_norm = normalize_name(raw_name)
    if not name_norm:
        return None, "no_message"

    if message_by_name is None:
        message_by_name = {
            normalize_name(m.name): m for m in MessageType.objects.all()
        }

    message = message_by_name.get(name_norm)
    if message is None:
        return None, "no_message"
    return message, None


def load_ipem_coal_2026_xlsx(path: Path) -> list[dict[str, str]]:
    import pandas as pd

    df = pd.read_excel(
        path,
        sheet_name=IPEM_COAL_2026_SHEET,
        header=IPEM_COAL_2026_HEADER_ROW,
    )
    rows: list[dict[str, str]] = []
    for _, series in df.iterrows():
        row = {str(col): _ipem_cell_str(series[col]) for col in df.columns}
        if not any(row.values()):
            continue
        rows.append(row)
    return rows


def build_ipem_coal_2026_overlap(
    xlsx_path: Path,
    route_set: RouteSet,
) -> list[IpemRzdOverlapRow]:
    ipem_rows = load_ipem_coal_2026_xlsx(xlsx_path)
    wagons = list(WagonKind.objects.all())
    message_by_name = {
        normalize_name(m.name): m for m in MessageType.objects.all()
    }

    overlap_rows: list[IpemRzdOverlapRow] = []
    for ipem_row_idx, row in enumerate(ipem_rows, start=1):
        origin_station_name = row.get("Станц отпр РФ", "")
        dest_station_name = row.get("Станц назн РФ", "")
        origin_railroad = row.get("Дор отпр", "")
        dest_railroad = row.get("Дор наз", "")

        issues: list[str] = []
        origin, origin_issue = resolve_station_by_ipem_name(
            origin_station_name, origin_railroad
        )
        if origin_issue:
            issues.append("no_origin" if origin_issue == "no_station" else "ambiguous_origin")

        dest, dest_issue = resolve_station_by_ipem_name(
            dest_station_name, dest_railroad
        )
        if dest_issue:
            issues.append("no_dest" if dest_issue == "no_station" else "ambiguous_dest")

        cargo = resolve_cargo_by_etsng(row.get("Код груза"))
        if cargo is None:
            issues.append("no_cargo")

        wagon, wagon_issue = resolve_wagon_kind(row.get("Род вагона", ""), wagons)
        if wagon_issue:
            issues.append(wagon_issue)

        message, message_issue = resolve_message_type(
            row.get("Вид перевозки", ""), message_by_name
        )
        if message_issue:
            issues.append(message_issue)

        resolve_status = "ok" if not issues else ";".join(issues)

        rzd_match_count_broad = 0
        rzd_match_count = 0
        if origin is not None and dest is not None and cargo is not None:
            rzd_match_count_broad = count_rzd_routes(
                route_set,
                origin_esr=origin.esr_code,
                dest_esr=dest.esr_code,
                cargo_id=cargo.pk,
            )
            if wagon is not None and message is not None:
                rzd_match_count = count_rzd_routes(
                    route_set,
                    origin_esr=origin.esr_code,
                    dest_esr=dest.esr_code,
                    cargo_id=cargo.pk,
                    wagon_kind_id=wagon.pk,
                    message_type_id=message.pk,
                )

        overlap_rows.append(
            IpemRzdOverlapRow(
                ipem_row=ipem_row_idx,
                price_chain=row.get("сцеп цены", ""),
                cargo_code_raw=row.get("Код груза", ""),
                cargo_name=row.get("Наим груза", ""),
                origin_station_name=origin_station_name,
                dest_station_name=dest_station_name,
                origin_railroad=origin_railroad,
                dest_railroad=dest_railroad,
                wagon_kind_raw=row.get("Род вагона", ""),
                message_type_raw=row.get("Вид перевозки", ""),
                origin_esr=origin.esr_code if origin else None,
                dest_esr=dest.esr_code if dest else None,
                cargo_code=format_etsng_code(cargo.code) if cargo else "",
                wagon_kind_name=wagon.name if wagon else "",
                message_type_name=message.name if message else "",
                resolve_status=resolve_status,
                rzd_match_count=rzd_match_count,
                rzd_match_count_broad=rzd_match_count_broad,
            )
        )

    return overlap_rows


def overlap_row_to_csv_dict(row: IpemRzdOverlapRow) -> dict[str, str]:
    return {
        "ipem_row": str(row.ipem_row),
        "сцеп_цены": row.price_chain,
        "код_груза": row.cargo_code_raw,
        "наим_груза": row.cargo_name,
        "станц_отпр": row.origin_station_name,
        "станц_назн": row.dest_station_name,
        "дор_отпр": row.origin_railroad,
        "дор_наз": row.dest_railroad,
        "род_вагона": row.wagon_kind_raw,
        "вид_перевозки": row.message_type_raw,
        "origin_esr": "" if row.origin_esr is None else str(row.origin_esr),
        "dest_esr": "" if row.dest_esr is None else str(row.dest_esr),
        "cargo_code": row.cargo_code,
        "wagon_kind_name": row.wagon_kind_name,
        "message_type_name": row.message_type_name,
        "resolve_status": row.resolve_status,
        "rzd_match_count": str(row.rzd_match_count),
        "rzd_match_count_broad": str(row.rzd_match_count_broad),
    }


def write_overlap_csv(path: Path, rows: Iterable[IpemRzdOverlapRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=IPEM_COAL_2026_OVERLAP_COLUMNS,
            delimiter=";",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(overlap_row_to_csv_dict(row))


def parse_int_cell(raw: str) -> Optional[int]:
    value = (raw or "").strip().replace(" ", "")
    if not value:
        return None
    try:
        return int(float(value.replace(",", ".")))
    except ValueError:
        return None


def parse_ipem_coal_2026_economics_row(row: dict[str, str]) -> dict[str, Optional[Decimal]]:
    economics: dict[str, Optional[Decimal]] = {}
    for route_field, ipem_column in IPEM_COAL_2026_COLUMN_BY_ROUTE_FIELD.items():
        raw = row.get(ipem_column)
        if raw is None:
            raw = row.get(ipem_column.strip())
        if raw is None and route_field == "transport_total_cost_per_ton":
            raw = row.get("Общие транспортные расходы, руб. за тонну")
        economics[route_field] = parse_decimal_cell(raw or "")
    for route_field in IPEM_COAL_ECONOMICS_DEFAULT_ZERO_FIELDS:
        if economics[route_field] is None:
            economics[route_field] = Decimal("0")
    return economics


def resolve_shipment_type(
    raw_name: str,
    shipment_by_name: Optional[dict[str, ShipmentType]] = None,
) -> tuple[Optional[ShipmentType], Optional[str]]:
    name_norm = normalize_name(raw_name)
    if not name_norm:
        return None, "no_shipment_type"

    if shipment_by_name is None:
        shipment_by_name = {
            normalize_name(s.name): s for s in ShipmentType.objects.all()
        }

    shipment = shipment_by_name.get(name_norm)
    if shipment is None:
        return None, "no_shipment_type"
    return shipment, None


def resolve_shipper_from_ipem_row(row: dict[str, str]) -> Optional[Shipper]:
    shipper_name = (row.get("Компания отправителя") or "").strip()
    if not shipper_name:
        return None

    holding = (row.get("Холдинг отправителя") or "").strip()
    okpo_raw = (row.get("ОКПО компании") or "").replace(" ", "")
    okpo = int(okpo_raw) if okpo_raw.isdigit() else 0

    shipper, created = Shipper.objects.get_or_create(
        okpo=okpo,
        inn="",
        name=shipper_name,
        defaults={"holding": holding},
    )
    if not created and holding and not shipper.holding:
        shipper.holding = holding
        shipper.save(update_fields=["holding"])
    return shipper


def model_route_link_key(route: Route) -> tuple[Any, ...]:
    return (
        route.origin_station_id,
        route.destination_station_id,
        route.cargo_id,
        route.wagon_kind_id,
        route.shipment_type_id,
    )


def resolve_ipem_coal_2026_row(
    row: dict[str, str],
    *,
    ipem_row: int,
    wagons: list[WagonKind],
    shipment_by_name: dict[str, ShipmentType],
    message_by_name: dict[str, MessageType],
) -> tuple[Optional[IpemCoal2026ResolvedRow], list[str]]:
    reasons: list[str] = []
    origin, origin_issue = resolve_station_by_ipem_name(
        row.get("Станц отпр РФ", ""),
        row.get("Дор отпр", ""),
    )
    if origin_issue:
        reasons.append(origin_issue)

    destination, dest_issue = resolve_station_by_ipem_name(
        row.get("Станц назн РФ", ""),
        row.get("Дор наз", ""),
    )
    if dest_issue:
        reasons.append(dest_issue)

    cargo = resolve_cargo_by_etsng(row.get("Код груза"))
    if cargo is None:
        reasons.append("no_cargo")

    wagon, wagon_issue = resolve_wagon_kind(row.get("Род вагона", ""), wagons)
    if wagon_issue:
        reasons.append(wagon_issue)

    shipment_type, shipment_issue = resolve_shipment_type(
        row.get("Категория отправки", ""),
        shipment_by_name,
    )
    if shipment_issue:
        reasons.append(shipment_issue)

    message_type, message_issue = resolve_message_type(
        row.get("Вид перевозки", ""),
        message_by_name,
    )
    if message_issue:
        reasons.append(message_issue)

    if reasons or not all([origin, destination, cargo, wagon, shipment_type]):
        return None, reasons

    economics = parse_ipem_coal_2026_economics_row(row)
    shipper = resolve_shipper_from_ipem_row(row)
    cargo_izpod = parse_cargo_izpod_fields_from_ipem_row(row, cargo)

    return (
        IpemCoal2026ResolvedRow(
            ipem_row=ipem_row,
            route_code=f"IPEM2026-{ipem_row:03d}",
            origin=origin,
            destination=destination,
            cargo=cargo,
            wagon_kind=wagon,
            shipment_type=shipment_type,
            message_type=message_type,
            shipper=shipper,
            economics=economics,
            transport_volume_tons=parse_decimal_cell(
                row.get("Объем перевозок (тн)", "")
            ),
            freight_turnover_tkm=parse_decimal_cell(row.get("Грузооборот, ткм", "")),
            freight_charge_rub=parse_decimal_cell(row.get("Провозная плата, руб", "")),
            distance_belt_midpoint_km=parse_int_cell(
                row.get("Средняя дальность(км)", "")
            ),
            load_tons_per_wagon=parse_decimal_cell(row.get("Загрузка вагона", "")),
            delivery_time_loaded_days=parse_int_cell(row.get("Груженый рейс, дней", "")),
            delivery_time_empty_days=parse_int_cell(row.get("Порожний рейс, дней", "")),
            delivery_time_ops_days=parse_int_cell(
                row.get("Погрузка-разгрузка, дней", "")
            ),
            rate_per_wagon_per_day=parse_decimal_cell(
                row.get("Ставка на вагон, руб. за вагон в сутки", "")
            ),
            enterprise_load_coefficient=parse_enterprise_load_coefficient(row),
            **cargo_izpod,
        ),
        [],
    )


def build_model_route_from_resolved_row(
    route_set: RouteSet,
    resolved: IpemCoal2026ResolvedRow,
) -> Route:
    route = Route(
        route_set=route_set,
        is_model=True,
        model_route=None,
        route_code=resolved.route_code,
        cargo=resolved.cargo,
        origin_station=resolved.origin,
        destination_station=resolved.destination,
        wagon_kind=resolved.wagon_kind,
        shipment_type=resolved.shipment_type,
        message_type=resolved.message_type,
        shipper=resolved.shipper,
        transport_volume_tons=resolved.transport_volume_tons,
        freight_turnover_tkm=resolved.freight_turnover_tkm,
        freight_charge_rub=resolved.freight_charge_rub,
        distance_belt_midpoint_km=resolved.distance_belt_midpoint_km,
        load_tons_per_wagon=resolved.load_tons_per_wagon,
        delivery_time_loaded_days=resolved.delivery_time_loaded_days,
        delivery_time_empty_days=resolved.delivery_time_empty_days,
        delivery_time_ops_days=resolved.delivery_time_ops_days,
        rate_per_wagon_per_day=resolved.rate_per_wagon_per_day,
        enterprise_load_coefficient=resolved.enterprise_load_coefficient,
        cargo_code_izpod=resolved.cargo_code_izpod,
        cargo_group_izpod=resolved.cargo_group_izpod,
        cargo_code_3=resolved.cargo_code_3,
        cargo_code_izpod_3=resolved.cargo_code_izpod_3,
    )
    for field_name, value in resolved.economics.items():
        setattr(route, field_name, value)
    return route


def _coal_model_routes_qs(route_set: RouteSet):
    return Route.objects.filter(
        route_set=route_set,
        is_model=True,
        cargo__cargo_group__code=IPEM_COAL_CARGO_GROUP_CODE,
    )


def clear_ipem_model_routes(route_set: RouteSet) -> None:
    coal_model_ids = list(_coal_model_routes_qs(route_set).values_list("pk", flat=True))
    if not coal_model_ids:
        return
    Route.objects.filter(
        route_set=route_set,
        is_model=False,
        model_route_id__in=coal_model_ids,
    ).update(model_route=None)
    Route.objects.filter(pk__in=coal_model_ids).delete()


def link_operational_routes_to_models(
    route_set: RouteSet,
    model_routes: Iterable[Route],
) -> int:
    linked_total = 0
    for model_route in model_routes:
        linked_total += Route.objects.operational().filter(
            route_set=route_set,
            origin_station_id=model_route.origin_station_id,
            destination_station_id=model_route.destination_station_id,
            cargo_id=model_route.cargo_id,
            wagon_kind_id=model_route.wagon_kind_id,
            shipment_type_id=model_route.shipment_type_id,
        ).update(model_route_id=model_route.pk)
    return linked_total


def sync_model_routes_cargo_izpod_from_operational(
    route_set: RouteSet,
    model_routes: Iterable[Route],
) -> int:
    updated_total = 0
    for model_route in model_routes:
        operational = (
            Route.objects.operational()
            .filter(route_set=route_set, model_route_id=model_route.pk)
            .first()
        )
        if operational is None:
            continue
        updates = {
            field: getattr(operational, field) or ""
            for field in CARGO_IZPOD_ROUTE_FIELDS
            if getattr(operational, field)
        }
        if not updates:
            continue
        Route.objects.filter(pk=model_route.pk).update(**updates)
        updated_total += 1
    return updated_total


def import_ipem_coal_2026_model_routes(
    xlsx_path: Path,
    route_set: RouteSet,
    *,
    dry_run: bool = False,
    progress: Callable[[str], None] | None = None,
) -> IpemCoal2026ImportResult:
    result = IpemCoal2026ImportResult()
    ipem_rows = load_ipem_coal_2026_xlsx(xlsx_path)
    result.total_rows = len(ipem_rows)

    wagons = list(WagonKind.objects.all())
    shipment_by_name = {
        normalize_name(s.name): s for s in ShipmentType.objects.all()
    }
    message_by_name = {
        normalize_name(m.name): m for m in MessageType.objects.all()
    }

    resolved_rows: list[IpemCoal2026ResolvedRow] = []
    seen_link_keys: dict[tuple[Any, ...], str] = {}

    for ipem_row_idx, row in enumerate(ipem_rows, start=1):
        resolved, reasons = resolve_ipem_coal_2026_row(
            row,
            ipem_row=ipem_row_idx,
            wagons=wagons,
            shipment_by_name=shipment_by_name,
            message_by_name=message_by_name,
        )
        if resolved is None:
            result.skipped_rows += 1
            result.skip_reasons.append(
                f"Строка {ipem_row_idx}: {'; '.join(reasons)}"
            )
            continue

        link_key = (
            resolved.origin.pk,
            resolved.destination.pk,
            resolved.cargo.pk,
            resolved.wagon_kind.pk,
            resolved.shipment_type.pk,
        )
        if link_key in seen_link_keys:
            result.duplicate_link_key_warnings.append(
                f"Ключ связи {link_key}: повтор в IPEM (строка {ipem_row_idx}, "
                f"ранее строка {seen_link_keys[link_key]}); при линковке победит последняя"
            )
        seen_link_keys[link_key] = str(ipem_row_idx)
        resolved_rows.append(resolved)

    if dry_run:
        result.created_model_routes = len(resolved_rows)
        return result

    clear_ipem_model_routes(route_set)

    model_routes: list[Route] = []
    for resolved in resolved_rows:
        model_routes.append(
            build_model_route_from_resolved_row(route_set, resolved)
        )

    created = Route.objects.bulk_create(model_routes, batch_size=500)
    result.created_model_routes = len(created)
    result.linked_operational_routes = link_operational_routes_to_models(
        route_set,
        created,
    )
    sync_model_routes_cargo_izpod_from_operational(route_set, created)
    from scenarios.domain.services.operational_elasticity import (
        assign_operational_elasticity_sources,
    )

    elasticity_stats = assign_operational_elasticity_sources(
        route_set,
        progress=progress,
    )
    result.elasticity_direct_model = elasticity_stats.direct_model
    result.elasticity_holding_aggregate = elasticity_stats.holding_aggregate
    result.elasticity_cargo_group_aggregate = elasticity_stats.cargo_group_aggregate
    result.elasticity_skipped = elasticity_stats.skipped
    return result


def build_ipem_match_records(
    csv_path: Path,
    route_set: RouteSet,
    *,
    similarity_threshold: int,
    cargo_index: Optional[list[CargoIndexItem]] = None,
) -> IpemMatchBuildResult:
    require_rapidfuzz()
    if cargo_index is None:
        cargo_index = build_cargo_index()

    result = IpemMatchBuildResult()
    seen_triples: dict[tuple[int, int, int], str] = {}

    with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        if not reader.fieldnames:
            raise ValueError("CSV не содержит заголовка")

        for row in reader:
            result.total_ipem_rows += 1
            ipem_index = (row.get("index") or "").strip()
            ipem_key = (row.get("КЛЮЧ_КОД_МАРШРУТА") or "").strip()
            cargo_name = (row.get("Груз") or "").strip()

            origin_esr, dest_esr = parse_esr_from_row(row)
            if origin_esr is None or dest_esr is None:
                result.skipped_no_esr += 1
                continue

            cargo = match_cargo_fuzzy(cargo_name, cargo_index, similarity_threshold)
            if cargo is None:
                result.skipped_no_cargo += 1
                continue

            rzd_count = count_rzd_routes(
                route_set,
                origin_esr=origin_esr,
                dest_esr=dest_esr,
                cargo_id=cargo.pk,
            )
            if rzd_count == 0:
                result.skipped_no_rzd += 1
                continue

            economics = parse_ipem_economics_row(row)
            triple = (origin_esr, dest_esr, cargo.pk)
            triple_label = f"{origin_esr}/{dest_esr}/cargo={cargo.code}"
            if triple in seen_triples and seen_triples[triple] != ipem_index:
                result.duplicate_triple_warnings.append(
                    f"Тройка {triple_label}: повтор в IPEM (index {ipem_index}, "
                    f"ранее index {seen_triples[triple]}); при apply победит последняя строка"
                )
            seen_triples[triple] = ipem_index

            result.matched.append(
                IpemMatchRecord(
                    ipem_index=ipem_index,
                    ipem_key=ipem_key,
                    origin_esr=origin_esr,
                    dest_esr=dest_esr,
                    cargo_name=cargo_name,
                    cargo_id=cargo.pk,
                    cargo_code=cargo.code,
                    economics=economics,
                    rzd_match_count=rzd_count,
                )
            )

    return result


def load_records_from_export_csv(csv_path: Path) -> list[IpemMatchRecord]:
    records: list[IpemMatchRecord] = []
    with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        if not reader.fieldnames:
            raise ValueError("CSV не содержит заголовка")

        for row in reader:
            try:
                origin_esr = int((row.get("origin_esr") or "").strip())
                dest_esr = int((row.get("dest_esr") or "").strip())
                cargo_id = (row.get("cargo_id") or "").strip()
                cargo_code = parse_etsng_code(row.get("cargo_code"))
                if not cargo_id or cargo_code is None:
                    raise ValueError(f"Некорректная строка export CSV: {row}")
            except ValueError as exc:
                raise ValueError(f"Некорректная строка export CSV: {row}") from exc

            economics = {
                field_name: parse_decimal_cell(row.get(field_name) or "")
                for field_name in IPEM_APPLY_ROUTE_FIELDS
            }
            records.append(
                IpemMatchRecord(
                    ipem_index=(row.get("ipem_index") or "").strip(),
                    ipem_key=(row.get("ipem_key") or "").strip(),
                    origin_esr=origin_esr,
                    dest_esr=dest_esr,
                    cargo_name=(row.get("cargo_name") or "").strip(),
                    cargo_id=cargo_id,
                    cargo_code=cargo_code,
                    economics=economics,
                    rzd_match_count=int((row.get("rzd_match_count") or "0").strip() or 0),
                )
            )
    return records


def record_to_export_row(record: IpemMatchRecord) -> dict[str, str]:
    row: dict[str, str] = {
        "ipem_index": record.ipem_index,
        "ipem_key": record.ipem_key,
        "origin_esr": str(record.origin_esr),
        "dest_esr": str(record.dest_esr),
        "cargo_name": record.cargo_name,
        "cargo_id": str(record.cargo_id),
        "cargo_code": str(record.cargo_code),
        "rzd_match_count": str(record.rzd_match_count),
    }
    for field_name in IPEM_APPLY_ROUTE_FIELDS:
        value = record.economics.get(field_name)
        row[field_name] = "" if value is None else format(value, "f")
    return row


def write_export_csv(path: Path, records: Iterable[IpemMatchRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        for record in records:
            writer.writerow(record_to_export_row(record))


def apply_economics_to_rzd_routes(
    route_set: RouteSet,
    records: list[IpemMatchRecord],
    *,
    dry_run: bool = False,
    batch_size: int = 1000,
) -> dict[str, int]:
    stats = {
        "ipem_rows_applied": 0,
        "rzd_routes_updated": 0,
    }
    update_fields = list(IPEM_APPLY_ROUTE_FIELDS)

    for record in records:
        routes = list(
            Route.objects.filter(
                route_set=route_set,
                origin_station__esr_code=record.origin_esr,
                destination_station__esr_code=record.dest_esr,
                cargo_id=record.cargo_id,
            )
        )
        if not routes:
            continue

        stats["ipem_rows_applied"] += 1
        for route in routes:
            for field_name, value in record.economics.items():
                setattr(route, field_name, value)

        if not dry_run:
            Route.objects.bulk_update(routes, update_fields, batch_size=batch_size)
        stats["rzd_routes_updated"] += len(routes)

    return stats
