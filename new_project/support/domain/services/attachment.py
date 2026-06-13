import os

from django.conf import settings

from core.models import User
from support.domain.repositories import TaskRepository
from support.domain.services.access import TaskAccessHelper
from support.domain.services.activity import ActivityService


class AttachmentService:
    def __init__(
        self,
        repository: TaskRepository | None = None,
        access: TaskAccessHelper | None = None,
        activity: ActivityService | None = None,
    ) -> None:
        self._repository = repository or TaskRepository()
        self._access = access or TaskAccessHelper(self._repository)
        self._activity = activity or ActivityService(self._repository)

    def _validate_file(self, uploaded_file) -> list[str]:
        if not uploaded_file:
            return ["Файл не передан"]
        max_size = getattr(settings, "SUPPORT_MAX_ATTACHMENT_SIZE", 10 * 1024 * 1024)
        if uploaded_file.size > max_size:
            return [f"Размер файла превышает {max_size // (1024 * 1024)} МБ"]
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        allowed = getattr(
            settings,
            "SUPPORT_ALLOWED_ATTACHMENT_EXTENSIONS",
            {".pdf", ".xlsx", ".png", ".jpg"},
        )
        if ext not in allowed:
            return [f"Тип файла {ext} не разрешён"]
        return []

    def upload(self, task_id: int, user: User, uploaded_file) -> tuple[dict | None, list[str]]:
        _, errors = self._access.require_task(task_id)
        if errors:
            return None, errors
        validation_errors = self._validate_file(uploaded_file)
        if validation_errors:
            return None, validation_errors

        attachment = self._repository.create_attachment(
            {
                "task_id": task_id,
                "file": uploaded_file,
                "original_name": uploaded_file.name,
                "size": uploaded_file.size,
                "uploaded_by_id": user.id,
            }
        )
        self._activity.log_attachment_added(
            task_id=task_id,
            actor_id=user.id,
            filename=attachment.original_name,
        )

        from support.domain.services.task import _format_dt, _user_display_name

        return {
            "id": attachment.id,
            "original_name": attachment.original_name,
            "size": attachment.size,
            "url": attachment.file.url,
            "uploaded_by_name": _user_display_name(user),
            "created_at": _format_dt(attachment.created_at) or "",
        }, []

    def delete(self, attachment_id: int, user: User) -> list[str]:
        attachment = self._repository.get_attachment(attachment_id)
        if not attachment:
            return ["Вложение не найдено"]
        filename = attachment.original_name
        task_id = attachment.task_id
        self._repository.delete_attachment(attachment_id)
        self._activity.log_attachment_removed(
            task_id=task_id,
            actor_id=user.id,
            filename=filename,
        )
        return []
