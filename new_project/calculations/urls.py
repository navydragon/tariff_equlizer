from django.urls import path

from calculations import views

app_name = "calculations"

urlpatterns = [
    path(
        "api/tariff-load/",
        views.tariff_load_api,
        name="tariff_load_api",
    ),
    path(
        "api/scenario-effects/compute/",
        views.scenario_effects_compute_api,
        name="scenario_effects_compute_api",
    ),
    path(
        "api/scenario-effects/compute-pandas/",
        views.scenario_effects_compute_pandas_api,
        name="scenario_effects_compute_pandas_api",
    ),
    path(
        "api/scenario-effects/aggregate/",
        views.scenario_effects_aggregate_api,
        name="scenario_effects_aggregate_api",
    ),
    path(
        "api/scenario-effects/",
        views.scenario_effects_api,
        name="scenario_effects_api",
    ),
    path(
        "api/scenario-absolute/revenues/",
        views.scenario_absolute_revenues_api,
        name="scenario_absolute_revenues_api",
    ),
    path(
        "api/scenario-absolute/volumes/",
        views.scenario_absolute_volumes_api,
        name="scenario_absolute_volumes_api",
    ),
    path(
        "api/scenario-absolute/revenues/export/",
        views.scenario_absolute_revenues_export_api,
        name="scenario_absolute_revenues_export_api",
    ),
    path(
        "api/scenario-absolute/volumes/export/",
        views.scenario_absolute_volumes_export_api,
        name="scenario_absolute_volumes_export_api",
    ),
    path(
        "api/scenario-effects/cube/",
        views.scenario_effects_cube_api,
        name="scenario_effects_cube_api",
    ),
    path(
        "api/scenario-effects/cube/export/",
        views.scenario_effects_cube_export_api,
        name="scenario_effects_cube_export_api",
    ),
]
