import csv
import sys
from pathlib import Path
from typing import Dict, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]  # .../new_project/core
DATA_DIR = BASE_DIR / "data"

MAPPING_PATH = DATA_DIR / "etsng_to_cargo_group_map.csv"
CARGO_GROUPS_PATH = DATA_DIR / "cargo_groups.csv"


def load_cargo_groups(path: Path) -> Dict[str, str]:
    groups: Dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            code = (row.get("code") or "").strip()
            name = (row.get("name") or "").strip()
            if code:
                groups[code] = name
    if not groups:
        raise ValueError(f"В {path} не найдено ни одной группы грузов.")
    return groups


def classify_name(name: str) -> str:
    """
    Эвристическое отнесение по наименованию к одной из 11 групп:
    1 — уголь каменный
    2 — кокс каменноугольный
    3 — чёрные металлы
    4 — лесные грузы
    5 — минерально-строительные
    6 — удобрения
    7 — хлебные грузы
    8 — нефтяные грузы
    9 — руды всякие
    10 — остальные грузы
    11 — грузы на своих осях
    """
    n = name.upper()

    # 11 — грузы на своих осях
    if "СВОИХ ОСЯХ" in n or "СОБСТВЕННЫМ ХОДОМ" in n or "НА СОБСТВЕННОМ ХОДУ" in n:
        return "11"

    # 1 — уголь каменный
    if "УГОЛЬ" in n or "АНТРАЦИТ" in n:
        # но кокс каменноугольный отдельная группа
        if "КОКС" not in n:
            return "1"

    # 2 — кокс каменноугольный
    if "КОКС" in n:
        return "2"

    # 3 — чёрные металлы
    if any(
        kw in n
        for kw in [
            "СТАЛЬ",
            "ЧУГУН",
            "ФЕРРОСПЛАВ",
            "АРМАТУР",
            "ПРОКАТ",
            "РЕЛЬС",
            "БАЛКА",
            "ШАРИКИ СТАЛЬНЫЕ",
            "ПРУТКИ",
            "ЛИСТЫ СТАЛЬНЫЕ",
            "ТРУБЫ СТАЛЬНЫЕ",
        ]
    ):
        return "3"

    # 4 — лесные грузы (круглый лес, пиломатериалы, балансы, щепа, древесина)
    if any(
        kw in n
        for kw in [
            "ЛЕС",
            "КРУГЛЯК",
            "БРЕВНА",
            "БАЛАНС",
            "ДРЕВЕСИНА",
            "ПИЛОМАТЕРИАЛ",
            "ДОСКИ",
            "БРУС",
            "ЩЕПА ДРЕВЕСНАЯ",
            "ХВОСТЫ ЛЕСНЫЕ",
        ]
    ):
        return "4"

    # 5 — минерально-строительные
    if any(
        kw in n
        for kw in [
            "ЩЕБЕНЬ",
            "ПЕСОК",
            "ГРАВИЙ",
            "ГАЛЬКА",
            "ГЛИНА",
            "ЦЕМЕНТ",
            "ИЗВЕСТЬ",
            "КИРПИЧ",
            "КАМЕНЬ",
            "БЕТОН",
            "СУХИЕ СТРОИТЕЛЬНЫЕ СМЕСИ",
            "МЕЛЬНИЧНЫЙ КАМЕНЬ",
            "ГИПС",
            "ШЛАК СТРОИТЕЛЬНЫЙ",
        ]
    ):
        return "5"

    # 6 — удобрения
    if any(
        kw in n
        for kw in [
            "УДОБРЕНИЯ",
            "СЕЛИТРА",
            "СУПЕРФОСФАТ",
            "АММИАЧНАЯ СЕЛИТРА",
            "НИТРОФОСКА",
            "КАРБАМИД",
        ]
    ):
        return "6"

    # 7 — хлебные грузы (зерно, мука, крупы, бобовые, комбикорма и т.п.)
    if any(
        kw in n
        for kw in [
            "ЗЕРНО",
            "ЗЕРНОВЫЕ",
            "ПШЕНИЦА",
             "РОЖЬ",
            "ЯЧМЕНЬ",
            "ОВЕС",
            "ОВЁС",
            "КУКУРУЗА",
            "РИС",
            "МУКА",
            "КРУПА",
            "КОМБИКОРМ",
            "КОРМОВОЕ ЗЕРНО",
            "БОБОВ",
            "ГОРОХ",
            "ФАСОЛИ",
            "СОЛОД",
        ]
    ):
        return "7"

    # 8 — нефтяные грузы
    if any(
        kw in n
        for kw in [
            "НЕФТЬ",
            "БЕНЗИН",
            "ДИЗЕЛЬ",
            "ТОПЛИВО",
            "МАСЛО НЕФТЯНОЕ",
            "МАСЛА НЕФТЯНЫЕ",
            "КЕРОСИН",
            "МАЗУТ",
            "БИТУМ НЕФТЯНОЙ",
        ]
    ):
        return "8"

    # 9 — руды всякие
    if any(
        kw in n
        for kw in [
            "РУДА",
            "РУДЫ",
            "КОНЦЕНТРАТ ЖЕЛЕЗОРУДНЫЙ",
            "АГЛОМЕРАТ ЖЕЛЕЗОРУДНЫЙ",
        ]
    ):
        return "9"

    # Остальные — 10
    return "10"


def auto_fill_mapping(
    mapping_path: Path,
    cargo_groups: Dict[str, str],
) -> Tuple[int, int]:
    """
    Заполняет пустые cargo_group_code в etsng_to_cargo_group_map.csv
    по эвристикам из наименования. Возвращает (изменено, всего_строк).
    """
    if not mapping_path.exists():
        raise FileNotFoundError(f"Не найден файл соответствий: {mapping_path}")

    with mapping_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if set(fieldnames) != {
        "etsng_code",
        "etsng_name",
        "cargo_group_code",
        "cargo_group_name",
    }:
        raise ValueError(
            f"Неожиданные заголовки в {mapping_path}: {fieldnames}. "
            "Ожидаются столбцы: etsng_code;etsng_name;cargo_group_code;cargo_group_name"
        )

    changed = 0
    total = len(rows)

    for row in rows:
        name = (row.get("etsng_name") or "").strip()
        group_code = (row.get("cargo_group_code") or "").strip()

        # Полностью пустые наименования: относим к "остальным" как к безопасному
        # значению по умолчанию, если код группы ещё не задан.
        if not name and not group_code:
            row["cargo_group_code"] = "10"
            row["cargo_group_name"] = cargo_groups.get("10", "")
            changed += 1
            continue

        if not name:
            continue

        guessed = classify_name(name)

        # Не трогаем коды групп, отличные от 10 (Остальные грузы), предполагая, что
        # они выставлены вручную/точно. Но можем "уточнить" 10 по эвристике.
        if group_code and group_code != "10":
            continue

        if guessed and guessed != group_code:
            row["cargo_group_code"] = guessed
            row["cargo_group_name"] = cargo_groups.get(guessed, "")
            changed += 1

    with mapping_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(rows)

    return changed, total


def main() -> None:
    cargo_groups = load_cargo_groups(CARGO_GROUPS_PATH)
    changed, total = auto_fill_mapping(MAPPING_PATH, cargo_groups)
    print(
        f"Автозаполнение завершено. Обновлено {changed} строк из {total} "
        f"в файле {MAPPING_PATH}."
    )


if __name__ == "__main__":
    main()

