import json
from pathlib import Path

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator, EmptyPage
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.domain.cargo.dto import CreateCargoDTO, UpdateCargoDTO
from core.domain.cargo.services import CargoService
from core.domain.route_analysis.dto import RouteAnalysisRequestDTO
from core.domain.route_analysis.services import RouteAnalysisService
from core.domain.services.app_settings import AppSettingsService
from core.domain.railroad.dto import CreateRailRoadDTO, UpdateRailRoadDTO
from core.domain.railroad.services import RailRoadService
from core.domain.route.dto import (
    CreateRouteSetDTO,
    RouteListFiltersDTO,
    UpdateRouteSetDTO,
)
from core.domain.route.services import RouteService, RouteSetService
from core.models import (
    Region,
    Station,
    RailRoad,
    WagonKind,
    ShipmentType,
    MessageType,
    Shipper,
    Route,
    Cargo,
)
from scenarios.models import Scenario


def index(request):
    """
    Главная страница: редирект на login/home в зависимости от авторизации.
    """
    if request.user.is_authenticated:
        return redirect("home")
    return redirect("login")


def hello_partial(request):
    """
    Пример простого htmx-эндпоинта, который возвращает фрагмент HTML.
    """
    return HttpResponse("Привет от htmx и Django!")


class CustomLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True


@login_required
def home(request):
    menu_path = Path(__file__).resolve().parent / "menu_items.json"
    with menu_path.open("r", encoding="utf-8") as f:
        items = json.load(f)

    items = sorted(items, key=lambda x: x.get("position", 0))
    return render(request, "core/home.html", {"menu_items": items})


@login_required
def references_view(request):
    """
    Страница «Справочники» с ссылками на подсправочники.
    """
    return render(request, "core/references.html")


def logout_view(request):
    """
    Кастомный logout view, который работает с GET-запросами.
    """
    logout(request)
    return redirect("index")


@login_required
def dashboard_1(request):
    """
    Заглушка для первого дашборда/сценария.
    """
    return render(request, "core/dashboard_1.html")


@login_required
def decision_effects(request):
    """
    Эффект от решений: эластичность спроса и оценка тарифных решений по сценарию.
    """
    return render(request, "core/decision_effects.html")


@login_required
def effects_cube(request):
    """
    Куб эффектов: влияние базовой индексации и отдельных решений по провозной плате.
    """
    return render(request, "core/effects_cube.html")


@login_required
def route_analysis(request):
    """
    Страница «Экономика грузов».
    """
    return render(request, "core/route_analysis.html")


# === Cargo: HTML-страницы ===


@login_required
def cargo_list_view(request):
    """
    Страница со списком грузов (таблица + фильтры).
    """
    from core.models import CargoGroup

    cargo_groups = CargoGroup.objects.all().order_by("position", "code")
    return render(
        request,
        "core/cargo_list.html",
        {
            "cargo_groups": cargo_groups,
        },
    )


# === Cargo: API (JSON) ===


@login_required
@require_http_methods(["GET"])
def cargo_list_api(request):
    """
    Список грузов с пагинацией и фильтрами.
    """
    service = CargoService()

    # Параметры пагинации
    try:
        page = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(request.GET.get("page_size", "20"))
    except (TypeError, ValueError):
        page_size = 20

    search = request.GET.get("search") or None
    code = request.GET.get("code") or None
    name = request.GET.get("name") or None

    cargo_group_code = None
    raw_group = request.GET.get("cargo_group_code")
    if raw_group not in (None, "", "null"):
        try:
            cargo_group_code = int(raw_group)
        except (TypeError, ValueError):
            return JsonResponse(
                {"success": False, "errors": ["Некорректный код группы груза"]},
                status=400,
            )

    result, errors = service.list_cargos(
        page=page,
        page_size=page_size,
        search=search,
        code=code,
        name=name,
        cargo_group_code=cargo_group_code,
    )

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "items": [
                {
                    "code": item.code,
                    "name": item.name,
                    "cargo_group_code": item.cargo_group_code,
                    "cargo_group_name": item.cargo_group_name,
                }
                for item in result.items
            ],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "total_pages": result.total_pages,
        }
    )


