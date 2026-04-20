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
from core.domain.railroad.dto import CreateRailRoadDTO, UpdateRailRoadDTO
from core.domain.railroad.services import RailRoadService
from core.models import (
    Region,
    Station,
    RailRoad,
    WagonKind,
    ShipmentType,
    MessageType,
    RouteSet,
    Route,
    Cargo,
)


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
            "page_title": "Типы сообщения",
            "page_subtitle": "Справочник типа сообщения (создание/редактирование/удаление)",
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

    search = (request.GET.get("search") or "").strip()

    qs = RouteSet.objects.all()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))

    paginator = Paginator(qs.order_by("name"), page_size)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    items = []
    for rs in page_obj.object_list:
        items.append(
            {
                "id": rs.id,
                "name": rs.name,
                "code": rs.code,
                "routes_count": rs.routes.count(),
                "created_at": rs.created_at.isoformat() if rs.created_at else None,
                "updated_at": rs.updated_at.isoformat() if rs.updated_at else None,
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
def route_set_detail_api(request, pk: int):
    try:
        rs = RouteSet.objects.get(pk=pk)
    except RouteSet.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Набор маршрутов не найден"]},
            status=404,
        )

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": rs.id,
                "name": rs.name,
                "code": rs.code,
                "routes_count": rs.routes.count(),
                "created_at": rs.created_at.isoformat() if rs.created_at else None,
                "updated_at": rs.updated_at.isoformat() if rs.updated_at else None,
            },
        }
    )


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

    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()

    errors: list[str] = []
    if not name:
        errors.append("Название набора обязательно")
    if not code:
        errors.append("Код набора обязателен")

    if RouteSet.objects.filter(name=name).exists():
        errors.append("Набор с таким названием уже существует")
    if RouteSet.objects.filter(code=code).exists():
        errors.append("Набор с таким кодом уже существует")

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    rs = RouteSet.objects.create(name=name, code=code)

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": rs.id,
                "name": rs.name,
                "code": rs.code,
                "routes_count": 0,
                "created_at": rs.created_at.isoformat() if rs.created_at else None,
                "updated_at": rs.updated_at.isoformat() if rs.updated_at else None,
            },
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def route_set_update_api(request, pk: int):
    try:
        rs = RouteSet.objects.get(pk=pk)
    except RouteSet.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Набор маршрутов не найден"]},
            status=404,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    name_raw = data.get("name")
    code_raw = data.get("code")

    errors: list[str] = []

    if name_raw is not None:
        name = (str(name_raw) or "").strip()
        if not name:
            errors.append("Название набора обязательно")
        elif RouteSet.objects.exclude(pk=rs.pk).filter(name=name).exists():
            errors.append("Другой набор с таким названием уже существует")
    else:
        name = rs.name

    if code_raw is not None:
        code = (str(code_raw) or "").strip()
        if not code:
            errors.append("Код набора обязателен")
        elif RouteSet.objects.exclude(pk=rs.pk).filter(code=code).exists():
            errors.append("Другой набор с таким кодом уже существует")
    else:
        code = rs.code

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    rs.name = name
    rs.code = code
    rs.save()

    return JsonResponse(
        {
            "success": True,
            "item": {
                "id": rs.id,
                "name": rs.name,
                "code": rs.code,
                "routes_count": rs.routes.count(),
                "created_at": rs.created_at.isoformat() if rs.created_at else None,
                "updated_at": rs.updated_at.isoformat() if rs.updated_at else None,
            },
        }
    )


@login_required
@require_http_methods(["POST"])
def route_set_delete_api(request, pk: int):
    try:
        rs = RouteSet.objects.get(pk=pk)
    except RouteSet.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Набор маршрутов не найден"]},
            status=404,
        )

    rs.delete()

    return JsonResponse({"success": True})


# === Route: API (JSON) ===


