"""
Views для работы со сценариями и связанными сущностями.
Тонкие контроллеры, которые вызывают сервисы.
"""
import json
from dataclasses import asdict

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.domain.services.app_settings import AppSettingsService
from core.models import Route
from scenarios.models import Scenario
from scenarios.domain.constants import PRICE_CHANGE_MODES, PRICE_CHANGE_PARAMETERS
from scenarios.domain.services import (
    ScenarioService,
    BTDCategoryService,
    BTDCategoryValueService,
    ExchangeRateService,
    InflationService,
    TariffRuleService,
)
from scenarios.domain.dto import (
    CreateScenarioDTO,
    UpdateScenarioDTO,
    CreateTariffRuleDTO,
    UpdateTariffRuleDTO,
)
from scenarios.domain.utils.tariff_rule_display import enrich_rule_dict_for_api
from scenarios.domain.utils.tariff_conditions import apply_tariff_conditions


def _tariff_rule_api_dict(rule, *, route_set_id: int) -> dict:
    return enrich_rule_dict_for_api(asdict(rule), route_set_id=route_set_id)


@login_required
def scenario_window_view(request):
    """Возвращает HTML шаблон scenario_window.html."""
    return render(request, "scenarios/scenario_window.html")


@login_required
@require_http_methods(["GET"])
def scenario_list_api(request):
    """AJAX endpoint (JSON) для получения списка сценариев."""
    service = ScenarioService()
    scenarios = service.get_user_scenarios(request.user)
    
    return JsonResponse({
        "success": True,
        "scenarios": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "start_year": s.start_year,
                "end_year": s.end_year,
                "route_set_id": s.route_set_id,
                "route_set_name": s.route_set_name,
                "author_id": s.author_id,
                "author_name": s.author_name,
                "include_base_tariff_decisions": s.include_base_tariff_decisions,
            }
            for s in scenarios
        ]
    })


@login_required
@require_http_methods(["GET"])
def scenario_detail_api(request, scenario_id):
    """AJAX endpoint (JSON) для получения деталей сценария."""
    service = ScenarioService()
    scenario = service.get_scenario(scenario_id)
    
    if not scenario:
        return JsonResponse({"success": False, "error": "Сценарий не найден"}, status=404)
    
    return JsonResponse({
        "success": True,
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "start_year": scenario.start_year,
            "end_year": scenario.end_year,
            "route_set_id": scenario.route_set_id,
            "route_set_name": scenario.route_set_name,
            "author_id": scenario.author_id,
            "author_name": scenario.author_name,
        }
    })


@login_required
@require_http_methods(["POST"])
def scenario_create_api(request):
    """AJAX endpoint (JSON) для создания сценария."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Неверный формат JSON"}, status=400)
    
    dto = CreateScenarioDTO(
        name=data.get("name", ""),
        description=data.get("description", ""),
        start_year=data.get("start_year"),
        end_year=data.get("end_year"),
        base_scenario_id=data.get("base_scenario_id"),
    )
    
    service = ScenarioService()
    
    # Всегда создаем сценарий на базе существующего
    # base_scenario_id обязателен
    if not dto.base_scenario_id:
        return JsonResponse({"success": False, "errors": ["Не указан базовый сценарий"]}, status=400)
    
    scenario, errors = service.create_scenario_from_base(dto, request.user)
    
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    
    return JsonResponse({
        "success": True,
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "start_year": scenario.start_year,
            "end_year": scenario.end_year,
            "author_id": scenario.author_id,
            "author_name": scenario.author_name,
        }
    }, status=201)


@login_required
@require_http_methods(["POST"])
def scenario_update_api(request, scenario_id):
    """AJAX endpoint (JSON) для обновления сценария."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Неверный формат JSON"}, status=400)
    
    dto = UpdateScenarioDTO(
        name=data.get("name"),
        description=data.get("description"),
        start_year=data.get("start_year"),
        end_year=data.get("end_year"),
        route_set_id=data.get("route_set_id"),
        exchange_rate_set_id=data.get("exchange_rate_set_id"),
        price_change_settings=data.get("price_change_settings"),
        export_price_mode=data.get("export_price_mode"),
        include_base_tariff_decisions=data.get("include_base_tariff_decisions"),
    )
    
    service = ScenarioService()
    scenario, errors = service.update_scenario(scenario_id, dto, request.user)
    
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    
    return JsonResponse({
        "success": True,
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "start_year": scenario.start_year,
            "end_year": scenario.end_year,
            "route_set_id": scenario.route_set_id,
            "route_set_name": scenario.route_set_name,
            "exchange_rate_set_id": scenario.exchange_rate_set_id,
            "exchange_rate_set_name": scenario.exchange_rate_set_name,
            "inflation_set_id": scenario.inflation_set_id,
            "inflation_set_name": scenario.inflation_set_name,
            "price_change_settings": scenario.price_change_settings,
            "export_price_mode": scenario.export_price_mode,
            "include_base_tariff_decisions": scenario.include_base_tariff_decisions,
            "author_id": scenario.author_id,
            "author_name": scenario.author_name,
        }
    })


