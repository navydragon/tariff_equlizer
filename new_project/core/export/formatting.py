from __future__ import annotations

from decimal import Decimal, InvalidOperation


def format_value_for_excel(value: object) -> object:
    """
    Подготовка значения для ячейки Excel в локали с запятой как десятичным
    разделителем (1,234 вместо 1.234).
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value

    if isinstance(value, Decimal):
        text = format(value, "f")
    elif isinstance(value, float):
        text = format(value, "f")
    else:
        text = str(value).strip()
        if not text:
            return ""

    normalized = text.replace(" ", "").replace(",", ".")
    try:
        Decimal(normalized)
    except InvalidOperation:
        return text

    if "," in text:
        return text
    if "." in text:
        return text.replace(".", ",")
    return text
