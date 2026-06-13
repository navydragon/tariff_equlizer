import json
from dataclasses import asdict
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from support.domain.constants import KANBAN_STATUSES, PRIORITY_LABELS, STATUS_LABELS, TYPE_LABELS
from support.domain.dto import CreateTaskDTO, TaskFiltersDTO, UpdateTaskDTO
from support.domain.services import AttachmentService, CommentService, TaskService


def _json_error(errors: list[str], status: int = 400) -> JsonResponse:
    return JsonResponse({"success": False, "errors": errors}, status=status)


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _parse_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()


@login_required
def task_list_view(request):
    return render(
        request,
        "support/task_list.html",
        {
            "statuses": STATUS_LABELS,
            "priorities": PRIORITY_LABELS,
            "types": TYPE_LABELS,
            "kanban_statuses": KANBAN_STATUSES,
            "kanban_statuses_json": json.dumps(KANBAN_STATUSES),
            "status_labels_json": json.dumps(STATUS_LABELS, ensure_ascii=False),
        },
    )


@login_required
def task_detail_view(request, task_id: int):
    service = TaskService()
    task, errors = service.get_task(task_id, request.user)
    if errors:
        return render(request, "support/task_not_found.html", status=404)

    deadline_iso = ""
    from support.models import Task as TaskModel

    task_obj = TaskModel.objects.get(id=task_id)
    if task_obj.deadline:
        local = timezone.localtime(task_obj.deadline)
        deadline_iso = local.strftime("%Y-%m-%dT%H:%M")

    return render(
        request,
        "support/task_detail.html",
        {
            "task": task,
            "deadline_iso": deadline_iso,
            "statuses": STATUS_LABELS,
            "priorities": PRIORITY_LABELS,
            "types": TYPE_LABELS,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def task_list_api(request):
    service = TaskService()
    if request.method == "GET":
        params = request.GET
        filters = TaskFiltersDTO(
            scope=params.get("scope", "all"),
            status=params.get("status") or None,
            priority=params.get("priority") or None,
            task_type=params.get("task_type") or None,
            author_id=int(params["author_id"]) if params.get("author_id") else None,
            assignee_id=int(params["assignee_id"]) if params.get("assignee_id") else None,
            tag_id=int(params["tag_id"]) if params.get("tag_id") else None,
            search=params.get("search", ""),
            overdue_only=params.get("overdue_only") == "true",
            unassigned_only=params.get("unassigned_only") == "true",
        )
        tasks = service.list_tasks(request.user, filters)
        stats = service.get_stats(request.user)
        return JsonResponse(
            {
                "success": True,
                "tasks": [asdict(t) for t in tasks],
                "stats": stats,
            }
        )

    data = _parse_body(request)
    dto = CreateTaskDTO(
        title=data.get("title", ""),
        description=data.get("description", ""),
        priority=data.get("priority", "medium"),
        task_type=data.get("task_type", "question"),
        deadline=_parse_datetime(data.get("deadline")),
        assignee_id=int(data["assignee_id"]) if data.get("assignee_id") else None,
        scenario_id=int(data["scenario_id"]) if data.get("scenario_id") else None,
        tag_ids=[int(x) for x in data.get("tag_ids", [])],
    )
    task, errors = service.create_task(request.user, dto)
    if errors:
        return _json_error(errors)
    return JsonResponse({"success": True, "task": asdict(task)})


@login_required
@require_http_methods(["GET", "PATCH", "DELETE"])
def task_detail_api(request, task_id: int):
    service = TaskService()
    if request.method == "GET":
        task, errors = service.get_task(task_id, request.user)
        if errors:
            return _json_error(errors, 404)
        return JsonResponse({"success": True, "task": asdict(task)})

    if request.method == "DELETE":
        errors = service.delete_task(task_id, request.user)
        if errors:
            return _json_error(errors, 403)
        return JsonResponse({"success": True})

    data = _parse_body(request)
    dto = UpdateTaskDTO(
        title=data.get("title"),
        description=data.get("description"),
        status=data.get("status"),
        priority=data.get("priority"),
        task_type=data.get("task_type"),
        deadline=_parse_datetime(data.get("deadline")) if "deadline" in data else None,
        assignee_id=int(data["assignee_id"]) if data.get("assignee_id") else None,
        scenario_id=int(data["scenario_id"]) if data.get("scenario_id") else None,
        tag_ids=[int(x) for x in data.get("tag_ids", [])] if "tag_ids" in data else None,
        clear_deadline=data.get("clear_deadline", False),
        clear_assignee=data.get("clear_assignee", False),
        clear_scenario=data.get("clear_scenario", False),
    )
    task, errors = service.update_task(task_id, request.user, dto)
    if errors:
        return _json_error(errors)
    return JsonResponse({"success": True, "task": asdict(task)})


@login_required
@require_http_methods(["PATCH"])
def task_status_api(request, task_id: int):
    data = _parse_body(request)
    status = data.get("status")
    if not status:
        return _json_error(["Статус обязателен"])
    service = TaskService()
    task, errors = service.update_status(task_id, request.user, status)
    if errors:
        return _json_error(errors)
    return JsonResponse({"success": True, "task": asdict(task)})


@login_required
@require_http_methods(["GET", "POST"])
def task_comments_api(request, task_id: int):
    service = CommentService()
    if request.method == "GET":
        task_service = TaskService()
        task, errors = task_service.get_task(task_id, request.user)
        if errors:
            return _json_error(errors, 404)
        return JsonResponse(
            {
                "success": True,
                "comments": [asdict(c) for c in task.comments],
            }
        )

    data = _parse_body(request)
    comment, errors = service.add_comment(task_id, request.user, data.get("body", ""))
    if errors:
        return _json_error(errors)
    return JsonResponse({"success": True, "comment": comment})


@login_required
@require_http_methods(["DELETE"])
def comment_delete_api(request, comment_id: int):
    service = CommentService()
    errors = service.delete_comment(comment_id, request.user)
    if errors:
        return _json_error(errors, 403)
    return JsonResponse({"success": True})


@login_required
@require_http_methods(["GET", "POST"])
def task_attachments_api(request, task_id: int):
    service = AttachmentService()
    if request.method == "GET":
        task_service = TaskService()
        task, errors = task_service.get_task(task_id, request.user)
        if errors:
            return _json_error(errors, 404)
        return JsonResponse({"success": True, "attachments": task.attachments})

    uploaded = request.FILES.get("file")
    attachment, errors = service.upload(task_id, request.user, uploaded)
    if errors:
        return _json_error(errors)
    return JsonResponse({"success": True, "attachment": attachment})


@login_required
@require_http_methods(["DELETE"])
def attachment_delete_api(request, attachment_id: int):
    service = AttachmentService()
    errors = service.delete(attachment_id, request.user)
    if errors:
        return _json_error(errors, 404)
    return JsonResponse({"success": True})


@login_required
@require_http_methods(["GET"])
def tags_api(request):
    service = TaskService()
    return JsonResponse({"success": True, "tags": service.get_tags()})


@login_required
@require_http_methods(["GET"])
def users_api(request):
    service = TaskService()
    return JsonResponse({"success": True, "users": service.get_users()})


@login_required
@require_http_methods(["GET"])
def scenarios_api(request):
    service = TaskService()
    return JsonResponse({"success": True, "scenarios": service.get_scenarios(request.user)})


@login_required
@require_http_methods(["POST"])
def task_watch_api(request, task_id: int):
    service = TaskService()
    is_watching, errors = service.toggle_watch(task_id, request.user)
    if errors:
        return _json_error(errors, 404)
    return JsonResponse({"success": True, "is_watching": is_watching})
