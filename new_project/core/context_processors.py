from django.urls import reverse


def breadcrumbs(request):
    resolver_match = getattr(request, "resolver_match", None)
    view_name = resolver_match.view_name if resolver_match else None

    if not view_name:
        return {"breadcrumbs": []}

    home_title = "Главная"
    refs_title = "Справочники"
    home_url = reverse("home")
    refs_url = reverse("references")

    # Только полноценные страницы (без api/modals/partials).
    trail_map = {
        "home": [
            {"title": home_title, "url": None},
        ],
        "route_analysis": [
            {"title": home_title, "url": home_url},
            {"title": "Экономика грузов", "url": None},
        ],
        "dashboard_1": [
            {"title": home_title, "url": home_url},
            {"title": "Дашборд", "url": None},
        ],
        "decision_effects": [
            {"title": home_title, "url": home_url},
            {"title": "Эффект от решений", "url": None},
        ],
        "effects_cube": [
            {"title": home_title, "url": home_url},
            {"title": "Куб эффектов", "url": None},
        ],
        "route_analytics": [
            {"title": home_title, "url": home_url},
            {"title": "Аналитика маршрутов", "url": None},
        ],
        "effects_cube_legacy": [
            {"title": home_title, "url": home_url},
            {"title": "Куб эффектов", "url": None},
        ],
        "references": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": None},
        ],
        "routes_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Маршруты", "url": None},
        ],
        "cargo_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Грузы", "url": None},
        ],
        "railroad_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Железные дороги", "url": None},
        ],
        "region_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Регионы", "url": None},
        ],
        "station_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Станции", "url": None},
        ],
        "wagon_kind_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Роды вагонов", "url": None},
        ],
        "shipment_type_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Типы отправки", "url": None},
        ],
        "message_type_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Виды сообщения", "url": None},
        ],
        "shipper_list": [
            {"title": home_title, "url": home_url},
            {"title": refs_title, "url": refs_url},
            {"title": "Грузоотправители", "url": None},
        ],
        "scenarios:management": [
            {"title": home_title, "url": home_url},
            {"title": "Сценарии", "url": None},
            {"title": "Управление сценариями", "url": None},
        ],
        "scenarios:edit": [
            {"title": home_title, "url": home_url},
            {"title": "Сценарии", "url": reverse("scenarios:management")},
            {"title": "Редактирование сценария", "url": None},
        ],
        "support:task_list": [
            {"title": home_title, "url": home_url},
            {"title": "Управление задачами", "url": None},
        ],
        "support:task_detail": [
            {"title": home_title, "url": home_url},
            {"title": "Управление задачами", "url": reverse("support:task_list")},
            {"title": "Задача", "url": None},
        ],
    }

    return {"breadcrumbs": trail_map.get(view_name, [])}
