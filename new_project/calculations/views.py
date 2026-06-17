import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from calculations.domain.dto import (
    ScenarioAbsoluteRequestDTO,
    ScenarioEffectsAggregateRequestDTO,
    ScenarioEffectsComputeRequestDTO,
    ScenarioEffectsCubeRequestDTO,
    ScenarioEffectsRequestDTO,
    TariffLoadRequestDTO,
    TariffLoadResponseDTO,
)
from calculations.domain.dto.scenario_effects_cube import (
    ScenarioEffectsCubeResponseDTO,
)
from calculations.domain.dto.scenario_absolute import ScenarioAbsoluteResponseDTO
from calculations.domain.services import (
    ScenarioAbsoluteService,
    ScenarioEffectsCubeService,
    ScenarioEffectsPandasService,
    ScenarioEffectsService,
    TariffLoadService,
)
from core.domain.services.app_settings import AppSettingsService
from core.export import ExcelExportService, ExportColumn, ExportTable, excel_response
from core.models import Route
from scenarios.models import Scenario


def _parse_json_body(request):
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )


def _get_user_scenario(request, scenario_id: int):
    try:
        scenario = Scenario.objects.get(pk=scenario_id)
    except Scenario.DoesNotExist:
        return None, JsonResponse(
            {"success": False, "errors": ["Сценарий не найден"]},
            status=404,
        )
    if not AppSettingsService().can_read_scenario(
        author_id=scenario.author_id,
        user_id=request.user.id,
    ):
        return None, JsonResponse(
            {"success": False, "errors": ["Сценарий не найден"]},
            status=404,
        )
    return scenario, None


