from core.models import User
from support.domain.repositories import TaskRepository
from support.domain.services.access import TaskAccessHelper
from support.domain.services.activity import ActivityService


class CommentService:
    def __init__(
        self,
        repository: TaskRepository | None = None,
        access: TaskAccessHelper | None = None,
        activity: ActivityService | None = None,
    ) -> None:
        self._repository = repository or TaskRepository()
        self._access = access or TaskAccessHelper(self._repository)
        self._activity = activity or ActivityService(self._repository)

    def add_comment(self, task_id: int, user: User, body: str) -> tuple[dict | None, list[str]]:
        _, errors = self._access.require_task(task_id)
        if errors:
            return None, errors
        if not body.strip():
            return None, ["Текст комментария обязателен"]

        comment = self._repository.create_comment(task_id, user.id, body.strip())
        self._activity.log_comment_added(task_id=task_id, actor_id=user.id)
        self._repository.add_watcher(task_id, user.id)

        from support.domain.services.task import _user_display_name, _format_dt

        return {
            "id": comment.id,
            "author_id": comment.author_id,
            "author_name": _user_display_name(user),
            "body": comment.body,
            "created_at": _format_dt(comment.created_at) or "",
            "updated_at": _format_dt(comment.updated_at) or "",
        }, []

    def delete_comment(self, comment_id: int, user: User) -> list[str]:
        comment = self._repository.get_comment(comment_id)
        if not comment:
            return ["Комментарий не найден"]
        errors = self._access.require_comment_delete(comment, user)
        if errors:
            return errors
        self._repository.delete_comment(comment_id)
        return []
