from dataclasses import asdict
from datetime import datetime
from typing import Optional

from django.utils import timezone

from core.models import User
from support.domain.constants import PRIORITY_LABELS, STATUS_LABELS, TYPE_LABELS
from support.domain.dto import CreateTaskDTO, TaskDetailDTO, TaskFiltersDTO, TaskListDTO, UpdateTaskDTO
from support.domain.repositories import TaskRepository
from support.domain.services.access import TaskAccessHelper
from support.domain.services.activity import ActivityService


def _user_display_name(user) -> str:
    if user is None:
        return ""
    parts = [user.last_name, user.first_name]
    name = " ".join(p for p in parts if p).strip()
    return name or user.login


def _format_dt(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M")


def _is_overdue(task) -> bool:
    if not task.deadline or task.status in ("done", "cancelled"):
        return False
    return task.deadline < timezone.now()


class TaskService:
    def __init__(
        self,
        repository: TaskRepository | None = None,
        access: TaskAccessHelper | None = None,
        activity: ActivityService | None = None,
    ) -> None:
        self._repository = repository or TaskRepository()
        self._access = access or TaskAccessHelper(self._repository)
        self._activity = activity or ActivityService(self._repository)

    def _task_to_list_dto(self, task) -> TaskListDTO:
        return TaskListDTO(
            id=task.id,
            title=task.title,
            status=task.status,
            status_label=STATUS_LABELS.get(task.status, task.status),
            priority=task.priority,
            priority_label=PRIORITY_LABELS.get(task.priority, task.priority),
            task_type=task.task_type,
            task_type_label=TYPE_LABELS.get(task.task_type, task.task_type),
            deadline=_format_dt(task.deadline),
            is_overdue=_is_overdue(task),
            author_id=task.author_id,
            author_name=_user_display_name(task.author),
            assignee_id=task.assignee_id,
            assignee_name=_user_display_name(task.assignee) if task.assignee else None,
            scenario_id=task.scenario_id,
            scenario_name=task.scenario.name if task.scenario else None,
            tags=[{"id": t.id, "name": t.name, "color": t.color} for t in task.tags.all()],
            comments_count=getattr(task, "comments_count", 0),
            attachments_count=getattr(task, "attachments_count", 0),
            created_at=_format_dt(task.created_at) or "",
            updated_at=_format_dt(task.updated_at) or "",
        )

    def _task_to_detail_dto(self, task, user: User) -> TaskDetailDTO:
        from support.domain.dto import TaskCommentDTO

        comments = [
            TaskCommentDTO(
                id=c.id,
                author_id=c.author_id,
                author_name=_user_display_name(c.author),
                body=c.body,
                created_at=_format_dt(c.created_at) or "",
                updated_at=_format_dt(c.updated_at) or "",
            )
            for c in task.comments.all()
        ]
        attachments = [
            {
                "id": a.id,
                "original_name": a.original_name,
                "size": a.size,
                "url": a.file.url if a.file else "",
                "uploaded_by_name": _user_display_name(a.uploaded_by),
                "created_at": _format_dt(a.created_at) or "",
            }
            for a in task.attachments.all()
        ]
        activities = [
            {
                "id": act.id,
                "actor_name": _user_display_name(act.actor),
                "action": act.action,
                "field_name": act.field_name,
                "old_value": act.old_value,
                "new_value": act.new_value,
                "message": act.message,
                "created_at": _format_dt(act.created_at) or "",
            }
            for act in self._repository.get_activities(task.id)
        ]
        return TaskDetailDTO(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            status_label=STATUS_LABELS.get(task.status, task.status),
            priority=task.priority,
            priority_label=PRIORITY_LABELS.get(task.priority, task.priority),
            task_type=task.task_type,
            task_type_label=TYPE_LABELS.get(task.task_type, task.task_type),
            deadline=_format_dt(task.deadline),
            is_overdue=_is_overdue(task),
            author_id=task.author_id,
            author_name=_user_display_name(task.author),
            assignee_id=task.assignee_id,
            assignee_name=_user_display_name(task.assignee) if task.assignee else None,
            scenario_id=task.scenario_id,
            scenario_name=task.scenario.name if task.scenario else None,
            tags=[{"id": t.id, "name": t.name, "color": t.color} for t in task.tags.all()],
            comments=comments,
            attachments=attachments,
            activities=activities,
            watchers_count=getattr(task, "watchers_count", 0),
            is_watching=self._repository.is_watching(task.id, user.id),
            created_at=_format_dt(task.created_at) or "",
            updated_at=_format_dt(task.updated_at) or "",
            closed_at=_format_dt(task.closed_at),
        )

    def list_tasks(self, user: User, filters: TaskFiltersDTO) -> list[TaskListDTO]:
        filter_dict = asdict(filters)
        filter_dict["user_id"] = user.id
        tasks = self._repository.filter_tasks(filter_dict)
        return [self._task_to_list_dto(t) for t in tasks]

    def get_stats(self, user: User) -> dict:
        return self._repository.count_stats(user.id)

    def get_task(self, task_id: int, user: User) -> tuple[Optional[TaskDetailDTO], list[str]]:
        task, errors = self._access.require_task(task_id)
        if errors:
            return None, errors
        return self._task_to_detail_dto(task, user), []

    def create_task(self, user: User, dto: CreateTaskDTO) -> tuple[Optional[TaskDetailDTO], list[str]]:
        if not dto.title.strip():
            return None, ["Заголовок обязателен"]

        data = {
            "title": dto.title.strip(),
            "description": dto.description.strip(),
            "priority": dto.priority,
            "task_type": dto.task_type,
            "deadline": dto.deadline,
            "author_id": user.id,
            "assignee_id": dto.assignee_id,
            "scenario_id": dto.scenario_id,
            "tag_ids": dto.tag_ids,
        }
        task = self._repository.create(data)
        self._repository.add_watcher(task.id, user.id)
        self._activity.log_created(task_id=task.id, actor_id=user.id)
        return self._task_to_detail_dto(task, user), []

    def update_task(
        self, task_id: int, user: User, dto: UpdateTaskDTO
    ) -> tuple[Optional[TaskDetailDTO], list[str]]:
        task, errors = self._access.require_task(task_id)
        if errors:
            return None, errors

        update_data = {}
        if dto.title is not None:
            update_data["title"] = dto.title.strip()
        if dto.description is not None:
            update_data["description"] = dto.description.strip()
        if dto.status is not None:
            old = task.status
            update_data["status"] = dto.status
            if dto.status in ("done", "cancelled") and not task.closed_at:
                update_data["closed_at"] = timezone.now()
            elif dto.status not in ("done", "cancelled"):
                update_data["closed_at"] = None
            self._activity.log_field_change(
                task_id=task.id,
                actor_id=user.id,
                field_name="status",
                old_value=self._activity.format_status(old),
                new_value=self._activity.format_status(dto.status),
            )
        if dto.priority is not None:
            self._activity.log_field_change(
                task_id=task.id,
                actor_id=user.id,
                field_name="priority",
                old_value=self._activity.format_priority(task.priority),
                new_value=self._activity.format_priority(dto.priority),
            )
            update_data["priority"] = dto.priority
        if dto.task_type is not None:
            self._activity.log_field_change(
                task_id=task.id,
                actor_id=user.id,
                field_name="task_type",
                old_value=self._activity.format_type(task.task_type),
                new_value=self._activity.format_type(dto.task_type),
            )
            update_data["task_type"] = dto.task_type
        if dto.clear_deadline:
            self._activity.log_field_change(
                task_id=task.id,
                actor_id=user.id,
                field_name="deadline",
                old_value=_format_dt(task.deadline) or "",
                new_value="",
            )
            update_data["deadline"] = None
        elif dto.deadline is not None:
            self._activity.log_field_change(
                task_id=task.id,
                actor_id=user.id,
                field_name="deadline",
                old_value=_format_dt(task.deadline) or "",
                new_value=_format_dt(dto.deadline) or "",
            )
            update_data["deadline"] = dto.deadline
        if dto.clear_assignee:
            self._activity.log_field_change(
                task_id=task.id,
                actor_id=user.id,
                field_name="assignee",
                old_value=_user_display_name(task.assignee),
                new_value="",
            )
            update_data["assignee_id"] = None
        elif dto.assignee_id is not None:
            from core.models import User as UserModel

            new_assignee = UserModel.objects.filter(id=dto.assignee_id).first()
            self._activity.log_field_change(
                task_id=task.id,
                actor_id=user.id,
                field_name="assignee",
                old_value=_user_display_name(task.assignee),
                new_value=_user_display_name(new_assignee),
            )
            update_data["assignee_id"] = dto.assignee_id
        if dto.clear_scenario:
            update_data["scenario_id"] = None
        elif dto.scenario_id is not None:
            update_data["scenario_id"] = dto.scenario_id
        if dto.tag_ids is not None:
            update_data["tag_ids"] = dto.tag_ids

        if not update_data:
            return self._task_to_detail_dto(task, user), []

        updated = self._repository.update(task.id, update_data)
        return self._task_to_detail_dto(updated, user), []

    def update_status(
        self, task_id: int, user: User, status: str
    ) -> tuple[Optional[TaskListDTO], list[str]]:
        dto = UpdateTaskDTO(status=status)
        detail, errors = self.update_task(task_id, user, dto)
        if errors:
            return None, errors
        task, _ = self._access.require_task(task_id)
        return self._task_to_list_dto(task), []

    def delete_task(self, task_id: int, user: User) -> list[str]:
        task, errors = self._access.require_task(task_id)
        if errors:
            return errors
        delete_errors = self._access.require_task_delete(task, user)
        if delete_errors:
            return delete_errors
        self._repository.delete(task_id)
        return []

    def toggle_watch(self, task_id: int, user: User) -> tuple[bool, list[str]]:
        task, errors = self._access.require_task(task_id)
        if errors:
            return False, errors
        if self._repository.is_watching(task_id, user.id):
            self._repository.remove_watcher(task_id, user.id)
            return False, []
        self._repository.add_watcher(task_id, user.id)
        return True, []

    def get_tags(self) -> list[dict]:
        return [
            {"id": t.id, "name": t.name, "color": t.color}
            for t in self._repository.get_all_tags()
        ]

    def get_users(self) -> list[dict]:
        return [
            {"id": u.id, "name": _user_display_name(u), "login": u.login}
            for u in User.objects.filter(is_active=True).order_by("last_name", "first_name")
        ]

    def get_scenarios(self, user: User) -> list[dict]:
        from scenarios.domain.services import ScenarioService

        scenarios = ScenarioService().get_user_scenarios(user)
        return [{"id": s.id, "name": s.name} for s in scenarios]
