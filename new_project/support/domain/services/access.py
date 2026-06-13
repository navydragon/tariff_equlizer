from __future__ import annotations

from core.models import User
from support.domain.repositories import TaskRepository

ERR_TASK_NOT_FOUND = "Задача не найдена"
ERR_TASK_DELETE_DENIED = "Нет прав на удаление этой задачи"
ERR_COMMENT_DELETE_DENIED = "Нет прав на удаление этого комментария"
ERR_COMMENT_NOT_FOUND = "Комментарий не найден"
ERR_ATTACHMENT_NOT_FOUND = "Вложение не найдено"


class TaskAccessHelper:
    def __init__(self, repository: TaskRepository | None = None) -> None:
        self._repository = repository or TaskRepository()

    def require_task(self, task_id: int):
        task = self._repository.get_by_id(task_id)
        if not task:
            return None, [ERR_TASK_NOT_FOUND]
        return task, []

    def can_delete_task(self, task, user: User) -> bool:
        return task.author_id == user.id or user.is_staff

    def require_task_delete(self, task, user: User) -> list[str]:
        if self.can_delete_task(task, user):
            return []
        return [ERR_TASK_DELETE_DENIED]

    def can_delete_comment(self, comment, user: User) -> bool:
        return comment.author_id == user.id or user.is_staff

    def require_comment_delete(self, comment, user: User) -> list[str]:
        if self.can_delete_comment(comment, user):
            return []
        return [ERR_COMMENT_DELETE_DENIED]
