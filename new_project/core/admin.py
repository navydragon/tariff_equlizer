from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    User,
    CargoGroup,
    Cargo,
    RailRoad,
    Region,
    Station,
    WagonKind,
    ShipmentType,
    MessageType,
    RouteSet,
    Route,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("login", "last_name", "first_name", "email", "active_scenario", "is_staff")
    search_fields = ("login", "last_name", "first_name", "email")
    ordering = ("login",)

    fieldsets = (
        (None, {"fields": ("login", "password")}),
        ("Персональная информация", {"fields": ("last_name", "first_name", "middle_name", "email", "active_scenario")}),
        ("Права доступа", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Важные даты", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("login", "password1", "password2", "last_name", "first_name", "middle_name", "email", "is_staff", "is_superuser"),
        }),
    )


@admin.register(CargoGroup)
class CargoGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "position")
    ordering = ("position", "code")
    search_fields = ("name",)


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "cargo_group")
    ordering = ("code",)
    search_fields = ("code", "name")
    list_filter = ("cargo_group",)


@admin.register(RailRoad)
class RailRoadAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country", "direction")
    ordering = ("code",)
    search_fields = ("code", "name", "country", "direction")
    list_filter = ("country", "direction")


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("full_name", "short_name", "type")
    ordering = ("full_name", "type")
    search_fields = ("full_name", "short_name", "type")
    list_filter = ("type",)


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("esr_code", "short_name", "region", "railroad")
    ordering = ("esr_code",)
    search_fields = ("esr_code", "short_name", "full_name")
    list_filter = ("region", "railroad")


@admin.register(WagonKind)
class WagonKindAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "position", "is_active")
    ordering = ("position", "name")
    search_fields = ("name", "code")
    list_filter = ("is_active",)


@admin.register(ShipmentType)
class ShipmentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "position", "is_active")
    ordering = ("position", "name")
    search_fields = ("name", "code")
    list_filter = ("is_active",)


@admin.register(MessageType)
class MessageTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "position", "is_active")
    ordering = ("position", "name")
    search_fields = ("name", "code")
    list_filter = ("is_active",)


@admin.register(RouteSet)
class RouteSetAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "created_at", "updated_at")
    search_fields = ("code", "name")
    ordering = ("name",)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "route_set",
        "route_code",
        "cargo",
        "origin_station",
        "destination_station",
        "transport_volume_mln_tons",
        "freight_turnover_bln_tkm",
        "freight_charge_ths_rub",
    )
    list_filter = (
        "route_set",
        "cargo",
        "origin_station__railroad",
        "destination_station__railroad",
        "wagon_kind",
        "shipment_type",
    )
    search_fields = (
        "route_code",
        "cargo__name",
        "cargo__code",
        "origin_station__full_name",
        "origin_station__esr_code",
        "destination_station__full_name",
        "destination_station__esr_code",
    )
