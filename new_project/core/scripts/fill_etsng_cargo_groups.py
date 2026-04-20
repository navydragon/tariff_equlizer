import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Tuple, List


BASE_DIR = Path(__file__).resolve().parents[1]  # .../new_project/core
DATA_DIR = BASE_DIR / "data"

DEFAULT_ETSNG_PATH = DATA_DIR / "etsng.csv"
DEFAULT_CARGO_GROUPS_PATH = DATA_DIR / "cargo_groups.csv"
DEFAULT_MAPPING_PATH = DATA_DIR / "etsng_to_cargo_group_map.csv"
DEFAULT_OUTPUT_PATH = DATA_DIR / "etsng_filled.csv"
DEFAULT_UNMAPPED_PATH = DATA_DIR / "etsng_unmapped.csv"


def load_cargo_groups(path: Path) -> Dict[str, str]:
    groups: Dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"Файл групп грузов не найден: {path}")

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        expected = {"name", "position", "code"}
        if set(reader.fieldnames or []) != expected:
            raise ValueError(
                f"Неожиданные заголовки в {path}: {reader.fieldnames}. "
                f"Ожидались столбцы {sorted(expected)}"
            )
        for row in reader:
            code = (row.get("code") or "").strip()
            name = (row.get("name") or "").strip()
            if not code:
                continue
            groups[code] = name
    if not groups:
        raise ValueError(f"В файле групп грузов {path} нет записей.")
    return groups


def detect_etsng_indices(header: List[str]) -> Tuple[int, int, int]:
    """
    Определяем индексы столбцов ETSNG:
    'Код', 'Наименование', 'Код группы груза'.
    Если что‑то не найдено, стараемся использовать позиции по умолчанию.
    """
    code_idx = name_idx = group_idx = None

    for i, col in enumerate(header):
        col_norm = col.strip().lower()
        if "код группы" in col_norm:
            group_idx = i
        elif col_norm == "код":
            code_idx = i
        elif "наимен" in col_norm:
            name_idx = i

    # Запасные значения по позициям
    if code_idx is None:
        code_idx = 0
    if name_idx is None:
        name_idx = 1 if len(header) > 1 else 0
    if group_idx is None:
        group_idx = len(header)

    return code_idx, name_idx, group_idx


def ensure_mapping_template(
    mapping_path: Path,
    etsng_path: Path,
    cargo_groups: Dict[str, str],
) -> None:
    """
    Если файла соответствий нет, создаём шаблон
    etsng_code;etsng_name;cargo_group_code;cargo_group_name
    на основе текущего etsng.csv и выходим.
    """
    if mapping_path.exists():
        return

    if not etsng_path.exists():
        raise FileNotFoundError(f"Файл ETSNG не найден: {etsng_path}")

    print(
        f"Файл соответствий {mapping_path} не найден. "
        f"Создаю шаблон на основе {etsng_path}..."
    )

    seen_codes = set()
    rows_for_mapping: List[Tuple[str, str, str, str]] = []

    with etsng_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"Файл ETSNG пуст: {etsng_path}")

        code_idx, name_idx, group_idx = detect_etsng_indices(header)

        for row in reader:
            if not row:
                continue
            # Расширяем строку до нужной длины
            if len(row) <= max(code_idx, name_idx, group_idx):
                row += [""] * (max(code_idx, name_idx, group_idx) + 1 - len(row))

            code = (row[code_idx] or "").strip()
            name = (row[name_idx] or "").strip()

            if not code or code in seen_codes:
                continue

            seen_codes.add(code)

            existing_group_code = ""
            existing_group_name = ""
            if group_idx < len(row):
                existing_group_code = (row[group_idx] or "").strip()
                if existing_group_code and existing_group_code in cargo_groups:
                    existing_group_name = cargo_groups[existing_group_code]
                else:
                    existing_group_code = ""
                    existing_group_name = ""

            rows_for_mapping.append(
                (code, name, existing_group_code, existing_group_name)
            )

    with mapping_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            ["etsng_code", "etsng_name", "cargo_group_code", "cargo_group_name"]
        )
        for code, name, group_code, group_name in rows_for_mapping:
            writer.writerow([code, name, group_code, group_name])

    print(
        f"Создан шаблон файла соответствий: {mapping_path}\n"
        f"Заполните столбец 'cargo_group_code' (и при желании 'cargo_group_name'), "
        f"используя коды 1–11 из cargo_groups.csv, затем запустите скрипт повторно."
    )
    # После создания шаблона намеренно завершаем работу, не трогая etsng.csv
    sys.exit(0)