@login_required
@require_http_methods(["POST"])
def tariff_load_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto = TariffLoadRequestDTO(
        scenario_id=data.get("scenario_id"),
        route_ids=data.get("route_ids") or [],
    )
    errors = dto.validate()
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    scenario, error_response = _get_user_scenario(request, dto.scenario_id)
    if error_response:
        return error_response

    routes = list(
        Route.objects.filter(
            pk__in=dto.route_ids,
            route_set_id=scenario.route_set_id,
        )
    )
    if len(routes) != len(set(dto.route_ids)):
        return JsonResponse(
            {"success": False, "errors": ["Один или несколько маршрутов не найдены"]},
            status=404,
        )

    route_by_id = {route.id: route for route in routes}
    ordered_routes = [route_by_id[route_id] for route_id in dto.route_ids]

    service = TariffLoadService()
    results = service.calculate_routes(scenario=scenario, routes=ordered_routes)
    response_dto = TariffLoadResponseDTO(
        scenario_id=scenario.id,
        routes=results,
    )

    return JsonResponse({"success": True, **response_dto.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def scenario_effects_compute_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto = ScenarioEffectsComputeRequestDTO(
        scenario_id=data.get("scenario_id"),
    )
    errors = dto.validate()
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    scenario, error_response = _get_user_scenario(request, dto.scenario_id)
    if error_response:
        return error_response

    service = ScenarioEffectsService()
    response_dto, calc_errors = service.compute(
        scenario=scenario,
        user_id=request.user.id,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    return JsonResponse({"success": True, **response_dto.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def scenario_effects_compute_pandas_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto = ScenarioEffectsComputeRequestDTO(
        scenario_id=data.get("scenario_id"),
        include_rule_breakdown=bool(data.get("include_rule_breakdown", False)),
    )
    errors = dto.validate()
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    scenario, error_response = _get_user_scenario(request, dto.scenario_id)
    if error_response:
        return error_response

    scenario = Scenario.objects.select_related("route_set").get(pk=scenario.pk)

    service = ScenarioEffectsPandasService()
    response_dto, calc_errors, meta = service.compute_pandas(
        scenario=scenario,
        user_id=request.user.id,
        include_rule_breakdown=dto.include_rule_breakdown,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            **response_dto.to_api_dict(),
            "engine": meta.get("engine"),
            "elapsed_ms": meta.get("elapsed_ms"),
            "cache_hit": meta.get("cache_hit", False),
            "route_mart_cache_hit": meta.get("route_mart_cache_hit", False),
            "scenario_compute_cache_hit": meta.get("scenario_compute_cache_hit", False),
            "compact_ready": meta.get("compact_ready", True),
            "data_version": meta.get("data_version"),
            "timings": meta.get("timings"),
        },
    )


@login_required
@require_http_methods(["POST"])
def scenario_effects_aggregate_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto = ScenarioEffectsAggregateRequestDTO(
        cache_key=data.get("cache_key") or "",
        year=data.get("year"),
        group_by=data.get("group_by") or "cargo_group",
        group_by_inner=data.get("group_by_inner") or "none",
        cargo_groups=data.get("cargo_groups") or [],
        holdings=data.get("holdings") or [],
    )
    errors = dto.validate()
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    scenario_id = data.get("scenario_id")
    if not isinstance(scenario_id, int) or scenario_id <= 0:
        return JsonResponse(
            {"success": False, "errors": ["Некорректный scenario_id"]},
            status=400,
        )

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    service = ScenarioEffectsService()
    response_dto, calc_errors = service.aggregate(
        scenario=scenario,
        user_id=request.user.id,
        request=dto,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    return JsonResponse({"success": True, **response_dto.to_api_dict()})


@login_required
@require_http_methods(["GET"])
def scenario_effects_revision_api(request):
    scenario_id_raw = request.GET.get("scenario_id")
    try:
        scenario_id = int(scenario_id_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "errors": ["Некорректный scenario_id"]},
            status=400,
        )

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    from calculations.domain.services.scenario_effects_cache import (
        get_scenario_effects_revision,
    )

    data_version = get_scenario_effects_revision(scenario_id=scenario.id)
    return JsonResponse({"success": True, "data_version": data_version})


@login_required
@require_http_methods(["GET"])
def scenario_warm_status_api(request):
    scenario_id_raw = request.GET.get("scenario_id")
    try:
        scenario_id = int(scenario_id_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "errors": ["Некорректный scenario_id"]},
            status=400,
        )

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    from calculations.domain.services.scenario_warm_status import get_warm_status

    status = get_warm_status(scenario_id=scenario.id)
    if status is None:
        return JsonResponse(
            {
                "success": True,
                "phase": None,
                "kpi_ready": False,
                "compact_ready": False,
            }
        )
    return JsonResponse({"success": True, **status})


@login_required
@require_http_methods(["POST"])
def scenario_effects_compact_status_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    cache_key = data.get("cache_key") or ""
    if not cache_key:
        return JsonResponse(
            {"success": False, "errors": ["Не указан cache_key"]},
            status=400,
        )

    from calculations.domain.services.scenario_effects_cache import (
        get_compact_status,
        get_payload,
        validate_cache_access,
    )

    payload = get_payload(cache_key)
    if payload is None:
        return JsonResponse(
            {"success": False, "errors": ["Кэш расчёта недоступен"]},
            status=404,
        )

    access_errors = validate_cache_access(
        payload=payload,
        user_id=request.user.id,
        scenario_id=payload.scenario_id,
    )
    if access_errors:
        return JsonResponse({"success": False, "errors": access_errors}, status=403)

    status = get_compact_status(cache_key=cache_key)
    return JsonResponse({"success": True, **status})


@login_required
@require_http_methods(["POST"])
def scenario_effects_api(request):
    """Полный расчёт (compute + aggregate) для обратной совместимости."""
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto = ScenarioEffectsRequestDTO(
        scenario_id=data.get("scenario_id"),
        year=data.get("year"),
        group_by=data.get("group_by") or "cargo_group",
        group_by_inner=data.get("group_by_inner") or "none",
        cargo_groups=data.get("cargo_groups") or [],
        holdings=data.get("holdings") or [],
    )
    errors = dto.validate()
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    scenario, error_response = _get_user_scenario(request, dto.scenario_id)
    if error_response:
        return error_response

    service = ScenarioEffectsService()
    response_dto, calc_errors = service.calculate(
        scenario=scenario,
        request=dto,
        user_id=request.user.id,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    return JsonResponse({"success": True, **response_dto.to_api_dict()})


def _parse_absolute_request(data: dict) -> tuple[ScenarioAbsoluteRequestDTO | None, int | None, JsonResponse | None]:
    scenario_id = data.get("scenario_id")
    if not isinstance(scenario_id, int) or scenario_id <= 0:
        return (
            None,
            None,
            JsonResponse(
                {"success": False, "errors": ["Некорректный scenario_id"]},
                status=400,
            ),
        )

    dto = ScenarioAbsoluteRequestDTO(
        cache_key=data.get("cache_key") or "",
        group_by=data.get("group_by") or "cargo_group",
        group_by_inner=data.get("group_by_inner") or "none",
    )
    errors = dto.validate()
    if errors:
        return None, None, JsonResponse({"success": False, "errors": errors}, status=400)

    return dto, scenario_id, None


def _absolute_table_to_export(
    response: ScenarioAbsoluteResponseDTO,
) -> ExportTable:
    columns = [ExportColumn(key="label", header="")]
    for year in response.years:
        columns.append(ExportColumn(key=str(year), header=str(year)))
    columns.append(
        ExportColumn(key="total", header=response.total_column_label),
    )

    rows = []
    for row in response.rows:
        export_row = {"label": row.label, "total": row.total}
        export_row.update(row.years)
        rows.append(export_row)

    return ExportTable(sheet_title="Данные", columns=columns, rows=rows)


@login_required
@require_http_methods(["POST"])
def scenario_absolute_revenues_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto, scenario_id, error_response = _parse_absolute_request(data)
    if error_response:
        return error_response

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    service = ScenarioAbsoluteService()
    response_dto, calc_errors = service.aggregate_revenues(
        scenario=scenario,
        user_id=request.user.id,
        request=dto,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    return JsonResponse({"success": True, **response_dto.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def scenario_absolute_volumes_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto, scenario_id, error_response = _parse_absolute_request(data)
    if error_response:
        return error_response

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    service = ScenarioAbsoluteService()
    response_dto, calc_errors = service.aggregate_volumes(
        scenario=scenario,
        user_id=request.user.id,
        request=dto,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    return JsonResponse({"success": True, **response_dto.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def scenario_absolute_revenues_export_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto, scenario_id, error_response = _parse_absolute_request(data)
    if error_response:
        return error_response

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    service = ScenarioAbsoluteService()
    response_dto, calc_errors = service.aggregate_revenues(
        scenario=scenario,
        user_id=request.user.id,
        request=dto,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    export_table = _absolute_table_to_export(response_dto)
    content = ExcelExportService().build_workbook_bytes(export_table)
    return excel_response(filename="dohody_vsego.xlsx", content=content)


@login_required
@require_http_methods(["POST"])
def scenario_absolute_volumes_export_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto, scenario_id, error_response = _parse_absolute_request(data)
    if error_response:
        return error_response

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    service = ScenarioAbsoluteService()
    response_dto, calc_errors = service.aggregate_volumes(
        scenario=scenario,
        user_id=request.user.id,
        request=dto,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    export_table = _absolute_table_to_export(response_dto)
    content = ExcelExportService().build_workbook_bytes(export_table)
    return excel_response(filename="obem_perevozok.xlsx", content=content)


def _parse_cube_request(data: dict) -> tuple[ScenarioEffectsCubeRequestDTO | None, int | None, JsonResponse | None]:
    scenario_id = data.get("scenario_id")
    if not isinstance(scenario_id, int) or scenario_id <= 0:
        return (
            None,
            None,
            JsonResponse(
                {"success": False, "errors": ["Некорректный scenario_id"]},
                status=400,
            ),
        )

    dto = ScenarioEffectsCubeRequestDTO(
        cache_key=data.get("cache_key") or "",
        group_by=data.get("group_by") or "cargo_group",
        group_by_inner=data.get("group_by_inner") or "none",
        cargo_groups=data.get("cargo_groups") or [],
        holdings=data.get("holdings") or [],
    )
    errors = dto.validate()
    if errors:
        return None, None, JsonResponse({"success": False, "errors": errors}, status=400)

    return dto, scenario_id, None


def _cube_table_to_export(
    response: ScenarioEffectsCubeResponseDTO,
) -> ExportTable:
    columns = [
        ExportColumn(key="group_label", header=response.group_by_label),
    ]
    if response.group_by_inner_label:
        columns.append(
            ExportColumn(
                key="group_inner_label",
                header=response.group_by_inner_label,
            ),
        )
    columns.append(ExportColumn(key="effect_label", header="Тарифное решение"))
    for year in response.years:
        columns.append(ExportColumn(key=str(year), header=str(year)))
    columns.append(
        ExportColumn(key="total", header=response.total_column_label),
    )

    rows = []
    for row in response.rows:
        export_row = {
            "group_label": row.group_label,
            "group_inner_label": row.group_inner_label or "",
            "effect_label": row.effect_label,
            "total": row.total,
        }
        export_row.update({str(year): value for year, value in row.years.items()})
        rows.append(export_row)

    return ExportTable(sheet_title="Куб эффектов", columns=columns, rows=rows)


@login_required
@require_http_methods(["POST"])
def scenario_effects_cube_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto, scenario_id, error_response = _parse_cube_request(data)
    if error_response:
        return error_response

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    service = ScenarioEffectsCubeService()
    response_dto, calc_errors = service.aggregate(
        scenario=scenario,
        user_id=request.user.id,
        request=dto,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    return JsonResponse({"success": True, **response_dto.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def scenario_effects_cube_export_api(request):
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    dto, scenario_id, error_response = _parse_cube_request(data)
    if error_response:
        return error_response

    scenario, error_response = _get_user_scenario(request, scenario_id)
    if error_response:
        return error_response

    service = ScenarioEffectsCubeService()
    response_dto, calc_errors = service.aggregate(
        scenario=scenario,
        user_id=request.user.id,
        request=dto,
    )
    if calc_errors:
        return JsonResponse({"success": False, "errors": calc_errors}, status=400)

    export_table = _cube_table_to_export(response_dto)
    content = ExcelExportService().build_workbook_bytes(export_table)
    return excel_response(filename="kub_effektov.xlsx", content=content)