@login_required
@require_http_methods(["POST"])
def scenario_delete_api(request, scenario_id):
    """AJAX endpoint (JSON) для удаления сценария."""
    service = ScenarioService()
    _, errors = service.delete_scenario(scenario_id, request.user)
    
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    
    return JsonResponse({"success": True})


@login_required
@require_http_methods(["POST"])
def scenario_set_active_api(request, scenario_id):
    """AJAX endpoint (JSON) для установки активного сценария."""
    service = ScenarioService()
    _, errors = service.set_active_scenario(request.user, scenario_id)
    
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    
    return JsonResponse({"success": True})


@login_required
def scenario_create_modal_view(request):
    """Возвращает HTML шаблон модалки создания."""
    # Получаем список сценариев для выпадающего списка "на базе существующего"
    service = ScenarioService()
    scenarios = service.get_user_scenarios(request.user)
    
    return render(request, "scenarios/create_scenario_modal.html", {
        "scenarios": scenarios
    })


@login_required
def scenario_management_view(request):
    """Возвращает HTML шаблон страницы управления сценариями."""
    return render(request, "scenarios/scenario_management.html")


@login_required
def scenario_edit_modal_view(request, scenario_id):
    """Возвращает HTML шаблон модалки редактирования сценария."""
    service = ScenarioService()
    scenario = service.get_scenario(scenario_id)
    
    if not scenario:
        return HttpResponse("Сценарий не найден", status=404)
    
    if not AppSettingsService().can_write_scenario(
        author_id=scenario.author_id,
        user_id=request.user.id,
    ):
        return HttpResponse("Нет прав на редактирование этого сценария", status=403)

    return render(request, "scenarios/edit_scenario_modal.html", {
        "scenario": scenario
    })


@login_required
def scenario_edit_view(request, scenario_id):
    """Возвращает HTML страницу редактирования сценария с вертикальными вкладками."""
    service = ScenarioService()
    scenario = service.get_scenario(scenario_id)
    
    if not scenario:
        return HttpResponse("Сценарий не найден", status=404)
    
    if not AppSettingsService().can_write_scenario(
        author_id=scenario.author_id,
        user_id=request.user.id,
    ):
        return HttpResponse("Нет прав на редактирование этого сценария", status=403)

    breadcrumbs = [
        {"title": "Главная", "url": reverse("home")},
        {"title": "Сценарии", "url": reverse("scenarios:management")},
        {"title": "Управление сценариями", "url": reverse("scenarios:management")},
        {"title": f"Редактирование: {scenario.name}", "url": None},
    ]

    price_change_rows = [
        {
            "key": key,
            "label": label,
            "mode": scenario.price_change_settings.get(key, "fixed"),
        }
        for key, label in PRICE_CHANGE_PARAMETERS
    ]
    export_price_modes = list(Scenario.ExportPriceMode.choices)

    return render(
        request,
        "scenarios/edit_scenario.html",
        {
            "scenario": scenario,
            "breadcrumbs": breadcrumbs,
            "price_change_rows": price_change_rows,
            "price_change_modes": PRICE_CHANGE_MODES,
            "export_price_modes": export_price_modes,
        },
    )


# === Tariff rules API ===