@login_required
@require_http_methods(["GET"])
def cargo_detail_api(request, code: int):
    """
    Детали одного груза.
    """
    service = CargoService()
    cargo, errors = service.get_cargo(code)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=404)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "code": cargo.code,
                "name": cargo.name,
                "cargo_group_code": cargo.cargo_group_code,
                "cargo_group_name": cargo.cargo_group_name,
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def cargo_create_api(request):
    """
    Создание нового груза.
    Ожидает JSON: {code, name, cargo_group_code?}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    try:
        code = int(data.get("code"))
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "errors": ["Код груза должен быть целым числом"]},
            status=400,
        )

    name = data.get("name", "")
    raw_group = data.get("cargo_group_code")
    cargo_group_code = None
    if raw_group not in (None, "", "null"):
        try:
            cargo_group_code = int(raw_group)
        except (TypeError, ValueError):
            return JsonResponse(
                {"success": False, "errors": ["Код группы груза должен быть целым числом"]},
                status=400,
            )

    dto = CreateCargoDTO(
        code=code,
        name=name,
        cargo_group_code=cargo_group_code,
    )

    service = CargoService()
    cargo, errors = service.create_cargo(dto)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "code": cargo.code,
                "name": cargo.name,
                "cargo_group_code": cargo.cargo_group_code,
                "cargo_group_name": cargo.cargo_group_name,
            },
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def cargo_update_api(request, code: int):
    """
    Обновление существующего груза.
    Ожидает JSON: {name?, cargo_group_code?}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    name = data.get("name")
    raw_group = data.get("cargo_group_code")

    cargo_group_code = None
    if raw_group == "":
        # Пустая строка — снять привязку к группе
        cargo_group_code = 0
    elif raw_group not in (None, "null"):
        try:
            cargo_group_code = int(raw_group)
        except (TypeError, ValueError):
            return JsonResponse(
                {"success": False, "errors": ["Код группы груза должен быть целым числом"]},
                status=400,
            )

    dto = UpdateCargoDTO(
        name=name,
        cargo_group_code=cargo_group_code,
    )

    service = CargoService()
    cargo, errors = service.update_cargo(code, dto)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "code": cargo.code,
                "name": cargo.name,
                "cargo_group_code": cargo.cargo_group_code,
                "cargo_group_name": cargo.cargo_group_name,
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def cargo_delete_api(request, code: int):
    """
    Удаление груза.
    """
    service = CargoService()
    _success, errors = service.delete_cargo(code)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=404)

    return JsonResponse({"success": True})


# === RailRoad: HTML-страницы ===


@login_required
def railroad_list_view(request):
    """
    Страница со списком железных дорог.
    """
    from core.models import RailRoad

    countries = (
        RailRoad.objects.exclude(country="")
        .order_by("country")
        .values_list("country", flat=True)
        .distinct()
    )
    directions = (
        RailRoad.objects.exclude(direction="")
        .order_by("direction")
        .values_list("direction", flat=True)
        .distinct()
    )

    return render(
        request,
        "core/railroad_list.html",
        {
            "countries": countries,
            "directions": directions,
        },
    )


# === RailRoad: API (JSON) ===


@login_required
@require_http_methods(["GET"])
def railroad_list_api(request):
    """
    Список железных дорог с пагинацией и фильтрами.
    """
    service = RailRoadService()

    try:
        page = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(request.GET.get("page_size", "20"))
    except (TypeError, ValueError):
        page_size = 20

    search = request.GET.get("search") or None
    code = request.GET.get("code") or None
    name = request.GET.get("name") or None
    country = request.GET.get("country") or None
    direction = request.GET.get("direction") or None

    result, errors = service.list_railroads(
        page=page,
        page_size=page_size,
        search=search,
        code=code,
        name=name,
        country=country,
        direction=direction,
    )

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "items": [
                {
                    "code": item.code,
                    "name": item.name,
                    "country": item.country,
                    "direction": item.direction,
                }
                for item in result.items
            ],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "total_pages": result.total_pages,
        }
    )


@login_required
@require_http_methods(["GET"])
def railroad_detail_api(request, code: str):
    """
    Детали одной железной дороги.
    """
    service = RailRoadService()
    railroad, errors = service.get_railroad(code)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=404)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "code": railroad.code,
                "name": railroad.name,
                "country": railroad.country,
                "direction": railroad.direction,
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def railroad_create_api(request):
    """
    Создание новой железной дороги.
    Ожидает JSON: {code, name, country?, direction?}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    code = (data.get("code") or "").strip()
    name = data.get("name", "")
    country = data.get("country", "")
    direction = data.get("direction", "")

    dto = CreateRailRoadDTO(
        code=code,
        name=name,
        country=country or "",
        direction=direction or "",
    )

    service = RailRoadService()
    railroad, errors = service.create_railroad(dto)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "code": railroad.code,
                "name": railroad.name,
                "country": railroad.country,
                "direction": railroad.direction,
            },
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def railroad_update_api(request, code: str):
    """
    Обновление существующей железной дороги.
    Ожидает JSON: {name?, country?, direction?}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    name = data.get("name")
    country = data.get("country")
    direction = data.get("direction")

    dto = UpdateRailRoadDTO(
        name=name,
        country=country,
        direction=direction,
    )

    service = RailRoadService()
    railroad, errors = service.update_railroad(code, dto)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "code": railroad.code,
                "name": railroad.name,
                "country": railroad.country,
                "direction": railroad.direction,
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def railroad_delete_api(request, code: str):
    """
    Удаление железной дороги.
    """
    service = RailRoadService()
    _success, errors = service.delete_railroad(code)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=404)

    return JsonResponse({"success": True})


# === Region: HTML-страницы ===


@login_required
def region_list_view(request):
    """
    Страница со списком регионов.
    """
    types = (
        Region.objects.exclude(type="")
        .order_by("type")
        .values_list("type", flat=True)
        .distinct()
    )
    return render(
        request,
        "core/region_list.html",
        {
            "types": types,
        },
    )


