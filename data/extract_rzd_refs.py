"""Извлечение DISTINCT CSV справочников из базы РЖД (ИХ_ГП)."""

from __future__ import annotations

import csv
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "new_project"))

from core.domain.cargo.formatting import normalize_rzd_cargo_code  # noqa: E402

DB_PATH = REPO_ROOT / "databases" / "02_2026-06-22.db"
DB_PATH_FALLBACK = REPO_ROOT / "databases" / "01_2026-05-19.db"
DB_PATH_LEGACY = Path(__file__).resolve().parent / "01_2026-05-19.db"
OUT_DIR = Path(__file__).parent / "refs-01"
TABLE = "ИХ_ГП"


def _parse_region_type(full_name: str) -> str:
    name = (full_name or "").strip()
    if not name:
        return "Не указан"
    lower = name.casefold()
    if lower.startswith("республика"):
        return "Республика"
    if lower.startswith("город"):
        return "Город"
    if "автономный округ" in lower or "ао " in lower:
        return "Автономный округ"
    if lower.endswith("область"):
        return "Область"
    if lower.endswith("край"):
        return "Край"
    if "федерации" in lower:
        return "Город"
    return "Не указан"


def _region_short_name(full_name: str, region_type: str) -> str:
    name = (full_name or "").strip()
    if not name:
        return "Не указан"
    if region_type == "Республика":
        short = re.sub(r"^республика\s+", "", name, flags=re.IGNORECASE).strip()
        return short or name
    if region_type == "Город":
        short = re.sub(r"^город\s+", "", name, flags=re.IGNORECASE).strip()
        return short.split()[0] if short else name
    if region_type == "Область":
        return re.sub(r"\s+область\s*$", "", name, flags=re.IGNORECASE).strip() or name
    if region_type == "Край":
        return re.sub(r"\s+край\s*$", "", name, flags=re.IGNORECASE).strip() or name
    return name


def _parse_cargo_code(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if not raw.isdigit():
        return None
    return raw


def _resolve_db_path() -> Path:
    for candidate in (DB_PATH, DB_PATH_FALLBACK, DB_PATH_LEGACY):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"База РЖД не найдена: проверены {DB_PATH}, {DB_PATH_FALLBACK}, {DB_PATH_LEGACY}"
    )


