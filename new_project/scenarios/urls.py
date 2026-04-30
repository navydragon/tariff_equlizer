"""
URL configuration for scenarios app.
"""
from django.urls import path
from . import views

app_name = "scenarios"

urlpatterns = [
    path("window/", views.scenario_window_view, name="window"),
    path("management/", views.scenario_management_view, name="management"),
    path("api/list/", views.scenario_list_api, name="api_list"),
    path("api/<int:scenario_id>/", views.scenario_detail_api, name="api_detail"),
    path("api/create/", views.scenario_create_api, name="api_create"),
    path("api/<int:scenario_id>/update/", views.scenario_update_api, name="api_update"),
    path("api/<int:scenario_id>/delete/", views.scenario_delete_api, name="api_delete"),
    path(
        "api/<int:scenario_id>/set-active/",
        views.scenario_set_active_api,
        name="api_set_active",
    ),
    path("create-modal/", views.scenario_create_modal_view, name="create_modal"),
    path(
        "edit-modal/<int:scenario_id>/",
        views.scenario_edit_modal_view,
        name="edit_modal",
    ),
    path("edit/<int:scenario_id>/", views.scenario_edit_view, name="edit"),

    # Tariff rules API
    path(
        "api/<int:scenario_id>/tariff-rules/",
        views.tariff_rule_list_api,
        name="tariff_rule_list",
    ),
    path(
        "api/<int:scenario_id>/tariff-rules/create/",
        views.tariff_rule_create_api,
        name="tariff_rule_create",
    ),
    path(
        "api/tariff-rules/<int:rule_id>/",
        views.tariff_rule_detail_api,
        name="tariff_rule_detail",
    ),
    path(
        "api/tariff-rules/<int:rule_id>/update/",
        views.tariff_rule_update_api,
        name="tariff_rule_update",
    ),
    path(
        "api/tariff-rules/<int:rule_id>/delete/",
        views.tariff_rule_delete_api,
        name="tariff_rule_delete",
    ),
    path(
        "api/<int:scenario_id>/tariff-rule-options/",
        views.tariff_rule_options_api,
        name="tariff_rule_options",
    ),
    path(
        "api/<int:scenario_id>/tariff-rule-stats/",
        views.tariff_rule_stats_api,
        name="tariff_rule_stats",
    ),

    # BTD categories API
    path(
        "api/<int:scenario_id>/btd-categories/",
        views.btd_category_list_api,
        name="btd_api_list",
    ),
    path(
        "api/<int:scenario_id>/btd-categories/create/",
        views.btd_category_create_api,
        name="btd_api_create",
    ),
    path(
        "api/btd-categories/<int:category_id>/update/",
        views.btd_category_update_api,
        name="btd_api_update",
    ),
    path(
        "api/btd-categories/<int:category_id>/delete/",
        views.btd_category_delete_api,
        name="btd_api_delete",
    ),
    path(
        "api/btd-categories/<int:category_id>/move/",
        views.btd_category_move_api,
        name="btd_api_move",
    ),

    # BTD values API
    path(
        "api/<int:scenario_id>/btd-values/matrix/",
        views.btd_values_matrix_api,
        name="btd_values_matrix",
    ),
    path(
        "api/btd-values/update/",
        views.btd_value_update_api,
        name="btd_value_update",
    ),

    # Exchange rates API
    path(
        "api/exchange-rate-sets/",
        views.exchange_rate_set_list_api,
        name="exchange_rate_set_list",
    ),
    path(
        "api/exchange-rate-sets/create/",
        views.exchange_rate_set_create_api,
        name="exchange_rate_set_create",
    ),
    path(
        "api/<int:scenario_id>/exchange-rate-sets/attach/",
        views.exchange_rate_set_attach_api,
        name="exchange_rate_set_attach",
    ),
    path(
        "api/<int:scenario_id>/exchange-rates/matrix/",
        views.exchange_rates_matrix_api,
        name="exchange_rates_matrix",
    ),
    path(
        "api/exchange-rates/update/",
        views.exchange_rate_value_update_api,
        name="exchange_rate_value_update",
    ),
]