# === Region: API (JSON) ===


@login_required
@require_http_methods(["GET"])
def region_list_api(request):
    """
    Список регионов с пагинацией и фильтрами.
    """
    try:
        page = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(request.GET.get("page_size", "20"))
    except (TypeError, ValueError):
        page_size = 20

    search = request.GET.get("search") or ""
    region_type = request.GET.get("type") or ""

    qs = Region.objects.all()
    if search:
        search = search.strip()
        if search:
            s = search.casefold()
            qs = qs.filter(
                Q(full_name_search__contains=s)
                | Q(short_name_search__contains=s)
            )
    if region_type:
        region_type = region_type.strip()
        if region_type:
            # type часто кириллицей — используем нормализованное поле
            qs = qs.filter(type_search__contains=region_type.casefold())

    paginator = Paginator(qs.order_by("full_name", "type"), page_size)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    items = [
        {
            "id": region.id,
            "short_name": region.short_name,
            "full_name": region.full_name,
            "type": region.type,
        }
        for region in page_obj.object_list
    ]

    return JsonResponse(
        {
            "success": True,
            "items": items,
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_obj.paginator.per_page,
            "total_pages": paginator.num_pages,
        }
    )


@login_required
@require_http_methods(["GET"])
def region_detail_api(request, pk: int):
    """
    Детали одного региона.
    """
    try:
        region = Region.objects.get(pk=pk)
    except Region.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Регион не найден"]},
            status=404,
        )

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": region.id,
                "short_name": region.short_name,
                "full_name": region.full_name,
                "type": region.type,
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def region_create_api(request):
    """
    Создание нового региона.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    full_name = (data.get("full_name") or "").strip()
    short_name = (data.get("short_name") or "").strip()
    region_type = (data.get("type") or "").strip()

    errors: list[str] = []
    if not full_name:
        errors.append("Полное наименование региона обязательно")
    if not region_type:
        errors.append("Тип региона обязателен")

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    region, created = Region.objects.get_or_create(
        full_name=full_name,
        type=region_type,
        defaults={
            "short_name": short_name or full_name,
        },
    )

    if not created:
        return JsonResponse(
            {
                "success": False,
                "errors": ["Регион с таким полным наименованием и типом уже существует"],
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": region.id,
                "short_name": region.short_name,
                "full_name": region.full_name,
                "type": region.type,
            },
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def region_update_api(request, pk: int):
    """
    Обновление существующего региона.
    """
    try:
        region = Region.objects.get(pk=pk)
    except Region.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Регион не найден"]},
            status=404,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    full_name = (data.get("full_name") or region.full_name).strip()
    short_name = (data.get("short_name") or region.short_name).strip()
    region_type = (data.get("type") or region.type).strip()

    errors: list[str] = []
    if not full_name:
        errors.append("Полное наименование региона обязательно")
    if not region_type:
        errors.append("Тип региона обязателен")

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    # Проверяем уникальность
    exists = Region.objects.exclude(pk=region.pk).filter(
        full_name=full_name,
        type=region_type,
    )
    if exists.exists():
        return JsonResponse(
            {
                "success": False,
                "errors": ["Другой регион с таким полным наименованием и типом уже существует"],
            },
            status=400,
        )

    region.full_name = full_name
    region.short_name = short_name or full_name
    region.type = region_type
    region.save()

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": region.id,
                "short_name": region.short_name,
                "full_name": region.full_name,
                "type": region.type,
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def region_delete_api(request, pk: int):
    """
    Удаление региона.
    """
    try:
        region = Region.objects.get(pk=pk)
    except Region.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Регион не найден"]},
            status=404,
        )

    try:
        region.delete()
    except Exception:
        return JsonResponse(
            {
                "success": False,
                "errors": ["Не удалось удалить регион (возможно, есть связанные станции)"],
            },
            status=400,
        )

    return JsonResponse({"success": True})


# === Station: HTML-страницы ===


@login_required
def station_list_view(request):
    """
    Страница со списком станций.
    """
    railroads = RailRoad.objects.all().order_by("code")
    regions = Region.objects.all().order_by("full_name", "type")
    return render(
        request,
        "core/station_list.html",
        {
            "railroads": railroads,
            "regions": regions,
        },
    )


# === Station: API (JSON) ===


@login_required
@require_http_methods(["GET"])
def station_list_api(request):
    """
    Список станций с пагинацией и фильтрами.
    """
    try:
        page = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(request.GET.get("page_size", "20"))
    except (TypeError, ValueError):
        page_size = 20

    search = request.GET.get("search") or ""
    railroad_code = request.GET.get("railroad") or ""
    region_id = request.GET.get("region_id") or ""

    qs = Station.objects.select_related("region", "railroad").all()

    if search:
        search = search.strip()
        if search:
            s = search.casefold()
            q = Q(short_name_search__contains=s) | Q(full_name_search__contains=s)
            # esr_code — число, поэтому ищем по нему только если введены цифры
            if search.isdigit():
                q = Q(esr_code=int(search)) | q
            qs = qs.filter(q)

    if railroad_code:
        railroad_code = railroad_code.strip()
        if railroad_code:
            qs = qs.filter(railroad__code=railroad_code)

    if region_id:
        try:
            region_id_int = int(region_id)
        except ValueError:
            return JsonResponse(
                {"success": False, "errors": ["Некорректный идентификатор региона"]},
                status=400,
            )
        qs = qs.filter(region_id=region_id_int)

    paginator = Paginator(qs.order_by("esr_code"), page_size)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    items = []
    for st in page_obj.object_list:
        items.append(
            {
                "esr_code": st.esr_code,
                "short_name": st.short_name,
                "full_name": st.full_name,
                "region_id": st.region_id,
                "region_full_name": st.region.full_name if st.region_id else "",
                "railroad_code": st.railroad.code if st.railroad_id else "",
                "railroad_name": st.railroad.name if st.railroad_id else "",
                "railroad_direction": st.railroad.direction if st.railroad_id else "",
            }
        )

    return JsonResponse(
        {
            "success": True,
            "items": items,
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_obj.paginator.per_page,
            "total_pages": paginator.num_pages,
        }
    )


@login_required
@require_http_methods(["GET"])
def station_detail_api(request, esr_code: int):
    """
    Детали одной станции.
    """
    try:
        station = Station.objects.select_related("region", "railroad").get(
            esr_code=esr_code
        )
    except Station.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Станция не найдена"]},
            status=404,
        )

    return JsonResponse(
        {
            "success": True,
            "item": {
                "esr_code": station.esr_code,
                "short_name": station.short_name,
                "full_name": station.full_name,
                "region_id": station.region_id,
                "region_full_name": station.region.full_name if station.region_id else "",
                "railroad_code": station.railroad.code if station.railroad_id else "",
                "railroad_name": station.railroad.name if station.railroad_id else "",
                "railroad_direction": station.railroad.direction
                if station.railroad_id
                else "",
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def station_create_api(request):
    """
    Создание новой станции.
    Ожидает JSON: {esr_code, short_name, full_name?, region_id, railroad_code}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    errors: list[str] = []

    esr_raw = data.get("esr_code")
    try:
        esr_code = int(esr_raw)
    except (TypeError, ValueError):
        errors.append("Код ЕСР должен быть целым числом")
        esr_code = None

    short_name = (data.get("short_name") or "").strip()
    full_name = (data.get("full_name") or "").strip()
    region_id = data.get("region_id")
    railroad_code = (data.get("railroad_code") or "").strip()

    if not short_name:
        errors.append("Краткое наименование станции обязательно")

    region_obj: Region | None = None
    if region_id in (None, "", "null"):
        errors.append("Регион обязателен")
    else:
        try:
            region_pk = int(region_id)
            region_obj = Region.objects.get(pk=region_pk)
        except (ValueError, Region.DoesNotExist):
            errors.append("Указан несуществующий регион")

    railroad_obj: RailRoad | None = None
    if not railroad_code:
        errors.append("Код железной дороги обязателен")
    else:
        try:
            railroad_obj = RailRoad.objects.get(code=railroad_code)
        except RailRoad.DoesNotExist:
            errors.append("Указана несуществующая железная дорога")

    if esr_code is not None and Station.objects.filter(esr_code=esr_code).exists():
        errors.append(f"Станция с кодом ЕСР {esr_code} уже существует")

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    station = Station.objects.create(
        esr_code=esr_code,
        short_name=short_name,
        full_name=full_name or short_name,
        region=region_obj,
        railroad=railroad_obj,
    )

    return JsonResponse(
        {
            "success": True,
            "item": {
                "esr_code": station.esr_code,
                "short_name": station.short_name,
                "full_name": station.full_name,
                "region_id": station.region_id,
                "region_full_name": station.region.full_name
                if station.region_id
                else "",
                "railroad_code": station.railroad.code if station.railroad_id else "",
            },
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def station_update_api(request, esr_code: int):
    """
    Обновление существующей станции.
    Ожидает JSON: {short_name?, full_name?, region_id?, railroad_code?}
    """
    try:
        station = Station.objects.get(esr_code=esr_code)
    except Station.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Станция не найдена"]},
            status=404,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    errors: list[str] = []

    short_name = data.get("short_name")
    full_name = data.get("full_name")
    region_id = data.get("region_id")
    railroad_code = data.get("railroad_code")

    if short_name is not None and not str(short_name).strip():
        errors.append("Краткое наименование станции не может быть пустым")

    region_obj: Region | None = None
    if region_id not in (None, "", "null"):
        try:
            region_pk = int(region_id)
            region_obj = Region.objects.get(pk=region_pk)
        except (ValueError, Region.DoesNotExist):
            errors.append("Указан несуществующий регион")

    railroad_obj: RailRoad | None = None
    if railroad_code not in (None, "", "null"):
        try:
            railroad_obj = RailRoad.objects.get(code=str(railroad_code))
        except RailRoad.DoesNotExist:
            errors.append("Указана несуществующая железная дорога")

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    if short_name is not None:
        station.short_name = str(short_name).strip()
    if full_name is not None:
        station.full_name = str(full_name).strip()
    if region_id not in (None, "", "null") and region_obj is not None:
        station.region = region_obj
    if railroad_code not in (None, "", "null") and railroad_obj is not None:
        station.railroad = railroad_obj

    if not station.full_name:
        station.full_name = station.short_name

    station.save()

    return JsonResponse(
        {
            "success": True,
            "item": {
                "esr_code": station.esr_code,
                "short_name": station.short_name,
                "full_name": station.full_name,
                "region_id": station.region_id,
                "region_full_name": station.region.full_name
                if station.region_id
                else "",
                "railroad_code": station.railroad.code if station.railroad_id else "",
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def station_delete_api(request, esr_code: int):
    """
    Удаление станции.
    """
    try:
        station = Station.objects.get(esr_code=esr_code)
    except Station.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Станция не найдена"]},
            status=404,
        )

    station.delete()

    return JsonResponse({"success": True})


def _parse_bool_param(raw: str | None) -> bool | None:
    if raw in (None, ""):
        return None
    if raw in ("1", "true", "True", "yes", "on"):
        return True
    if raw in ("0", "false", "False", "no", "off"):
        return False
    return None


def _simple_dict_list_api(request, model):
    try:
        page = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(request.GET.get("page_size", "20"))
    except (TypeError, ValueError):
        page_size = 20

    search = (request.GET.get("search") or "").strip()
    is_active_raw = request.GET.get("is_active")
    is_active = _parse_bool_param(is_active_raw)

    qs = model.objects.all()
    if search:
        s = search.casefold()
        qs = qs.filter(name_search__contains=s)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)

    paginator = Paginator(qs.order_by("position", "name"), page_size)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    items = [
        {
            "id": item.id,
            "name": item.name,
            "code": item.code,
            "position": item.position,
            "is_active": item.is_active,
        }
        for item in page_obj.object_list
    ]

    return JsonResponse(
        {
            "success": True,
            "items": items,
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_obj.paginator.per_page,
            "total_pages": paginator.num_pages,
        }
    )


def _simple_dict_detail_api(model, pk: int):
    try:
        item = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Запись не найдена"]}, status=404)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": item.id,
                "name": item.name,
                "code": item.code,
                "position": item.position,
                "is_active": item.is_active,
            },
        }
    )