def _extract_cargos(cur: sqlite3.Cursor) -> tuple[Path, int, Counter[str]]:
    cur.execute(
        f"""
        SELECT
            "Код груза" AS cargo_code,
            "Наим груза" AS cargo_name,
            "Код группы груза" AS group_code
        FROM [{TABLE}]
        WHERE "Код груза" IS NOT NULL AND TRIM("Код груза") != ''
        """
    )

    cargo_by_code: dict[str, dict[str, str]] = {}
    warning_counts: Counter[str] = Counter()
    skipped_cargos = 0

    for row in cur.fetchall():
        raw_code = _parse_cargo_code(row["cargo_code"])
        if raw_code is None:
            skipped_cargos += 1
            continue

        normalized, warn = normalize_rzd_cargo_code(raw_code)
        if not normalized:
            skipped_cargos += 1
            continue
        if warn:
            warning_counts[warn] += 1

        name = (row["cargo_name"] or "").strip()
        group_code = row["group_code"]
        group_raw = "" if group_code is None else str(group_code).strip()

        existing = cargo_by_code.get(normalized)
        if existing is None or name > existing["name"]:
            cargo_by_code[normalized] = {
                "name": name,
                "group": group_raw,
            }

    cargos_path = OUT_DIR / "cargos.csv"
    with cargos_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Код", "Наименование", "Код группы груза"])
        for code in sorted(cargo_by_code):
            entry = cargo_by_code[code]
            writer.writerow([code, entry["name"], entry["group"]])

    return cargos_path, skipped_cargos, warning_counts


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(_resolve_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # --- Регионы ---
    cur.execute(
        f"""
        SELECT DISTINCT subject FROM (
            SELECT "Субъект федерации отп" AS subject FROM [{TABLE}]
            UNION
            SELECT "Субъект федерации наз" AS subject FROM [{TABLE}]
        )
        WHERE subject IS NOT NULL AND TRIM(subject) != ''
        ORDER BY subject
        """
    )
    regions_path = OUT_DIR / "regions.csv"
    with regions_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["region_shortname", "region_fullname", "Тип региона"])
        for row in cur.fetchall():
            full_name = (row["subject"] or "").strip()
            region_type = _parse_region_type(full_name)
            short_name = _region_short_name(full_name, region_type)
            writer.writerow([short_name, full_name, region_type])

    # --- Станции (отправление + назначение), одна строка на код ЕСР ---
    cur.execute(
        f"""
        SELECT
            esr_code,
            MAX(station_name) AS station_name,
            MAX(region_name) AS region_name,
            MAX(railroad_code) AS railroad_code
        FROM (
            SELECT
                "Код станц отпр РФ" AS esr_code,
                "Станц отпр РФ" AS station_name,
                "Субъект федерации отп" AS region_name,
                "Дор отпр" AS railroad_code
            FROM [{TABLE}]
            WHERE "Код станц отпр РФ" IS NOT NULL
            UNION ALL
            SELECT
                "Код станц назн РФ" AS esr_code,
                "Станц назн РФ" AS station_name,
                "Субъект федерации наз" AS region_name,
                "Дор наз" AS railroad_code
            FROM [{TABLE}]
            WHERE "Код станц назн РФ" IS NOT NULL
        )
        GROUP BY esr_code
        ORDER BY esr_code
        """
    )
    stations_path = OUT_DIR / "stations.csv"
    with stations_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            [
                "Код ЕСР",
                "shortname",
                "fullname",
                "region_shortname",
                "region_fullname",
                "Тип региона",
                "КОД дороги",
            ]
        )
        for row in cur.fetchall():
            esr = row["esr_code"]
            if esr is None:
                continue
            station_name = (row["station_name"] or "").strip()
            region_full = (row["region_name"] or "").strip() or "Не указан"
            region_type = _parse_region_type(region_full)
            region_short = _region_short_name(region_full, region_type)
            railroad = (row["railroad_code"] or "").strip()
            writer.writerow(
                [
                    int(esr),
                    station_name,
                    station_name,
                    region_short,
                    region_full,
                    region_type,
                    railroad,
                ]
            )

    # --- Грузы, одна строка на нормализованный 5-значный код ---
    cargos_path, skipped_cargos, cargo_warnings = _extract_cargos(cur)
    if skipped_cargos:
        print(f"  cargos: пропущено строк с невалидным кодом: {skipped_cargos}")
    if cargo_warnings:
        print("  cargos: предупреждения по аномальным кодам:")
        for warning, count in cargo_warnings.most_common():
            print(f"    {warning}: {count} строк")

    # --- Грузоотправители (компании-отправители) ---
    cur.execute(
        f"""
        SELECT
            "ОКПО_компании_отпр" AS okpo,
            "ИНН_компании" AS inn,
            "Наименование_компании" AS shipper_name,
            MAX("Холдинг") AS holding
        FROM [{TABLE}]
        WHERE "Наименование_компании" IS NOT NULL
          AND TRIM("Наименование_компании") NOT IN ('', '-', '0')
        GROUP BY "ОКПО_компании_отпр", "ИНН_компании", "Наименование_компании"
        ORDER BY shipper_name, okpo, inn
        """
    )
    shippers_path = OUT_DIR / "shippers.csv"
    with shippers_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            [
                "ОКПО",
                "ИНН",
                "Грузоотправитель",
                "Холдинг грузоотправителя",
            ]
        )
        for row in cur.fetchall():
            okpo = row["okpo"]
            inn = row["inn"]
            shipper = (row["shipper_name"] or "").strip()
            holding = (row["holding"] or "").strip()
            writer.writerow(
                [
                    "" if okpo is None else int(okpo),
                    "" if inn is None else str(inn).strip(),
                    shipper,
                    holding,
                ]
            )

    conn.close()

    print(f"Готово: {OUT_DIR}")
    for path in (regions_path, stations_path, cargos_path, shippers_path):
        with path.open(encoding="utf-8-sig") as f:
            lines = sum(1 for _ in f) - 1
        print(f"  {path.name}: {lines} строк")


if __name__ == "__main__":
    main()
