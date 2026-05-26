"""Сопоставление total_ipem с маршрутами РЖД и поля экономики."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional

from core.models import Cargo, Route, RouteSet

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
    cargo_id: int
    cargo_code: int
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


def normalize_name(value: str) -> str:
    return (value or "").strip().casefold()


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
    cargo_id: int,
) -> int:
    return Route.objects.filter(
        route_set=route_set,
        origin_station__esr_code=origin_esr,
        destination_station__esr_code=dest_esr,
        cargo_id=cargo_id,
    ).count()


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
                cargo_id = int((row.get("cargo_id") or "").strip())
                cargo_code = int((row.get("cargo_code") or "").strip())
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
