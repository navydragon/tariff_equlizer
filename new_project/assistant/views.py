import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from assistant.domain.dto.chat import PRESET_LABELS, ChatRequestDTO
from assistant.domain.services.chat import AssistantChatService


def _json_error(errors: list[str], status: int = 400) -> JsonResponse:
    return JsonResponse({"success": False, "errors": errors}, status=status)


def _parse_body(request) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()


@login_required
@require_http_methods(["GET"])
def presets_api(request):
    return JsonResponse(
        {
            "success": True,
            "presets": [
                {"id": key, "label": label}
                for key, label in PRESET_LABELS.items()
            ],
        },
    )


@login_required
@require_http_methods(["POST"])
def chat_api(request):
    data = _parse_body(request)
    if not data:
        return _json_error(["Неверный формат JSON"])

    dto = ChatRequestDTO.from_payload(data)
    response, errors = AssistantChatService().chat(user=request.user, request_dto=dto)
    if errors:
        status = 404 if any("не найден" in e.lower() for e in errors) else 400
        return _json_error(errors, status=status)

    assert response is not None
    return JsonResponse({"success": True, **response.to_api_dict()})