def _simple_dict_create_api(request, model):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "errors": ["Неверный формат JSON"]}, status=400)

    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()
    position_raw = data.get("position")
    is_active = bool(data.get("is_active", True))

    errors: list[str] = []
    if not name:
        errors.append("Название обязательно")

    position = 0
    if position_raw not in (None, "", "null"):
        try:
            position = int(position_raw)
        except (TypeError, ValueError):
            errors.append("Позиция должна быть целым числом")

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    if model.objects.filter(name=name).exists():
        return JsonResponse({"success": False, "errors": ["Запись с таким названием уже существует"]}, status=400)

    if code and model.objects.filter(code=code).exists():
        return JsonResponse({"success": False, "errors": ["Запись с таким кодом уже существует"]}, status=400)

    item = model.objects.create(
        name=name,
        code=code,
        position=position,
        is_active=is_active,
    )

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": item.id,
                "name": item.name,
                "code": item.code,
                "position": item.position,
                "is_active": item.is_active,
            },
        },
        status=201,
    )


def _simple_dict_update_api(request, model, pk: int):
    try:
        item = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Запись не найдена"]}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "errors": ["Неверный формат JSON"]}, status=400)

    name = data.get("name")
    code = data.get("code")
    position_raw = data.get("position")
    is_active_raw = data.get("is_active")

    errors: list[str] = []

    if name is not None:
        name = str(name).strip()
        if not name:
            errors.append("Название обязательно")
        else:
            if model.objects.exclude(pk=item.pk).filter(name=name).exists():
                errors.append("Запись с таким названием уже существует")

    if code is not None:
        code = str(code).strip()
        if code and model.objects.exclude(pk=item.pk).filter(code=code).exists():
            errors.append("Запись с таким кодом уже существует")

    position = None
    if position_raw is not None:
        try:
            position = int(position_raw)
        except (TypeError, ValueError):
            errors.append("Позиция должна быть целым числом")

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    if name is not None:
        item.name = name
    if code is not None:
        item.code = code
    if position is not None:
        item.position = position
    if is_active_raw is not None:
        item.is_active = bool(is_active_raw)

    item.save()

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": item.id,
                "name": item.name,
                "code": item.code,
                "position": item.position,
                "is_active": item.is_active,
            },
        }
    )


