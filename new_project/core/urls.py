from django.urls import path
from django.views.generic import RedirectView

from . import views


urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("home/", views.home, name="home"),
    path("dashboard-1/", views.dashboard_1, name="dashboard_1"),
    path(
        "decision-effects/",
        views.decision_effects,
        name="decision_effects",
    ),
    path(
        "effects-cube/",
        views.effects_cube,
        name="effects_cube",
    ),
    path(
        "cube/",
        RedirectView.as_view(pattern_name="effects_cube", permanent=True),
        name="effects_cube_legacy",
    ),
    path(
        "dashboard-2/",
        RedirectView.as_view(pattern_name="decision_effects", permanent=True),
        name="dashboard_2",
    ),
    path("route-analysis/", views.route_analysis, name="route_analysis"),
    path("hello/", views.hello_partial, name="hello_partial"),
    # Справочники
    path("references/", views.references_view, name="references"),
    path("references/routes/", views.routes_list_view, name="routes_list"),
    path("references/cargos/", views.cargo_list_view, name="cargo_list"),
    path("references/railroads/", views.railroad_list_view, name="railroad_list"),
    path("references/regions/", views.region_list_view, name="region_list"),
    path("references/stations/", views.station_list_view, name="station_list"),
    path("references/wagon-kinds/", views.wagon_kind_list_view, name="wagon_kind_list"),
    path("references/shipment-types/", views.shipment_type_list_view, name="shipment_type_list"),
    path("references/message-types/", views.message_type_list_view, name="message_type_list"),
    path("references/shippers/", views.shipper_list_view, name="shipper_list"),
    # API для грузов
    path(
        "references/api/cargos/",
        views.cargo_list_api,
        name="cargo_list_api",
    ),
    path(
        "references/api/cargos/<int:code>/",
        views.cargo_detail_api,
        name="cargo_detail_api",
    ),
    path(
        "references/api/cargos/create/",
        views.cargo_create_api,
        name="cargo_create_api",
    ),
    path(
        "references/api/cargos/<int:code>/update/",
        views.cargo_update_api,
        name="cargo_update_api",
    ),
    path(
        "references/api/cargos/<int:code>/delete/",
        views.cargo_delete_api,
        name="cargo_delete_api",
    ),
    # API для железных дорог
    path(
        "references/api/railroads/",
        views.railroad_list_api,
        name="railroad_list_api",
    ),
    path(
        "references/api/railroads/<str:code>/",
        views.railroad_detail_api,
        name="railroad_detail_api",
    ),
    path(
        "references/api/railroads/create/",
        views.railroad_create_api,
        name="railroad_create_api",
    ),
    path(
        "references/api/railroads/<str:code>/update/",
        views.railroad_update_api,
        name="railroad_update_api",
    ),
    path(
        "references/api/railroads/<str:code>/delete/",
        views.railroad_delete_api,
        name="railroad_delete_api",
    ),
    # API для регионов
    path(
        "references/api/regions/",
        views.region_list_api,
        name="region_list_api",
    ),
    path(
        "references/api/regions/<int:pk>/",
        views.region_detail_api,
        name="region_detail_api",
    ),
    path(
        "references/api/regions/create/",
        views.region_create_api,
        name="region_create_api",
    ),
    path(
        "references/api/regions/<int:pk>/update/",
        views.region_update_api,
        name="region_update_api",
    ),
    path(
        "references/api/regions/<int:pk>/delete/",
        views.region_delete_api,
        name="region_delete_api",
    ),
    # API для станций
    path(
        "references/api/stations/",
        views.station_list_api,
        name="station_list_api",
    ),
    path(
        "references/api/stations/<int:esr_code>/",
        views.station_detail_api,
        name="station_detail_api",
    ),
    path(
        "references/api/stations/create/",
        views.station_create_api,
        name="station_create_api",
    ),
    path(
        "references/api/stations/<int:esr_code>/update/",
        views.station_update_api,
        name="station_update_api",
    ),
    path(
        "references/api/stations/<int:esr_code>/delete/",
        views.station_delete_api,
        name="station_delete_api",
    ),
    # API: род вагона
    path(
        "references/api/wagon-kinds/",
        views.wagon_kind_list_api,
        name="wagon_kind_list_api",
    ),
    path(
        "references/api/wagon-kinds/<int:pk>/",
        views.wagon_kind_detail_api,
        name="wagon_kind_detail_api",
    ),
    path(
        "references/api/wagon-kinds/create/",
        views.wagon_kind_create_api,
        name="wagon_kind_create_api",
    ),
    path(
        "references/api/wagon-kinds/<int:pk>/update/",
        views.wagon_kind_update_api,
        name="wagon_kind_update_api",
    ),
    path(
        "references/api/wagon-kinds/<int:pk>/delete/",
        views.wagon_kind_delete_api,
        name="wagon_kind_delete_api",
    ),
    # API: тип отправки
    path(
        "references/api/shipment-types/",
        views.shipment_type_list_api,
        name="shipment_type_list_api",
    ),
    path(
        "references/api/shipment-types/<int:pk>/",
        views.shipment_type_detail_api,
        name="shipment_type_detail_api",
    ),
    path(
        "references/api/shipment-types/create/",
        views.shipment_type_create_api,
        name="shipment_type_create_api",
    ),
    path(
        "references/api/shipment-types/<int:pk>/update/",
        views.shipment_type_update_api,
        name="shipment_type_update_api",
    ),
    path(
        "references/api/shipment-types/<int:pk>/delete/",
        views.shipment_type_delete_api,
        name="shipment_type_delete_api",
    ),
    # API: вид сообщения
    path(
        "references/api/message-types/",
        views.message_type_list_api,
        name="message_type_list_api",
    ),
    path(
        "references/api/message-types/<int:pk>/",
        views.message_type_detail_api,
        name="message_type_detail_api",
    ),
    path(
        "references/api/message-types/create/",
        views.message_type_create_api,
        name="message_type_create_api",
    ),
    path(
        "references/api/message-types/<int:pk>/update/",
        views.message_type_update_api,
        name="message_type_update_api",
    ),
    path(
        "references/api/message-types/<int:pk>/delete/",
        views.message_type_delete_api,
        name="message_type_delete_api",
    ),
    # API: наборы маршрутов и маршруты
    path(
        "references/api/route-sets/",
        views.route_set_list_api,
        name="route_set_list_api",
    ),
    path(
        "references/api/route-sets/<int:pk>/",
        views.route_set_detail_api,
        name="route_set_detail_api",
    ),
    path(
        "references/api/route-sets/create/",
        views.route_set_create_api,
        name="route_set_create_api",
    ),
    path(
        "references/api/route-sets/<int:pk>/update/",
        views.route_set_update_api,
        name="route_set_update_api",
    ),
    path(
        "references/api/route-sets/<int:pk>/delete/",
        views.route_set_delete_api,
        name="route_set_delete_api",
    ),
    path(
        "references/api/shippers/",
        views.shipper_list_api,
        name="shipper_list_api",
    ),
    path(
        "references/api/shippers/<int:pk>/",
        views.shipper_detail_api,
        name="shipper_detail_api",
    ),
    path(
        "references/api/shippers/create/",
        views.shipper_create_api,
        name="shipper_create_api",
    ),
    path(
        "references/api/shippers/<int:pk>/update/",
        views.shipper_update_api,
        name="shipper_update_api",
    ),
    path(
        "references/api/shippers/<int:pk>/delete/",
        views.shipper_delete_api,
        name="shipper_delete_api",
    ),
    path(
        "references/api/routes/",
        views.route_list_api,
        name="route_list_api",
    ),
    path(
        "references/api/routes/<int:pk>/",
        views.route_detail_api,
        name="route_detail_api",
    ),
    path(
        "references/api/routes/create/",
        views.route_create_api,
        name="route_create_api",
    ),
    path(
        "references/api/routes/<int:pk>/update/",
        views.route_update_api,
        name="route_update_api",
    ),
    path(
        "references/api/routes/<int:pk>/delete/",
        views.route_delete_api,
        name="route_delete_api",
    ),
    path(
        "analysis/api/route-analysis/",
        views.route_analysis_api,
        name="route_analysis_api",
    ),
]