def _get_route_payload_errors(data: dict) -> tuple[dict, list[str]]:
    errors: list[str] = []

    payload: dict = {}

    route_set_id = data.get("route_set_id")
    if route_set_id in (None, "", "null"):
        errors.append("Набор маршрутов обязателен")
    else:
        try:
            payload["route_set"] = RouteSet.objects.get(pk=int(route_set_id))
        except (ValueError, RouteSet.DoesNotExist):
            errors.append("Указан несуществующий набор маршрутов")

    cargo_code = data.get("cargo_code")
    if cargo_code in (None, "", "null"):
        errors.append("Код груза обязателен")
    else:
        try:
            payload["cargo"] = Cargo.objects.get(code=int(cargo_code))
        except (ValueError, Cargo.DoesNotExist):
            errors.append("Указан несуществующий груз (код ETSNG)")

    origin_esr = data.get("origin_esr_code")
    if origin_esr in (None, "", "null"):
        errors.append("Код ЕСР станции отправления обязателен")
    else:
        try:
            payload["origin_station"] = Station.objects.get(esr_code=int(origin_esr))
        except (ValueError, Station.DoesNotExist):
            errors.append("Указана несуществующая станция отправления")

    destination_esr = data.get("destination_esr_code")
    if destination_esr in (None, "", "null"):
        errors.append("Код ЕСР станции назначения обязателен")
    else:
        try:
            payload["destination_station"] = Station.objects.get(
                esr_code=int(destination_esr)
            )
        except (ValueError, Station.DoesNotExist):
            errors.append("Указана несуществующая станция назначения")

    wagon_kind_id = data.get("wagon_kind_id")
    if wagon_kind_id in (None, "", "null"):
        errors.append("Род вагона обязателен")
    else:
        try:
            payload["wagon_kind"] = WagonKind.objects.get(pk=int(wagon_kind_id))
        except (ValueError, WagonKind.DoesNotExist):
            errors.append("Указан несуществующий род вагона")

    shipment_type_id = data.get("shipment_type_id")
    if shipment_type_id in (None, "", "null"):
        errors.append("Тип отправки обязателен")
    else:
        try:
            payload["shipment_type"] = ShipmentType.objects.get(
                pk=int(shipment_type_id)
            )
        except (ValueError, ShipmentType.DoesNotExist):
            errors.append("Указан несуществующий тип отправки")

    message_type_id = data.get("message_type_id")
    if message_type_id not in (None, "", "null"):
        try:
            payload["message_type"] = MessageType.objects.get(pk=int(message_type_id))
        except (ValueError, MessageType.DoesNotExist):
            errors.append("Указан несуществующий тип сообщения")

    payload["shipper_holding"] = (data.get("shipper_holding") or "").strip()
    payload["shipper"] = (data.get("shipper") or "").strip()
    payload["route_code"] = (data.get("route_code") or "").strip()

    def _parse_int_field(field_name: str) -> int | None:
        raw = data.get(field_name)
        if raw in (None, "", "null"):
            return None
        try:
            return int(str(raw).replace(" ", ""))
        except (TypeError, ValueError):
            errors.append(f"Поле \"{field_name}\" должно быть целым числом")
            return None

    def _parse_decimal_field(field_name: str) -> tuple[Decimal | None, None]:
        from decimal import Decimal, InvalidOperation

        raw = data.get(field_name)
        if raw in (None, "", "null"):
            return None, None
        try:
            value = Decimal(str(raw).replace(" ", "").replace(",", "."))
            return value, None
        except (InvalidOperation, TypeError, ValueError):
            return None, f'Поле "{field_name}" должно быть числом'

    int_fields = [
        "distance_loaded_km",
        "distance_empty_km",
        "delivery_time_loaded_days",
        "delivery_time_empty_days",
        "delivery_time_ops_days",
    ]
    for name in int_fields:
        value = _parse_int_field(name)
        if value is not None:
            payload[name] = value

    decimal_fields = [
        "load_tons_per_wagon",
        "rate_per_wagon_per_day",
        "rzd_cost_loaded_per_ton",
        "rzd_cost_empty_per_ton",
        "rzd_cost_total_per_ton",
        "operators_cost_per_ton",
        "transshipment_cost_per_ton",
        "excise_or_duty_per_ton",
        "transport_total_cost_per_ton",
        "production_cost_per_ton",
        "total_cost_per_ton",
        "market_price_per_ton",
    ]
    for name in decimal_fields:
        value, err = _parse_decimal_field(name)
        if err:
            errors.append(err)
        if value is not None:
            payload[name] = value

    return payload, errors