def _simple_dict_delete_api(model, pk: int):
    try:
        item = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Запись не найдена"]}, status=404)

    item.delete()
    return JsonResponse({"success": True})


# === WagonKind ===


@login_required
def wagon_kind_list_view(request):
    return render(
        request,
        "core/wagon_kind_list.html",
        {
            "page_title": "Роды вагонов",
            "page_subtitle": "Справочник рода вагона (создание/редактирование/удаление)",
            "list_api_url": "/references/api/wagon-kinds/",
            "create_api_url": "/references/api/wagon-kinds/create/",
            "detail_api_url_template": "/references/api/wagon-kinds/0/",
            "update_api_url_template": "/references/api/wagon-kinds/0/update/",
            "delete_api_url_template": "/references/api/wagon-kinds/0/delete/",
        },
    )


@login_required
@require_http_methods(["GET"])
def wagon_kind_list_api(request):
    return _simple_dict_list_api(request, WagonKind)


@login_required
@require_http_methods(["GET"])
def wagon_kind_detail_api(request, pk: int):
    return _simple_dict_detail_api(WagonKind, pk)


@login_required
@require_http_methods(["POST"])
def wagon_kind_create_api(request):
    return _simple_dict_create_api(request, WagonKind)


@login_required
@require_http_methods(["POST"])
def wagon_kind_update_api(request, pk: int):
    return _simple_dict_update_api(request, WagonKind, pk)


