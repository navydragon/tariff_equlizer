from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from core.models import CargoGroup

_UNKNOWN_POSITION = 9_999
_SENTINEL_POSITION = 10_000


@lru_cache(maxsize=1)
def _cargo_group_positions() -> dict[str, int]:
    return dict(CargoGroup.objects.values_list("name", "position"))


def clear_cargo_group_position_cache() -> None:
    _cargo_group_positions.cache_clear()


def cargo_group_sort_key(name: str) -> tuple[int, str]:
    if name == "—":
        return (_SENTINEL_POSITION, "")
    position = _cargo_group_positions().get(name)
    if position is None:
        return (_UNKNOWN_POSITION, name)
    return (position, name)


def sort_cargo_group_names(names: Iterable[str]) -> list[str]:
    return sorted(names, key=cargo_group_sort_key)


def normalize_filter_options(
    filter_options: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    if not filter_options:
        return {}
    result = dict(filter_options)
    cargo_groups = result.get("cargo_groups")
    if cargo_groups:
        result["cargo_groups"] = sort_cargo_group_names(cargo_groups)
    return result


def sort_group_labels(labels: Iterable[str], *, dimension: str) -> list[str]:
    if dimension == "cargo_group":
        return sort_cargo_group_names(labels)
    return sorted(labels)


def group_key_sort_key(
    key: tuple[str, ...],
    *,
    group_by: str,
    group_by_inner: str,
) -> tuple[tuple[int, str], ...]:
    parts: list[tuple[int, str]] = []
    if len(key) >= 1:
        if group_by == "cargo_group":
            parts.append(cargo_group_sort_key(key[0]))
        else:
            parts.append((0, key[0]))
    if len(key) >= 2:
        if group_by_inner == "cargo_group":
            parts.append(cargo_group_sort_key(key[1]))
        else:
            parts.append((0, key[1]))
    return tuple(parts)
