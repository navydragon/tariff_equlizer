from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django import forms

from .models import (
    User,
    Setting,
    CargoGroup,
    Cargo,
    RailRoad,
    Region,
    Station,
    WagonKind,
    ShipmentType,
    MessageType,
    Shipper,
    RouteSet,
    Route,
)


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Подтверждение пароля", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("login", "last_name", "first_name", "middle_name", "email", "is_staff", "is_superuser")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Пароли не совпадают")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Пароль")

    class Meta:
        model = User
        fields = (
            "login",
            "password",
            "last_name",
            "first_name",
            "middle_name",
            "email",
            "active_scenario",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )

    def clean_password(self):
        return self.initial.get("password")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    form = UserChangeForm
    add_form = UserCreationForm
    list_display = ("login", "last_name", "first_name", "email", "active_scenario", "is_staff")
    search_fields = ("login", "last_name", "first_name", "email")
    ordering = ("login",)
    readonly_fields = ("last_login", "date_joined")

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


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("code", "value", "description")
    search_fields = ("code", "description", "value")
    ordering = ("code",)


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


@admin.register(Shipper)
class ShipperAdmin(admin.ModelAdmin):
    list_display = ("name", "holding", "inn", "okpo")
    ordering = ("name",)
    search_fields = ("name", "holding", "inn")
    list_filter = ("holding",)


@admin.register(RouteSet)
class RouteSetAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "created_at", "updated_at")
    search_fields = ("code", "name")
    ordering = ("name",)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    # На больших таблицах админка обычно тормозит из-за полного COUNT(*) и
    # построения списков значений для связанных list_filter.
    show_full_result_count = False
    list_per_page = 50
    ordering = ("route_set", "id")
    list_display = (
        "route_set",
        "route_code",
        "cargo",
        "origin_station",
        "destination_station",
        "transport_volume_tons",
        "freight_turnover_tkm",
        "freight_charge_rub",
    )
    list_select_related = (
        "route_set",
        "cargo",
        "origin_station",
        "destination_station",
        "wagon_kind",
        "shipment_type",
        "message_type",
        "shipper",
    )
    list_filter = (
        "route_set",
        "is_model",
        # Остальные связанные фильтры (cargo/станции/и т.д.) на больших объёмах
        # резко замедляют рендер списка — их лучше искать через search/autocomplete.
        "shipment_category",
        "park_type",
    )
    autocomplete_fields = (
        "route_set",
        "cargo",
        "origin_station",
        "destination_station",
        "wagon_kind",
        "shipment_type",
        "message_type",
        "shipper",
        "model_route",
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