@login_required
@require_http_methods(["POST"])
def wagon_kind_delete_api(request, pk: int):
    return _simple_dict_delete_api(WagonKind, pk)


# === ShipmentType ===


@login_required
def shipment_type_list_view(request):
    return render(
        request,
        "core/shipment_type_list.html",
        {
            "page_title": "Типы отправки",
            "page_subtitle": "Справочник типа отправки (создание/редактирование/удаление)",
            "list_api_url": "/references/api/shipment-types/",
            "create_api_url": "/references/api/shipment-types/create/",
            "detail_api_url_template": "/references/api/shipment-types/0/",
            "update_api_url_template": "/references/api/shipment-types/0/update/",
            "delete_api_url_template": "/references/api/shipment-types/0/delete/",
        },
    )


@login_required
@require_http_methods(["GET"])
def shipment_type_list_api(request):
    return _simple_dict_list_api(request, ShipmentType)


@login_required
@require_http_methods(["GET"])
def shipment_type_detail_api(request, pk: int):
    return _simple_dict_detail_api(ShipmentType, pk)


@login_required
@require_http_methods(["POST"])
def shipment_type_create_api(request):
    return _simple_dict_create_api(request, ShipmentType)


@login_required
@require_http_methods(["POST"])
def shipment_type_update_api(request, pk: int):
    return _simple_dict_update_api(request, ShipmentType, pk)


@login_required
@require_http_methods(["POST"])
def shipment_type_delete_api(request, pk: int):
    return _simple_dict_delete_api(ShipmentType, pk)


# === MessageType ===


@login_required
def message_type_list_view(request):
    return render(
        request,
        "core/message_type_list.html",
        {
            "page_title": "Виды сообщения",
            "page_subtitle": "Справочник вида сообщения (создание/редактирование/удаление)",
            "list_api_url": "/references/api/message-types/",
            "create_api_url": "/references/api/message-types/create/",
            "detail_api_url_template": "/references/api/message-types/0/",
            "update_api_url_template": "/references/api/message-types/0/update/",
            "delete_api_url_template": "/references/api/message-types/0/delete/",
        },
    )


@login_required
@require_http_methods(["GET"])
def message_type_list_api(request):
    return _simple_dict_list_api(request, MessageType)


@login_required
@require_http_methods(["GET"])
def message_type_detail_api(request, pk: int):
    return _simple_dict_detail_api(MessageType, pk)


@login_required
@require_http_methods(["POST"])
def message_type_create_api(request):
    return _simple_dict_create_api(request, MessageType)


@login_required
@require_http_methods(["POST"])
def message_type_update_api(request, pk: int):
    return _simple_dict_update_api(request, MessageType, pk)


@login_required
@require_http_methods(["POST"])
def message_type_delete_api(request, pk: int):
    return _simple_dict_delete_api(MessageType, pk)


# === Shipper: HTML и API ===


def _shipper_item_dict(shipper: Shipper) -> dict:
    holding = (shipper.holding or "").strip()
    text = shipper.name
    if holding:
        text = f"{text} ({holding})"
    return {
        "id": shipper.id,
        "name": shipper.name,
        "holding": holding,
        "okpo": shipper.okpo,
        "inn": shipper.inn,
        "text": text,
    }


@login_required
def shipper_list_view(request):
    holdings = (
        Shipper.objects.exclude(holding="")
        .order_by("holding")
        .values_list("holding", flat=True)
        .distinct()
    )
    return render(
        request,
        "core/shipper_list.html",
        {"holdings": holdings},
    )


@login_required
@require_http_methods(["GET"])
def shipper_list_api(request):
    try:
        page = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.GET.get("page_size", "20"))
    except (TypeError, ValueError):
        page_size = 20

    qs = Shipper.objects.all().order_by("name")
    holding = (request.GET.get("holding") or "").strip()
    if holding:
        qs = qs.filter(holding=holding)

    search = (request.GET.get("search") or "").strip()
    if search:
        s = search.casefold()
        if search.isdigit():
            qs = qs.filter(
                Q(okpo=int(search))
                | Q(inn__icontains=search)
                | Q(name_search__contains=s)
                | Q(holding__icontains=search)
            )
        else:
            qs = qs.filter(
                Q(name_search__contains=s) | Q(holding__icontains=search)
            )

    paginator = Paginator(qs, page_size)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    items = [_shipper_item_dict(shipper) for shipper in page_obj.object_list]

    return JsonResponse(
        {
            "success": True,
            "items": items,
            "total": paginator.count,
            "page": page_obj.number,
            "page_size": page_size,
            "total_pages": paginator.num_pages,
        }
    )


