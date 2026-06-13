from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("", views.task_list_view, name="task_list"),
    path("tasks/<int:task_id>/", views.task_detail_view, name="task_detail"),
    path("api/tasks/", views.task_list_api, name="api_task_list"),
    path("api/tasks/<int:task_id>/", views.task_detail_api, name="api_task_detail"),
    path("api/tasks/<int:task_id>/status/", views.task_status_api, name="api_task_status"),
    path("api/tasks/<int:task_id>/comments/", views.task_comments_api, name="api_task_comments"),
    path(
        "api/tasks/<int:task_id>/attachments/",
        views.task_attachments_api,
        name="api_task_attachments",
    ),
    path(
        "api/tasks/<int:task_id>/watch/",
        views.task_watch_api,
        name="api_task_watch",
    ),
    path("api/comments/<int:comment_id>/", views.comment_delete_api, name="api_comment_delete"),
    path(
        "api/attachments/<int:attachment_id>/",
        views.attachment_delete_api,
        name="api_attachment_delete",
    ),
    path("api/tags/", views.tags_api, name="api_tags"),
    path("api/users/", views.users_api, name="api_users"),
    path("api/scenarios/", views.scenarios_api, name="api_scenarios"),
]
