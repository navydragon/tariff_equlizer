from __future__ import annotations

import io
from typing import TYPE_CHECKING

from django.http import HttpResponse

if TYPE_CHECKING:
    from core.export.dto import ExportTable

from core.export.formatting import format_value_for_excel


class ExcelExportService:
    def build_workbook_bytes(self, table: ExportTable) -> bytes:
        from openpyxl import Workbook
        from openpyxl.styles import Font

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = table.sheet_title[:31]

        headers = [column.header for column in table.columns]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)

        keys = [column.key for column in table.columns]
        for row in table.rows:
            sheet.append(
                [format_value_for_excel(row.get(key, "")) for key in keys],
            )

        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()


def excel_response(*, filename: str, content: bytes) -> HttpResponse:
    response = HttpResponse(
        content,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