@login_required
@require_http_methods(["GET"])
def shipper_detail_api(request, pk: int):
    try:
        shipper = Shipper.objects.get(pk=pk)
    except Shipper.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Грузоотправитель не найден"]}, status=404)

    return JsonResponse({"success": True, "item": _shipper_item_dict(shipper)})


@login_required
@require_http_methods(["POST"])
def shipper_create_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "errors": ["Неверный формат JSON"]}, status=400)

    errors: list[str] = []
    name = (data.get("name") or "").strip()
    if not name:
        errors.append("Наименование обязательно")

    okpo, okpo_error = _parse_shipper_okpo(data.get("okpo"))
    if okpo_error:
        errors.append(okpo_error)

    inn = (data.get("inn") or "").strip()
    holding = (data.get("holding") or "").strip()

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    if Shipper.objects.filter(okpo=okpo, inn=inn, name=name).exists():
        return JsonResponse(
            {"success": False, "errors": ["Грузоотправитель с такими ОКПО, ИНН и названием уже существует"]},
            status=400,
        )

    shipper = Shipper.objects.create(okpo=okpo, inn=inn, name=name, holding=holding)
    return JsonResponse({"success": True, "item": _shipper_item_dict(shipper)}, status=201)


@login_required
@require_http_methods(["POST"])
def shipper_update_api(request, pk: int):
    try:
        shipper = Shipper.objects.get(pk=pk)
    except Shipper.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Грузоотправитель не найден"]}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "errors": ["Неверный формат JSON"]}, status=400)

    errors: list[str] = []
    name = shipper.name
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            errors.append("Наименование обязательно")

    okpo = shipper.okpo
    if "okpo" in data:
        okpo, okpo_error = _parse_shipper_okpo(data.get("okpo"))
        if okpo_error:
            errors.append(okpo_error)

    inn = shipper.inn
    if "inn" in data:
        inn = (data.get("inn") or "").strip()

    holding = shipper.holding
    if "holding" in data:
        holding = (data.get("holding") or "").strip()

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    if Shipper.objects.exclude(pk=shipper.pk).filter(okpo=okpo, inn=inn, name=name).exists():
        return JsonResponse(
            {"success": False, "errors": ["Грузоотправитель с такими ОКПО, ИНН и названием уже существует"]},
            status=400,
        )

    shipper.okpo = okpo
    shipper.inn = inn
    shipper.name = name
    shipper.holding = holding
    shipper.save()

    return JsonResponse({"success": True, "item": _shipper_item_dict(shipper)})


@login_required
@require_http_methods(["POST"])
def shipper_delete_api(request, pk: int):
    try:
        shipper = Shipper.objects.get(pk=pk)
    except Shipper.DoesNotExist:
        return JsonResponse({"success": False, "errors": ["Грузоотправитель не найден"]}, status=404)

    shipper.delete()
    return JsonResponse({"success": True})


def _parse_shipper_okpo(raw) -> tuple[int | None, str | None]:
    if raw in (None, "", "null"):
        return None, None
    try:
        return int(str(raw).strip()), None
    except (TypeError, ValueError):
        return None, "ОКПО должно быть целым числом"


# === Routes: HTML-страница ===


@login_required
def routes_list_view(request):
    wagon_kinds = WagonKind.objects.all().order_by("name")
    shipment_types = ShipmentType.objects.all().order_by("name")
    message_types = MessageType.objects.all().order_by("name")

    return render(
        request,
        "core/routes_list.html",
        {
            "page_title": "Маршруты",
            "page_subtitle": "Управление наборами маршрутов и маршрутами",
            "route_set_list_api_url": "/references/api/route-sets/",
            "route_set_detail_api_url_template": "/references/api/route-sets/0/",
            "route_set_create_api_url": "/references/api/route-sets/create/",
            "route_set_update_api_url_template": "/references/api/route-sets/0/update/",
            "route_set_delete_api_url_template": "/references/api/route-sets/0/delete/",
            "route_list_api_url": "/references/api/routes/",
            "route_detail_api_url_template": "/references/api/routes/0/",
            "route_create_api_url": "/references/api/routes/create/",
            "route_update_api_url_template": "/references/api/routes/0/update/",
            "route_delete_api_url_template": "/references/api/routes/0/delete/",
            "wagon_kinds": wagon_kinds,
            "shipment_types": shipment_types,
            "message_types": message_types,
        },
    )


# === RouteSet: API (JSON) ===


@login_required
@require_http_methods(["GET"])
def route_set_list_api(request):
    try:
        page = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(request.GET.get("page_size", "50"))
    except (TypeError, ValueError):
        page_size = 50

    search = (request.GET.get("search") or "").strip() or None

    service = RouteSetService()
    result, errors = service.list_sets(page=page, page_size=page_size, search=search)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse({"success": True, **result.to_api_dict()})


