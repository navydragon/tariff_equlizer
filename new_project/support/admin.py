from django.contrib import admin

from support.models import Task, TaskActivity, TaskAttachment, TaskComment, TaskTag, TaskWatcher


@admin.register(TaskTag)
class TaskTagAdmin(admin.ModelAdmin):
    list_display = ("name", "color")
    search_fields = ("name",)


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 0
    readonly_fields = ("author", "created_at")


class TaskAttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 0
    readonly_fields = ("uploaded_by", "created_at", "size")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "priority",
        "task_type",
        "author",
        "assignee",
        "deadline",
        "updated_at",
    )
    list_filter = ("status", "priority", "task_type")
    search_fields = ("title", "description")
    filter_horizontal = ("tags",)
    inlines = [TaskCommentInline, TaskAttachmentInline]


@admin.register(TaskActivity)
class TaskActivityAdmin(admin.ModelAdmin):
    list_display = ("task", "actor", "action", "field_name", "created_at")
    list_filter = ("action",)


@admin.register(TaskWatcher)
class TaskWatcherAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "created_at")