@login_required
@require_http_methods(["GET"])
def tariff_rule_list_api(request, scenario_id):
    service = TariffRuleService()
    rules, errors = service.list_rules(scenario_id, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    try:
        scenario = Scenario.objects.only("route_set_id").get(pk=scenario_id)
        route_set_id = scenario.route_set_id
    except Scenario.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Сценарий не найден"]}, status=404)
    return JsonResponse(
        {
            "success": True,
            "rules": [
                _tariff_rule_api_dict(rule, route_set_id=route_set_id)
                for rule in rules
            ],
        }
    )


@login_required
@require_http_methods(["POST"])
def tariff_rule_create_api(request, scenario_id):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Неверный формат JSON"}, status=400)

    dto = CreateTariffRuleDTO(
        scenario_id=scenario_id,
        name=data.get("name", ""),
        base_percent=data.get("base_percent"),
        position=data.get("position"),
        conditions=data.get("conditions"),
        year_values=data.get("year_values"),
    )

    service = TariffRuleService()
    rule, errors = service.create_rule(dto, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    return JsonResponse({"success": True, "rule": asdict(rule)}, status=201)


@login_required
@require_http_methods(["GET"])
def tariff_rule_detail_api(request, rule_id):
    service = TariffRuleService()
    rule, errors = service.get_rule(rule_id, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    try:
        scenario = Scenario.objects.only("route_set_id").get(pk=rule.scenario_id)
    except Scenario.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Сценарий не найден"]}, status=404)
    return JsonResponse(
        {
            "success": True,
            "rule": _tariff_rule_api_dict(rule, route_set_id=scenario.route_set_id),
        },
    )


@login_required
@require_http_methods(["POST"])
def tariff_rule_update_api(request, rule_id):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Неверный формат JSON"}, status=400)

    dto = UpdateTariffRuleDTO(
        name=data.get("name"),
        base_percent=data.get("base_percent"),
        position=data.get("position"),
        conditions=data.get("conditions"),
        year_values=data.get("year_values"),
    )
    service = TariffRuleService()
    rule, errors = service.update_rule(rule_id, dto, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    return JsonResponse({"success": True, "rule": asdict(rule)})


@login_required
@require_http_methods(["POST"])
def tariff_rule_delete_api(request, rule_id):
    service = TariffRuleService()
    ok, errors = service.delete_rule(rule_id, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    return JsonResponse({"success": True, "deleted": ok})


@login_required
@require_http_methods(["GET"])
def tariff_rule_options_api(request, scenario_id):
    parameter = (request.GET.get("parameter") or "").strip()
    if not parameter:
        return JsonResponse({"success": False, "errors": ["Не указан parameter"]}, status=400)

    try:
        scenario = Scenario.objects.select_related("route_set", "author").get(id=scenario_id)
    except Scenario.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Сценарий не найден"]}, status=404)

    if not AppSettingsService().can_write_scenario(
        author_id=scenario.author_id,
        user_id=request.user.id,
    ):
        return JsonResponse({"success": False, "errors": ["Нет прав на изменение этого сценария"]}, status=403)

    qs = Route.objects.filter(route_set_id=scenario.route_set_id)

    items: list[dict] = []

    if parameter == "cargo_group":
        rows = (
            qs.exclude(cargo__cargo_group__isnull=True)
            .values("cargo__cargo_group__code", "cargo__cargo_group__name")
            .distinct()
            .order_by("cargo__cargo_group__name")
        )
        items = [{"value": r["cargo__cargo_group__code"], "text": r["cargo__cargo_group__name"]} for r in rows]
    elif parameter == "cargo_code":
        rows = qs.values("cargo__code", "cargo__name").distinct().order_by("cargo__code")
        items = [{"value": r["cargo__code"], "text": f'{r["cargo__code"]} — {r["cargo__name"]}'} for r in rows]
    elif parameter == "origin_railroad":
        rows = (
            qs.values("origin_station__railroad__code", "origin_station__railroad__name")
            .distinct()
            .order_by("origin_station__railroad__code")
        )
        items = [{"value": r["origin_station__railroad__code"], "text": f'{r["origin_station__railroad__code"]} — {r["origin_station__railroad__name"]}'} for r in rows]
    elif parameter == "destination_railroad":
        rows = (
            qs.values("destination_station__railroad__code", "destination_station__railroad__name")
            .distinct()
            .order_by("destination_station__railroad__code")
        )
        items = [{"value": r["destination_station__railroad__code"], "text": f'{r["destination_station__railroad__code"]} — {r["destination_station__railroad__name"]}'} for r in rows]
    elif parameter == "wagon_kind":
        rows = qs.values("wagon_kind__id", "wagon_kind__name").distinct().order_by("wagon_kind__name")
        items = [{"value": r["wagon_kind__id"], "text": r["wagon_kind__name"]} for r in rows]
    elif parameter == "shipment_type":
        rows = qs.values("shipment_type__id", "shipment_type__name").distinct().order_by("shipment_type__name")
        items = [{"value": r["shipment_type__id"], "text": r["shipment_type__name"]} for r in rows]
    elif parameter == "message_type":
        rows = (
            qs.exclude(message_type__isnull=True)
            .values("message_type__id", "message_type__name")
            .distinct()
            .order_by("message_type__name")
        )
        items = [{"value": r["message_type__id"], "text": r["message_type__name"]} for r in rows]
    elif parameter == "shipper":
        rows = (
            qs.exclude(shipper__isnull=True)
            .values("shipper_id", "shipper__name", "shipper__holding")
            .distinct()
            .order_by("shipper__name")
        )
        items = [
            {
                "value": r["shipper_id"],
                "text": (
                    f'{r["shipper__name"]} ({r["shipper__holding"]})'
                    if r["shipper__holding"]
                    else r["shipper__name"]
                ),
            }
            for r in rows
        ]
    elif parameter == "shipper_holding":
        rows = (
            qs.exclude(shipper__isnull=True)
            .exclude(shipper__holding="")
            .values_list("shipper__holding", flat=True)
            .distinct()
            .order_by("shipper__holding")
        )
        items = [{"value": v, "text": v} for v in rows]
    elif parameter == "distance_belt":
        rows = (
            qs.exclude(distance_belt="")
            .values_list("distance_belt", flat=True)
            .distinct()
            .order_by("distance_belt")
        )
        items = [{"value": v, "text": v} for v in rows]
    elif parameter == "special_container_type":
        rows = (
            qs.exclude(special_container_type="")
            .values_list("special_container_type", flat=True)
            .distinct()
            .order_by("special_container_type")
        )
        items = [{"value": v, "text": v} for v in rows]
    else:
        return JsonResponse({"success": False, "errors": ["Неизвестный parameter"]}, status=400)

    return JsonResponse({"success": True, "items": items})


@login_required
@require_http_methods(["POST"])
def tariff_rule_stats_api(request, scenario_id):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Неверный формат JSON"}, status=400)

    try:
        scenario = Scenario.objects.select_related("route_set", "author").get(id=scenario_id)
    except Scenario.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Сценарий не найден"]}, status=404)

    if not AppSettingsService().can_write_scenario(
        author_id=scenario.author_id,
        user_id=request.user.id,
    ):
        return JsonResponse({"success": False, "errors": ["Нет прав на изменение этого сценария"]}, status=403)

    conditions = data.get("conditions") or []
    qs = Route.objects.filter(route_set_id=scenario.route_set_id)
    total = qs.count()
    matched = apply_tariff_conditions(qs, conditions).count()
    percent = 0.0 if total <= 0 else round((matched * 100.0) / total, 2)

    return JsonResponse(
        {
            "success": True,
            "total_routes": total,
            "matched_routes": matched,
            "matched_percent": percent,
        }
    )


@login_required
@require_http_methods(["GET"])
def btd_category_list_api(request, scenario_id):
    """AJAX endpoint (JSON) для получения списка категорий BTD конкретного сценария."""
    service = BTDCategoryService()
    categories, errors = service.list_categories(scenario_id, request.user)

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "categories": [
                {
                    "id": c.id,
                    "name": c.name,
                    "position": c.position,
                    "scenario_id": c.scenario_id,
                }
                for c in categories
            ],
        }
    )


@login_required
@require_http_methods(["POST"])
def btd_category_create_api(request, scenario_id):
    """AJAX endpoint (JSON) для создания категории BTD."""
    from scenarios.domain.dto import CreateBTDCategoryDTO

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Неверный формат JSON"}, status=400
        )

    dto = CreateBTDCategoryDTO(
        name=data.get("name", ""),
        scenario_id=scenario_id,
        position=data.get("position"),
    )

    service = BTDCategoryService()
    category, errors = service.create_category(dto, request.user)

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "category": {
                "id": category.id,
                "name": category.name,
                "position": category.position,
                "scenario_id": category.scenario_id,
            },
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def btd_category_update_api(request, category_id):
    """AJAX endpoint (JSON) для обновления категории BTD."""
    from scenarios.domain.dto import UpdateBTDCategoryDTO

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Неверный формат JSON"}, status=400
        )

    dto = UpdateBTDCategoryDTO(
        name=data.get("name"),
        position=data.get("position"),
    )

    service = BTDCategoryService()
    category, errors = service.update_category(category_id, dto, request.user)

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "category": {
                "id": category.id,
                "name": category.name,
                "position": category.position,
                "scenario_id": category.scenario_id,
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def btd_category_delete_api(request, category_id):
    """AJAX endpoint (JSON) для удаления категории BTD с пересчетом позиций."""
    service = BTDCategoryService()
    _, errors = service.delete_category(category_id, request.user)

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse({"success": True})


@login_required
@require_http_methods(["POST"])
def btd_category_move_api(request, category_id):
    """AJAX endpoint (JSON) для смены позиции категории (поднять выше / опустить ниже)."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Неверный формат JSON"}, status=400
        )

    direction = data.get("direction")
    if direction not in ("up", "down"):
        return JsonResponse(
            {"success": False, "errors": ["Неверный direction: ожидается up или down"]},
            status=400,
        )

    service = BTDCategoryService()
    categories, errors = service.move_category(category_id, direction, request.user)

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "categories": [
                {"id": c.id, "name": c.name, "position": c.position, "scenario_id": c.scenario_id}
                for c in categories
            ],
        }
    )


@login_required
@require_http_methods(["GET"])
def btd_values_matrix_api(request, scenario_id):
    """AJAX endpoint (JSON) для получения матрицы значений BTD по годам сценария."""
    service = BTDCategoryValueService()
    payload, errors = service.get_matrix(scenario_id, request.user)

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "years": payload["years"],
            "categories": payload["categories"],
            "total_coefficient": payload.get("total_coefficient", {}),
        }
    )


@login_required
@require_http_methods(["POST"])
def btd_value_update_api(request):
    """AJAX endpoint (JSON) для обновления одного значения BTD (ячейка матрицы)."""
    from scenarios.domain.dto import UpdateBTDCategoryValueDTO

    # Поддерживаем JSON и form-data (x-editable по умолчанию шлет form-data)
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "errors": ["Неверный формат JSON"]},
                status=400,
            )
    else:
        data = request.POST

    try:
        scenario_id = int(data.get("scenario_id"))
        category_id = int(data.get("category_id"))
        year = int(data.get("year"))
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "success": False,
                "errors": ["Некорректные идентификаторы сценария, категории или года"],
            },
            status=400,
        )

    value = data.get("value")

    dto = UpdateBTDCategoryValueDTO(
        scenario_id=scenario_id,
        category_id=category_id,
        year=year,
        value=str(value) if value is not None else "",
    )

    service = BTDCategoryValueService()
    value_dto, errors = service.update_value(dto, request.user)

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "value": value_dto.value,
        }
    )


# ===========================
# Exchange rates (USD/RUB)
# ===========================


@login_required
@require_http_methods(["GET"])
def exchange_rate_set_list_api(request):
    service = ExchangeRateService()
    sets = service.list_sets(request.user)
    return JsonResponse(
        {
            "success": True,
            "items": [
                {
                    "id": s.id,
                    "name": s.name,
                    "author_id": s.author_id,
                    "author_name": s.author_name,
                }
                for s in sets
            ],
        }
    )


@login_required
@require_http_methods(["POST"])
def exchange_rate_set_create_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    name = data.get("name") or ""
    service = ExchangeRateService()
    created, errors = service.create_set(str(name), request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": created.id,
                "name": created.name,
                "author_id": created.author_id,
                "author_name": created.author_name,
            },
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def exchange_rate_set_delete_api(request, rate_set_id: int):
    service = ExchangeRateService()
    ok, errors = service.delete_set(rate_set_id, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    return JsonResponse({"success": True, "deleted": ok})


@login_required
@require_http_methods(["POST"])
def exchange_rate_set_attach_api(request, scenario_id: int):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    try:
        rate_set_id = int(data.get("rate_set_id"))
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "errors": ["Некорректный rate_set_id"]},
            status=400,
        )

    service = ExchangeRateService()
    scenario_dto, errors = service.attach_set_to_scenario(
        scenario_id, rate_set_id, request.user
    )
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "scenario": {
                "id": scenario_dto.id,
                "exchange_rate_set_id": scenario_dto.exchange_rate_set_id,
                "exchange_rate_set_name": scenario_dto.exchange_rate_set_name,
            },
        }
    )


@login_required
@require_http_methods(["GET"])
def exchange_rates_matrix_api(request, scenario_id: int):
    service = ExchangeRateService()
    payload, errors = service.get_matrix(scenario_id, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "years": payload["years"],
            "rate_set": payload["rate_set"].__dict__ if payload.get("rate_set") else None,
            "values": payload.get("values", {}),
        }
    )


@login_required
@require_http_methods(["POST"])
def exchange_rate_value_update_api(request):
    from scenarios.domain.dto import UpdateExchangeRateValueDTO

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    try:
        scenario_id = int(data.get("scenario_id"))
        rate_set_id = int(data.get("rate_set_id"))
        year = int(data.get("year"))
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "success": False,
                "errors": ["Некорректные идентификаторы сценария/набора/года"],
            },
            status=400,
        )

    usd_rub = data.get("usd_rub")

    dto = UpdateExchangeRateValueDTO(
        scenario_id=scenario_id,
        rate_set_id=rate_set_id,
        year=year,
        usd_rub=str(usd_rub) if usd_rub is not None else "",
    )

    service = ExchangeRateService()
    value_dto, errors = service.update_value(dto, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "usd_rub": value_dto.usd_rub,
        }
    )


@login_required
@require_http_methods(["GET"])
def inflation_set_list_api(request):
    service = InflationService()
    sets = service.list_sets(request.user)
    return JsonResponse(
        {
            "success": True,
            "items": [
                {
                    "id": s.id,
                    "name": s.name,
                    "author_id": s.author_id,
                    "author_name": s.author_name,
                }
                for s in sets
            ],
        }
    )


@login_required
@require_http_methods(["POST"])
def inflation_set_create_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    name = data.get("name") or ""
    service = InflationService()
    created, errors = service.create_set(str(name), request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": created.id,
                "name": created.name,
                "author_id": created.author_id,
                "author_name": created.author_name,
            },
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def inflation_set_delete_api(request, inflation_set_id: int):
    service = InflationService()
    ok, errors = service.delete_set(inflation_set_id, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)
    return JsonResponse({"success": True, "deleted": ok})


@login_required
@require_http_methods(["POST"])
def inflation_set_attach_api(request, scenario_id: int):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    try:
        inflation_set_id = int(data.get("inflation_set_id"))
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "errors": ["Некорректный inflation_set_id"]},
            status=400,
        )

    service = InflationService()
    scenario_dto, errors = service.attach_set_to_scenario(
        scenario_id, inflation_set_id, request.user
    )
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "scenario": {
                "id": scenario_dto.id,
                "inflation_set_id": scenario_dto.inflation_set_id,
                "inflation_set_name": scenario_dto.inflation_set_name,
            },
        }
    )


@login_required
@require_http_methods(["GET"])
def inflation_matrix_api(request, scenario_id: int):
    service = InflationService()
    payload, errors = service.get_matrix(scenario_id, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    inflation_set = payload.get("inflation_set")
    return JsonResponse(
        {
            "success": True,
            "years": payload["years"],
            "inflation_set": inflation_set.__dict__ if inflation_set else None,
            "values": payload.get("values", {}),
        }
    )


@login_required
@require_http_methods(["POST"])
def inflation_value_update_api(request):
    from scenarios.domain.dto import UpdateInflationValueDTO

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    try:
        scenario_id = int(data.get("scenario_id"))
        inflation_set_id = int(data.get("inflation_set_id"))
        year = int(data.get("year"))
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "success": False,
                "errors": ["Некорректные идентификаторы сценария/набора/года"],
            },
            status=400,
        )

    rate_percent = data.get("rate_percent")

    dto = UpdateInflationValueDTO(
        scenario_id=scenario_id,
        inflation_set_id=inflation_set_id,
        year=year,
        rate_percent=str(rate_percent) if rate_percent is not None else "",
    )

    service = InflationService()
    value_dto, errors = service.update_value(dto, request.user)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "rate_percent": value_dto.rate_percent,
        }
    )