@login_required
@require_http_methods(["GET"])
def route_set_detail_api(request, pk: int):
    service = RouteSetService()
    item, errors = service.get_set(pk)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=404)

    return JsonResponse({"success": True, "item": item.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def route_set_create_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    dto = CreateRouteSetDTO(
        name=(data.get("name") or "").strip(),
        code=(data.get("code") or "").strip(),
    )
    service = RouteSetService()
    item, errors = service.create_set(dto)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {"success": True, "item": item.to_api_dict()},
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def route_set_update_api(request, pk: int):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    name_raw = data.get("name")
    code_raw = data.get("code")
    dto = UpdateRouteSetDTO(
        name=(str(name_raw).strip() if name_raw is not None else None),
        code=(str(code_raw).strip() if code_raw is not None else None),
    )

    service = RouteSetService()
    item, errors = service.update_set(pk, dto)
    if errors:
        return JsonResponse(
            {"success": False, "errors": errors},
            status=404 if errors == ["Набор маршрутов не найден"] else 400,
        )

    return JsonResponse({"success": True, "item": item.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def route_set_delete_api(request, pk: int):
    service = RouteSetService()
    _success, errors = service.delete_set(pk)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=404)

    return JsonResponse({"success": True})


# === Route: API (JSON) ===


def _route_not_found_status(errors: list[str]) -> int:
    return 404 if errors == ["Маршрут не найден"] else 400


@login_required
@require_http_methods(["GET"])
def route_list_api(request):
    try:
        page = int(request.GET.get("page", "1"))
    except (TypeError, ValueError):
        page = 1

    try:
        page_size = int(request.GET.get("page_size", "20"))
    except (TypeError, ValueError):
        page_size = 20

    try:
        route_set_id = int(request.GET.get("route_set_id", "0"))
    except (TypeError, ValueError):
        route_set_id = 0

    search = (request.GET.get("search") or "").strip() or None
    filters = RouteListFiltersDTO(
        route_set_id=route_set_id,
        page=page,
        page_size=page_size,
        search=search,
        origin_esr=request.GET.get("origin_esr") or None,
        destination_esr=request.GET.get("destination_esr") or None,
    )

    service = RouteService()
    result, errors = service.list_routes(filters)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse({"success": True, **result.to_api_dict()})


@login_required
@require_http_methods(["GET"])
def route_detail_api(request, pk: int):
    service = RouteService()
    item, errors = service.get_route(pk)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=404)

    return JsonResponse({"success": True, "item": item.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def route_create_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    service = RouteService()
    item, errors = service.create_route(data)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    return JsonResponse(
        {"success": True, "item": item.to_api_dict()},
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def route_update_api(request, pk: int):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    service = RouteService()
    item, errors = service.update_route(pk, data)
    if errors:
        return JsonResponse(
            {"success": False, "errors": errors},
            status=_route_not_found_status(errors),
        )

    return JsonResponse({"success": True, "item": item.to_api_dict()})


@login_required
@require_http_methods(["POST"])
def route_delete_api(request, pk: int):
    service = RouteService()
    _success, errors = service.delete_route(pk)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=404)

    return JsonResponse({"success": True})


@login_required
@require_http_methods(["POST"])
def route_analysis_api(request):
    """
    Расчёт экрана «Экономика грузов»: таблица, эквалайзер, KPI, эффекты.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    scenario_id = data.get("scenario_id")
    route_id = data.get("route_id")
    try:
        scenario_id = int(scenario_id)
        route_id = int(route_id)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "errors": ["Некорректные scenario_id или route_id"]},
            status=400,
        )

    dto = RouteAnalysisRequestDTO(
        scenario_id=scenario_id,
        route_id=route_id,
        overrides=RouteAnalysisRequestDTO.parse_overrides(data.get("overrides")),
    )
    errors = dto.validate()
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    try:
        scenario = (
            Scenario.objects.select_related("inflation_set", "exchange_rate_set")
            .prefetch_related(
                "inflation_set__values",
                "exchange_rate_set__values",
                "price_change_settings",
            )
            .get(pk=dto.scenario_id)
        )
    except Scenario.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Сценарий не найден"]},
            status=404,
        )
    if not AppSettingsService().can_read_scenario(
        author_id=scenario.author_id,
        user_id=request.user.id,
    ):
        return JsonResponse(
            {"success": False, "errors": ["Сценарий не найден"]},
            status=404,
        )

    try:
        route = Route.objects.select_related("message_type").get(pk=dto.route_id)
    except Route.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Маршрут не найден"]},
            status=404,
        )

    if route.route_set_id != scenario.route_set_id:
        return JsonResponse(
            {"success": False, "errors": ["Маршрут не найден"]},
            status=404,
        )

    service = RouteAnalysisService()
    response_dto = service.calculate(
        request_dto=dto,
        scenario=scenario,
        route=route,
    )

    return JsonResponse(
        {
            "success": True,
            **response_dto.to_api_dict(),
        }
    )

