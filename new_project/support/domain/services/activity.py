from support.domain.constants import PRIORITY_LABELS, STATUS_LABELS, TYPE_LABELS
from support.domain.repositories import TaskRepository


class ActivityService:
    def __init__(self, repository: TaskRepository | None = None) -> None:
        self._repository = repository or TaskRepository()

    def log_field_change(
        self,
        *,
        task_id: int,
        actor_id: int,
        field_name: str,
        old_value: str,
        new_value: str,
        action: str = "field_changed",
    ) -> None:
        if old_value == new_value:
            return
        self._repository.log_activity(
            {
                "task_id": task_id,
                "actor_id": actor_id,
                "action": action,
                "field_name": field_name,
                "old_value": old_value,
                "new_value": new_value,
            }
        )

    def log_created(self, *, task_id: int, actor_id: int) -> None:
        self._repository.log_activity(
            {
                "task_id": task_id,
                "actor_id": actor_id,
                "action": "created",
                "message": "Задача создана",
            }
        )

    def log_comment_added(self, *, task_id: int, actor_id: int) -> None:
        self._repository.log_activity(
            {
                "task_id": task_id,
                "actor_id": actor_id,
                "action": "comment_added",
                "message": "Добавлен комментарий",
            }
        )

    def log_attachment_added(self, *, task_id: int, actor_id: int, filename: str) -> None:
        self._repository.log_activity(
            {
                "task_id": task_id,
                "actor_id": actor_id,
                "action": "attachment_added",
                "message": f"Добавлен файл: {filename}",
            }
        )

    def log_attachment_removed(self, *, task_id: int, actor_id: int, filename: str) -> None:
        self._repository.log_activity(
            {
                "task_id": task_id,
                "actor_id": actor_id,
                "action": "attachment_removed",
                "message": f"Удалён файл: {filename}",
            }
        )

    @staticmethod
    def format_status(value: str) -> str:
        return STATUS_LABELS.get(value, value)

    @staticmethod
    def format_priority(value: str) -> str:
        return PRIORITY_LABELS.get(value, value)

    @staticmethod
    def format_type(value: str) -> str:
        return TYPE_LABELS.get(value, value)