def load_mapping(
    mapping_path: Path,
    cargo_groups: Dict[str, str],
) -> Dict[str, Tuple[str, str]]:
    """
    Читаем etsng_to_cargo_group_map.csv и возвращаем словарь:
    etsng_code -> (cargo_group_code, cargo_group_name)
    """
    mapping: Dict[str, Tuple[str, str]] = {}
    if not mapping_path.exists():
        raise FileNotFoundError(
            f"Файл соответствий не найден: {mapping_path}. "
            f"Сначала создайте шаблон (запуском этого скрипта без готового файла) "
            f"и заполните его."
        )

    with mapping_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        expected = {
            "etsng_code",
            "etsng_name",
            "cargo_group_code",
            "cargo_group_name",
        }
        if set(reader.fieldnames or []) != expected:
            raise ValueError(
                f"Неожиданные заголовки в {mapping_path}: {reader.fieldnames}. "
                f"Ожидались столбцы {sorted(expected)}"
            )

        errors: List[str] = []
        for row in reader:
            code = (row.get("etsng_code") or "").strip()
            if not code:
                continue

            group_code = (row.get("cargo_group_code") or "").strip()
            group_name = (row.get("cargo_group_name") or "").strip()

            if group_code:
                if group_code not in cargo_groups:
                    errors.append(
                        f"Код группы '{group_code}' для ETSNG {code} "
                        f"отсутствует в cargo_groups.csv"
                    )
                if not group_name:
                    group_name = cargo_groups.get(group_code, "")

            mapping[code] = (group_code, group_name)

    if errors:
        msg = "Ошибки в файле соответствий:\n" + "\n".join(errors)
        raise ValueError(msg)

    return mapping


def fill_etsng_with_groups(
    etsng_path: Path,
    cargo_groups_path: Path,
    mapping_path: Path,
    output_path: Path,
    unmapped_path: Path,
) -> None:
    cargo_groups = load_cargo_groups(cargo_groups_path)
    ensure_mapping_template(mapping_path, etsng_path, cargo_groups)
    mapping = load_mapping(mapping_path, cargo_groups)

    if not etsng_path.exists():
        raise FileNotFoundError(f"Файл ETSNG не найден: {etsng_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    unmapped_path.parent.mkdir(parents=True, exist_ok=True)

    counts_by_group: Dict[str, int] = defaultdict(int)
    unmapped_rows: List[Tuple[str, str, str]] = []

    with etsng_path.open(encoding="utf-8-sig", newline="") as src, output_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as dst:
        reader = csv.reader(src, delimiter=";")
        writer = csv.writer(dst, delimiter=";")

        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"Файл ETSNG пуст: {etsng_path}")

        code_idx, name_idx, group_idx = detect_etsng_indices(header)

        # Обеспечиваем наличие столбца "Код группы груза"
        if group_idx >= len(header):
            header.append("Код группы груза")
        writer.writerow(header)

        for row in reader:
            if not row:
                continue

            # Расширяем строку до нужной длины
            max_idx = max(code_idx, name_idx, group_idx)
            if len(row) <= max_idx:
                row += [""] * (max_idx + 1 - len(row))

            code = (row[code_idx] or "").strip()
            name = (row[name_idx] or "").strip()
            current_group = (row[group_idx] or "").strip()

            mapped_group_code = ""
            mapped_group_name = ""

            if code in mapping:
                mapped_group_code, mapped_group_name = mapping[code]

            if mapped_group_code:
                row[group_idx] = mapped_group_code
                counts_by_group[mapped_group_code] += 1
            else:
                # Если в исходном файле уже есть код группы, проверяем его валидность
                if current_group and current_group in cargo_groups:
                    counts_by_group[current_group] += 1
                else:
                    unmapped_rows.append((code, name, current_group))

            writer.writerow(row)

    # Записываем непроставленные/проблемные строки
    with unmapped_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["etsng_code", "etsng_name", "raw_group_code"])
        for code, name, raw_group in unmapped_rows:
            writer.writerow([code, name, raw_group])

    total_filled = sum(counts_by_group.values())

    print(f"Результат записан в: {output_path}")
    print(f"Файл с непроставленными/проблемными строками: {unmapped_path}")
    print(f"Всего строк с проставленным кодом группы: {total_filled}")
    print("Распределение по кодам групп:")
    for group_code, count in sorted(counts_by_group.items(), key=lambda x: x[0]):
        name = cargo_groups.get(group_code, "")
        print(f"  Группа {group_code} ({name}): {count}")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Заполнение столбца 'Код группы груза' в ETSNG на основе "
            "ручного справочника соответствий и файла cargo_groups.csv."
        )
    )
    parser.add_argument(
        "--etsng-path",
        type=Path,
        default=DEFAULT_ETSNG_PATH,
        help=f"Путь к etsng.csv (по умолчанию: {DEFAULT_ETSNG_PATH})",
    )
    parser.add_argument(
        "--cargo-groups-path",
        type=Path,
        default=DEFAULT_CARGO_GROUPS_PATH,
        help=f"Путь к cargo_groups.csv (по умолчанию: {DEFAULT_CARGO_GROUPS_PATH})",
    )
    parser.add_argument(
        "--mapping-path",
        type=Path,
        default=DEFAULT_MAPPING_PATH,
        help=(
            "Путь к etsng_to_cargo_group_map.csv "
            f"(по умолчанию: {DEFAULT_MAPPING_PATH})"
        ),
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Путь для сохранения заполненного ETSNG (по умолчанию: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--unmapped-path",
        type=Path,
        default=DEFAULT_UNMAPPED_PATH,
        help=(
            "Путь для отчёта по строкам без валидного кода группы "
            f"(по умолчанию: {DEFAULT_UNMAPPED_PATH})"
        ),
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> None:
    args = parse_args(argv)
    fill_etsng_with_groups(
        etsng_path=args.etsng_path,
        cargo_groups_path=args.cargo_groups_path,
        mapping_path=args.mapping_path,
        output_path=args.output_path,
        unmapped_path=args.unmapped_path,
    )


if __name__ == "__main__":
    main(sys.argv[1:])

