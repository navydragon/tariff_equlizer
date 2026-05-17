from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExportColumn:
    key: str
    header: str


@dataclass(frozen=True)
class ExportTable:
    sheet_title: str
    columns: list[ExportColumn]
    rows: list[dict[str, str]] = field(default_factory=list)
