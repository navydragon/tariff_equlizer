from __future__ import annotations

from core.models import Setting


class SettingRepository:
    def get_by_code(self, code: str) -> Setting | None:
        try:
            return Setting.objects.get(code=code)
        except Setting.DoesNotExist:
            return None

    def upsert(self, *, code: str, description: str, value: str) -> tuple[Setting, bool]:
        return Setting.objects.update_or_create(
            code=code,
            defaults={
                "description": description,
                "value": value,
            },
        )
