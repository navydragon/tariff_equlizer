from typing import Optional

from django.db.models import Count, Q, QuerySet

from support.models import Task, TaskActivity, TaskAttachment, TaskComment, TaskTag, TaskWatcher


class TaskRepository:
    def _base_queryset(self) -> QuerySet:
        return (
            Task.objects.select_related("author", "assignee", "scenario")
            .prefetch_related("tags")
            .annotate(
                comments_count=Count("comments", distinct=True),
                attachments_count=Count("attachments", distinct=True),
            )
        )

    def get_by_id(self, task_id: int) -> Optional[Task]:
        try:
            return (
                Task.objects.select_related("author", "assignee", "scenario")
                .prefetch_related("tags", "comments__author", "attachments__uploaded_by")
                .annotate(
                    comments_count=Count("comments", distinct=True),
                    attachments_count=Count("attachments", distinct=True),
                    watchers_count=Count("watchers", distinct=True),
                )
                .get(id=task_id)
            )
        except Task.DoesNotExist:
            return None

    def filter_tasks(self, filters: dict) -> list[Task]:
        qs = self._base_queryset()

        scope = filters.get("scope", "all")
        user_id = filters.get("user_id")

        if scope == "mine" and user_id:
            qs = qs.filter(assignee_id=user_id)
        elif scope == "authored" and user_id:
            qs = qs.filter(author_id=user_id)
        elif scope == "watching" and user_id:
            qs = qs.filter(watchers__user_id=user_id)

        if status := filters.get("status"):
            qs = qs.filter(status=status)
        if priority := filters.get("priority"):
            qs = qs.filter(priority=priority)
        if task_type := filters.get("task_type"):
            qs = qs.filter(task_type=task_type)
        if author_id := filters.get("author_id"):
            qs = qs.filter(author_id=author_id)
        if assignee_id := filters.get("assignee_id"):
            qs = qs.filter(assignee_id=assignee_id)
        if tag_id := filters.get("tag_id"):
            qs = qs.filter(tags__id=tag_id)
        if search := filters.get("search"):
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        if filters.get("overdue_only"):
            from django.utils import timezone

            qs = qs.filter(
                deadline__lt=timezone.now(),
                deadline__isnull=False,
            ).exclude(status__in=["done", "cancelled"])
        if filters.get("unassigned_only"):
            qs = qs.filter(assignee__isnull=True).exclude(status__in=["done", "cancelled"])

        return list(qs.distinct())

    def create(self, data: dict) -> Task:
        tag_ids = data.pop("tag_ids", [])
        task = Task.objects.create(**data)
        if tag_ids:
            task.tags.set(TaskTag.objects.filter(id__in=tag_ids))
        return self.get_by_id(task.id)

    def update(self, task_id: int, data: dict) -> Optional[Task]:
        try:
            task = Task.objects.get(id=task_id)
        except Task.DoesNotExist:
            return None

        tag_ids = data.pop("tag_ids", None)
        for key, value in data.items():
            setattr(task, key, value)
        task.save()
        if tag_ids is not None:
            task.tags.set(TaskTag.objects.filter(id__in=tag_ids))
        return self.get_by_id(task.id)

    def delete(self, task_id: int) -> bool:
        deleted, _ = Task.objects.filter(id=task_id).delete()
        return deleted > 0

    def get_comments(self, task_id: int) -> list[TaskComment]:
        return list(
            TaskComment.objects.filter(task_id=task_id)
            .select_related("author")
            .order_by("created_at")
        )

    def create_comment(self, task_id: int, author_id: int, body: str) -> TaskComment:
        return TaskComment.objects.create(task_id=task_id, author_id=author_id, body=body)

    def delete_comment(self, comment_id: int) -> bool:
        deleted, _ = TaskComment.objects.filter(id=comment_id).delete()
        return deleted > 0

    def get_comment(self, comment_id: int) -> Optional[TaskComment]:
        try:
            return TaskComment.objects.select_related("author", "task").get(id=comment_id)
        except TaskComment.DoesNotExist:
            return None

    def get_attachments(self, task_id: int) -> list[TaskAttachment]:
        return list(
            TaskAttachment.objects.filter(task_id=task_id)
            .select_related("uploaded_by")
            .order_by("-created_at")
        )

    def create_attachment(self, data: dict) -> TaskAttachment:
        return TaskAttachment.objects.create(**data)

    def get_attachment(self, attachment_id: int) -> Optional[TaskAttachment]:
        try:
            return TaskAttachment.objects.select_related("task", "uploaded_by").get(
                id=attachment_id
            )
        except TaskAttachment.DoesNotExist:
            return None

    def delete_attachment(self, attachment_id: int) -> bool:
        attachment = self.get_attachment(attachment_id)
        if not attachment:
            return False
        if attachment.file:
            attachment.file.delete(save=False)
        attachment.delete()
        return True

    def log_activity(self, data: dict) -> TaskActivity:
        return TaskActivity.objects.create(**data)

    def get_activities(self, task_id: int) -> list[TaskActivity]:
        return list(
            TaskActivity.objects.filter(task_id=task_id)
            .select_related("actor")
            .order_by("-created_at")
        )

    def add_watcher(self, task_id: int, user_id: int) -> None:
        TaskWatcher.objects.get_or_create(task_id=task_id, user_id=user_id)

    def remove_watcher(self, task_id: int, user_id: int) -> None:
        TaskWatcher.objects.filter(task_id=task_id, user_id=user_id).delete()

    def is_watching(self, task_id: int, user_id: int) -> bool:
        return TaskWatcher.objects.filter(task_id=task_id, user_id=user_id).exists()

    def get_all_tags(self) -> list[TaskTag]:
        return list(TaskTag.objects.all())

    def get_or_create_tag(self, name: str) -> TaskTag:
        tag, _ = TaskTag.objects.get_or_create(name=name.strip())
        return tag

    def count_stats(self, user_id: int) -> dict:
        from django.utils import timezone

        now = timezone.now()
        base = Task.objects.exclude(status__in=["done", "cancelled"])
        return {
            "open": base.count(),
            "mine": base.filter(assignee_id=user_id).count(),
            "authored": Task.objects.filter(author_id=user_id).count(),
            "overdue": base.filter(deadline__lt=now, deadline__isnull=False).count(),
            "unassigned": base.filter(assignee__isnull=True).count(),
        }