def _route_to_dict(route: Route) -> dict:
    return {
        "id": route.id,
        "route_set_id": route.route_set_id,
        "route_set_code": route.route_set.code if route.route_set_id else "",
        "route_code": route.route_code,
        "cargo_code": route.cargo.code if route.cargo_id else None,
        "cargo_name": route.cargo.name if route.cargo_id else "",
        "origin_esr_code": route.origin_station.esr_code
        if route.origin_station_id
        else None,
        "origin_station_name": route.origin_station.full_name
        if route.origin_station_id
        else "",
        "destination_esr_code": route.destination_station.esr_code
        if route.destination_station_id
        else None,
        "destination_station_name": route.destination_station.full_name
        if route.destination_station_id
        else "",
        "origin_railroad_code": route.origin_station.railroad.code
        if route.origin_station_id and route.origin_station.railroad_id
        else "",
        "origin_region_full_name": route.origin_station.region.full_name
        if route.origin_station_id and route.origin_station.region_id
        else "",
        "origin_railroad_name": route.origin_station.railroad.name
        if route.origin_station_id and route.origin_station.railroad_id
        else "",
        "origin_railroad_direction": route.origin_station.railroad.direction
        if route.origin_station_id and route.origin_station.railroad_id
        else "",
        "destination_railroad_code": route.destination_station.railroad.code
        if route.destination_station_id and route.destination_station.railroad_id
        else "",
        "destination_region_full_name": route.destination_station.region.full_name
        if route.destination_station_id and route.destination_station.region_id
        else "",
        "destination_railroad_name": route.destination_station.railroad.name
        if route.destination_station_id and route.destination_station.railroad_id
        else "",
        "destination_railroad_direction": route.destination_station.railroad.direction
        if route.destination_station_id and route.destination_station.railroad_id
        else "",
        "wagon_kind_id": route.wagon_kind_id,
        "wagon_kind_name": route.wagon_kind.name if route.wagon_kind_id else "",
        "shipment_type_id": route.shipment_type_id,
        "shipment_type_name": route.shipment_type.name
        if route.shipment_type_id
        else "",
        "message_type_id": route.message_type_id,
        "message_type_name": route.message_type.name if route.message_type_id else "",
        "shipper_holding": route.shipper_holding,
        "shipper": route.shipper,
        "distance_loaded_km": route.distance_loaded_km,
        "distance_empty_km": route.distance_empty_km,
        "load_tons_per_wagon": str(route.load_tons_per_wagon)
        if route.load_tons_per_wagon is not None
        else None,
        "delivery_time_loaded_days": route.delivery_time_loaded_days,
        "delivery_time_empty_days": route.delivery_time_empty_days,
        "delivery_time_ops_days": route.delivery_time_ops_days,
        "rate_per_wagon_per_day": str(route.rate_per_wagon_per_day)
        if route.rate_per_wagon_per_day is not None
        else None,
        "rzd_cost_loaded_per_ton": str(route.rzd_cost_loaded_per_ton)
        if route.rzd_cost_loaded_per_ton is not None
        else None,
        "rzd_cost_empty_per_ton": str(route.rzd_cost_empty_per_ton)
        if route.rzd_cost_empty_per_ton is not None
        else None,
        "rzd_cost_total_per_ton": str(route.rzd_cost_total_per_ton)
        if route.rzd_cost_total_per_ton is not None
        else None,
        "operators_cost_per_ton": str(route.operators_cost_per_ton)
        if route.operators_cost_per_ton is not None
        else None,
        "transshipment_cost_per_ton": str(route.transshipment_cost_per_ton)
        if route.transshipment_cost_per_ton is not None
        else None,
        "excise_or_duty_per_ton": str(route.excise_or_duty_per_ton)
        if route.excise_or_duty_per_ton is not None
        else None,
        "transport_total_cost_per_ton": str(route.transport_total_cost_per_ton)
        if route.transport_total_cost_per_ton is not None
        else None,
        "production_cost_per_ton": str(route.production_cost_per_ton)
        if route.production_cost_per_ton is not None
        else None,
        "total_cost_per_ton": str(route.total_cost_per_ton)
        if route.total_cost_per_ton is not None
        else None,
        "market_price_per_ton": str(route.market_price_per_ton)
        if route.market_price_per_ton is not None
        else None,
    }


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

    if not route_set_id:
        return JsonResponse(
            {"success": False, "errors": ["Не указан набор маршрутов"]},
            status=400,
        )

    qs = Route.objects.select_related(
        "route_set",
        "cargo",
        "origin_station",
        "destination_station",
        "origin_station__railroad",
        "destination_station__railroad",
        "wagon_kind",
        "shipment_type",
        "message_type",
    ).filter(route_set_id=route_set_id)

    search = request.GET.get("search") or ""
    if search:
        search = search.strip()
        if search:
            s = search.casefold()
            q = Q(cargo__name__icontains=search) | Q(
                origin_station__short_name_search__contains=s
            ) | Q(origin_station__full_name_search__contains=s) | Q(
                destination_station__short_name_search__contains=s
            ) | Q(
                destination_station__full_name_search__contains=s
            ) | Q(
                route_code__icontains=search
            ) | Q(
                message_type__name_search__contains=s
            )
            if search.isdigit():
                try:
                    esr = int(search)
                    q = (
                        Q(origin_station__esr_code=esr)
                        | Q(destination_station__esr_code=esr)
                        | q
                    )
                except ValueError:
                    pass
            qs = qs.filter(q)

    origin_esr = request.GET.get("origin_esr")
    if origin_esr:
        try:
            qs = qs.filter(origin_station__esr_code=int(origin_esr))
        except (TypeError, ValueError):
            return JsonResponse(
                {
                    "success": False,
                    "errors": ["Код ЕСР станции отправления должен быть целым числом"],
                },
                status=400,
            )

    destination_esr = request.GET.get("destination_esr")
    if destination_esr:
        try:
            qs = qs.filter(destination_station__esr_code=int(destination_esr))
        except (TypeError, ValueError):
            return JsonResponse(
                {
                    "success": False,
                    "errors": ["Код ЕСР станции назначения должен быть целым числом"],
                },
                status=400,
            )

    paginator = Paginator(qs.order_by("id"), page_size)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    items = [_route_to_dict(route) for route in page_obj.object_list]

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
def route_detail_api(request, pk: int):
    try:
        route = Route.objects.select_related(
            "route_set",
            "cargo",
            "origin_station",
            "destination_station",
            "origin_station__railroad",
            "destination_station__railroad",
            "wagon_kind",
            "shipment_type",
            "message_type",
        ).get(pk=pk)
    except Route.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Маршрут не найден"]},
            status=404,
        )

    return JsonResponse({"success": True, "item": _route_to_dict(route)})


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

    payload, errors = _get_route_payload_errors(data)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    try:
        route = Route.objects.create(**payload)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse(
            {
                "success": False,
                "errors": [f"Не удалось создать маршрут: {exc}"],
            },
            status=400,
        )

    return JsonResponse(
        {
            "success": True,
            "item": _route_to_dict(route),
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def route_update_api(request, pk: int):
    try:
        route = Route.objects.get(pk=pk)
    except Route.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Маршрут не найден"]},
            status=404,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "errors": ["Неверный формат JSON"]},
            status=400,
        )

    payload, errors = _get_route_payload_errors(data)
    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    for field, value in payload.items():
        setattr(route, field, value)

    try:
        route.save()
    except Exception as exc:  # noqa: BLE001
        return JsonResponse(
            {
                "success": False,
                "errors": [f"Не удалось сохранить маршрут: {exc}"],
            },
            status=400,
        )

    return JsonResponse({"success": True, "item": _route_to_dict(route)})


@login_required
@require_http_methods(["POST"])
def route_delete_api(request, pk: int):
    try:
        route = Route.objects.get(pk=pk)
    except Route.DoesNotExist:
        return JsonResponse(
            {"success": False, "errors": ["Маршрут не найден"]},
            status=404,
        )

    route.delete()
    return JsonResponse({"success": True})

