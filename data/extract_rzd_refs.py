"""Извлечение DISTINCT CSV справочников из базы РЖД (ИХ_ГП)."""

from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "01_2026-05-19.db"
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


def _parse_cargo_code(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
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

    # --- Грузы, одна строка на код ---
    cur.execute(
        f"""
        SELECT
            "Код груза" AS cargo_code,
            MAX("Наим груза") AS cargo_name,
            MAX("Код группы груза") AS group_code
        FROM [{TABLE}]
        WHERE "Код груза" IS NOT NULL AND TRIM("Код груза") != ''
        GROUP BY "Код груза"
        ORDER BY cargo_code
        """
    )
    cargos_path = OUT_DIR / "cargos.csv"
    skipped_cargos = 0
    with cargos_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Код", "Наименование", "Код группы груза"])
        for row in cur.fetchall():
            code = _parse_cargo_code(row["cargo_code"])
            if code is None:
                skipped_cargos += 1
                continue
            name = (row["cargo_name"] or "").strip()
            group_code = row["group_code"]
            writer.writerow([code, name, group_code if group_code is not None else ""])

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
