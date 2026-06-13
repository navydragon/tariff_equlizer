import os
import uuid

from django.conf import settings
from django.db import models

from support.domain.constants import TASK_PRIORITIES, TASK_STATUSES, TASK_TYPES


def task_attachment_upload_to(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return f"support/attachments/{instance.task_id}/{uuid.uuid4().hex}{ext}"


class TaskTag(models.Model):
    name = models.CharField("Название", max_length=50, unique=True)
    color = models.CharField("Цвет", max_length=7, default="#206bc4")

    class Meta:
        verbose_name = "Тег задачи"
        verbose_name_plural = "Теги задач"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Task(models.Model):
    title = models.CharField("Заголовок", max_length=255)
    description = models.TextField("Описание", blank=True)
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=TASK_STATUSES,
        default="backlog",
        db_index=True,
    )
    priority = models.CharField(
        "Приоритет",
        max_length=20,
        choices=TASK_PRIORITIES,
        default="medium",
        db_index=True,
    )
    task_type = models.CharField(
        "Тип",
        max_length=20,
        choices=TASK_TYPES,
        default="question",
        db_index=True,
    )
    deadline = models.DateTimeField("Дедлайн", null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        on_delete=models.PROTECT,
        related_name="authored_tasks",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Исполнитель",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    scenario = models.ForeignKey(
        "scenarios.Scenario",
        verbose_name="Сценарий",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tasks",
    )
    tags = models.ManyToManyField(
        TaskTag,
        verbose_name="Теги",
        blank=True,
        related_name="tasks",
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)
    closed_at = models.DateTimeField("Закрыта", null=True, blank=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"#{self.pk} {self.title}"


class TaskComment(models.Model):
    task = models.ForeignKey(
        Task,
        verbose_name="Задача",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        on_delete=models.PROTECT,
        related_name="task_comments",
    )
    body = models.TextField("Текст")
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Комментарий #{self.pk} к задаче #{self.task_id}"


class TaskAttachment(models.Model):
    task = models.ForeignKey(
        Task,
        verbose_name="Задача",
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField("Файл", upload_to=task_attachment_upload_to)
    original_name = models.CharField("Имя файла", max_length=255)
    size = models.PositiveIntegerField("Размер")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Загрузил",
        on_delete=models.PROTECT,
        related_name="task_attachments",
    )
    created_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        verbose_name = "Вложение"
        verbose_name_plural = "Вложения"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.original_name


class TaskActivity(models.Model):
    task = models.ForeignKey(
        Task,
        verbose_name="Задача",
        on_delete=models.CASCADE,
        related_name="activities",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.PROTECT,
        related_name="task_activities",
    )
    action = models.CharField("Действие", max_length=50)
    field_name = models.CharField("Поле", max_length=50, blank=True)
    old_value = models.TextField("Старое значение", blank=True)
    new_value = models.TextField("Новое значение", blank=True)
    message = models.TextField("Сообщение", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Активность"
        verbose_name_plural = "Активности"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} по задаче #{self.task_id}"


class TaskWatcher(models.Model):
    task = models.ForeignKey(
        Task,
        verbose_name="Задача",
        on_delete=models.CASCADE,
        related_name="watchers",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Пользователь",
        on_delete=models.CASCADE,
        related_name="watched_tasks",
    )
    created_at = models.DateTimeField("Подписан", auto_now_add=True)

    class Meta:
        verbose_name = "Подписчик"
        verbose_name_plural = "Подписчики"
        unique_together = [("task", "user")]

    def __str__(self) -> str:
        return f"{self.user_id} → задача #{self.task_id}"
