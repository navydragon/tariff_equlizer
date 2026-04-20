from django.db import models
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin


class UserManager(BaseUserManager):
    def create_user(self, login, password=None, **extra_fields):
        if not login:
            raise ValueError("Логин должен быть указан")
        login = self.model.normalize_username(login)
        email = extra_fields.get("email")
        if email:
            email = self.normalize_email(email)
            extra_fields["email"] = email
        user = self.model(login=login, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(login, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    last_name = models.CharField("Фамилия", max_length=150)
    first_name = models.CharField("Имя", max_length=150)
    middle_name = models.CharField("Отчество", max_length=150, blank=True)
    login = models.CharField("Логин", max_length=150, unique=True)
    email = models.EmailField("Email", blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    active_scenario = models.ForeignKey(
        "scenarios.Scenario",
        verbose_name="Активный сценарий",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_users",
    )

    objects = UserManager()

    USERNAME_FIELD = "login"
    REQUIRED_FIELDS = ["email", "first_name", "last_name"]

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self) -> str:
        return self.login


class CargoGroup(models.Model):
    code = models.PositiveSmallIntegerField("Код", primary_key=True)
    name = models.CharField("Название", max_length=255)
    position = models.PositiveIntegerField("Позиция")

    class Meta:
        verbose_name = "Группа груза"
        verbose_name_plural = "Группы груза"
        ordering = ["position", "code"]

    def __str__(self) -> str:
        return self.name


class Cargo(models.Model):
    code = models.PositiveIntegerField("Код ETSNG", primary_key=True)
    name = models.CharField("Наименование", max_length=255)
    cargo_group = models.ForeignKey(
        CargoGroup,
        verbose_name="Группа груза",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cargos",
    )

    class Meta:
        verbose_name = "Груз (ETSNG)"
        verbose_name_plural = "Грузы (ETSNG)"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class RailRoad(models.Model):
    code = models.CharField("Код", max_length=4, primary_key=True)
    name = models.CharField("Название", max_length=255)
    country = models.CharField("Страна", max_length=100, blank=True)
    direction = models.CharField("Направление", max_length=50, blank=True)

    class Meta:
        verbose_name = "Железная дорога"
        verbose_name_plural = "Железные дороги"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Region(models.Model):
    short_name = models.CharField("Краткое название", max_length=100)
    full_name = models.CharField("Полное название", max_length=255)
    type = models.CharField("Тип региона", max_length=50)
    short_name_search = models.CharField(
        max_length=100,
        editable=False,
        default="",
        db_index=True,
    )
    full_name_search = models.CharField(
        max_length=255,
        editable=False,
        default="",
        db_index=True,
    )
    type_search = models.CharField(
        max_length=50,
        editable=False,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Регион"
        verbose_name_plural = "Регионы"
        ordering = ["full_name", "type"]
        constraints = [
            models.UniqueConstraint(
                fields=["full_name", "type"],
                name="uniq_region_full_name_type",
            )
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.type})"

    def save(self, *args, **kwargs):
        self.short_name_search = (self.short_name or "").casefold()
        self.full_name_search = (self.full_name or "").casefold()
        self.type_search = (self.type or "").casefold()
        return super().save(*args, **kwargs)


class Station(models.Model):
    esr_code = models.PositiveIntegerField("Код ЕСР", primary_key=True)
    short_name = models.CharField("Краткое название", max_length=150)
    full_name = models.CharField("Полное название", max_length=255)
    short_name_search = models.CharField(
        max_length=150,
        editable=False,
        default="",
        db_index=True,
    )
    full_name_search = models.CharField(
        max_length=255,
        editable=False,
        default="",
        db_index=True,
    )
    region = models.ForeignKey(
        Region,
        verbose_name="Регион",
        on_delete=models.PROTECT,
        related_name="stations",
    )
    railroad = models.ForeignKey(
        RailRoad,
        verbose_name="Железная дорога",
        on_delete=models.PROTECT,
        related_name="stations",
    )

    class Meta:
        verbose_name = "Станция"
        verbose_name_plural = "Станции"
        ordering = ["esr_code"]
        indexes = [
            models.Index(fields=["short_name"], name="station_short_name_idx"),
            models.Index(fields=["railroad"], name="station_railroad_idx"),
            models.Index(fields=["region"], name="station_region_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.esr_code} — {self.full_name}"

    def save(self, *args, **kwargs):
        self.short_name_search = (self.short_name or "").casefold()
        self.full_name_search = (self.full_name or "").casefold()
        return super().save(*args, **kwargs)


class WagonKind(models.Model):
    code = models.CharField("Код", max_length=20, blank=True, default="")
    name = models.CharField("Название", max_length=255, unique=True)
    position = models.PositiveIntegerField("Позиция", default=0)
    is_active = models.BooleanField("Активен", default=True)
    name_search = models.CharField(
        max_length=255,
        editable=False,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Род вагона"
        verbose_name_plural = "Роды вагонов"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=~models.Q(code=""),
                name="uniq_wagonkind_code_nonempty",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name_search = (self.name or "").casefold()
        self.code = (self.code or "").strip()
        return super().save(*args, **kwargs)


class ShipmentType(models.Model):
    code = models.CharField("Код", max_length=20, blank=True, default="")
    name = models.CharField("Название", max_length=255, unique=True)
    position = models.PositiveIntegerField("Позиция", default=0)
    is_active = models.BooleanField("Активен", default=True)
    name_search = models.CharField(
        max_length=255,
        editable=False,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Тип отправки"
        verbose_name_plural = "Типы отправки"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=~models.Q(code=""),
                name="uniq_shipmenttype_code_nonempty",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name_search = (self.name or "").casefold()
        self.code = (self.code or "").strip()
        return super().save(*args, **kwargs)


class MessageType(models.Model):
    code = models.CharField("Код", max_length=20, blank=True, default="")
    name = models.CharField("Название", max_length=255, unique=True)
    position = models.PositiveIntegerField("Позиция", default=0)
    is_active = models.BooleanField("Активен", default=True)
    name_search = models.CharField(
        max_length=255,
        editable=False,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Тип сообщения"
        verbose_name_plural = "Типы сообщения"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=~models.Q(code=""),
                name="uniq_messagetype_code_nonempty",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name_search = (self.name or "").casefold()
        self.code = (self.code or "").strip()
        return super().save(*args, **kwargs)


class RouteSet(models.Model):
    name = models.CharField("Название набора", max_length=255, unique=True)
    code = models.CharField("Код набора", max_length=100, unique=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        verbose_name = "Набор маршрутов"
        verbose_name_plural = "Наборы маршрутов"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Route(models.Model):
    route_set = models.ForeignKey(
        RouteSet,
        verbose_name="Набор маршрутов",
        on_delete=models.CASCADE,
        related_name="routes",
    )
    cargo = models.ForeignKey(
        Cargo,
        verbose_name="Груз",
        on_delete=models.PROTECT,
        related_name="routes",
    )
    origin_station = models.ForeignKey(
        Station,
        verbose_name="Станция отправления",
        on_delete=models.PROTECT,
        related_name="origin_routes",
    )
    destination_station = models.ForeignKey(
        Station,
        verbose_name="Станция назначения",
        on_delete=models.PROTECT,
        related_name="destination_routes",
    )
    wagon_kind = models.ForeignKey(
        WagonKind,
        verbose_name="Род вагона",
        on_delete=models.PROTECT,
        related_name="routes",
    )
    shipment_type = models.ForeignKey(
        ShipmentType,
        verbose_name="Тип отправки",
        on_delete=models.PROTECT,
        related_name="routes",
    )
    message_type = models.ForeignKey(
        MessageType,
        verbose_name="Тип сообщения",
        on_delete=models.PROTECT,
        related_name="routes",
        null=True,
        blank=True,
    )

    shipper_holding = models.CharField(
        "Холдинг грузоотправителя",
        max_length=255,
        blank=True,
    )
    shipper = models.CharField(
        "Грузоотправитель",
        max_length=255,
        blank=True,
    )
    route_code = models.CharField(
        "Ключевой код маршрута",
        max_length=50,
        blank=True,
        db_index=True,
    )

    distance_loaded_km = models.PositiveIntegerField(
        "Расстояние гружёный рейс, км",
        null=True,
        blank=True,
    )
    distance_empty_km = models.PositiveIntegerField(
        "Расстояние порожний рейс, км",
        null=True,
        blank=True,
    )
    load_tons_per_wagon = models.DecimalField(
        "Загрузка в вагон, т",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    delivery_time_loaded_days = models.PositiveIntegerField(
        "Срок доставки гружёный рейс, сут",
        null=True,
        blank=True,
    )
    delivery_time_empty_days = models.PositiveIntegerField(
        "Срок доставки порожний рейс, сут",
        null=True,
        blank=True,
    )
    delivery_time_ops_days = models.PositiveIntegerField(
        "Срок доставки погр./выгр., сут",
        null=True,
        blank=True,
    )
    rate_per_wagon_per_day = models.DecimalField(
        "Ставка на вагон, руб./вагон/сут",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    rzd_cost_loaded_per_ton = models.DecimalField(
        'Расходы РЖД, гружёный пробег, руб./т',
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    rzd_cost_empty_per_ton = models.DecimalField(
        'Расходы РЖД, порожний пробег, руб./т',
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    rzd_cost_total_per_ton = models.DecimalField(
        'Расходы РЖД, итого, руб./т',
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    operators_cost_per_ton = models.DecimalField(
        "Расходы операторов, руб./т",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    transshipment_cost_per_ton = models.DecimalField(
        "Расходы на перевалку, руб./т",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    excise_or_duty_per_ton = models.DecimalField(
        "Акциз/пошлина, руб./т",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    transport_total_cost_per_ton = models.DecimalField(
        "Общие транспортные расходы, руб./т",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    production_cost_per_ton = models.DecimalField(
        "Себестоимость добычи/производства, руб./т",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    total_cost_per_ton = models.DecimalField(
        "Общие расходы, руб./т",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    market_price_per_ton = models.DecimalField(
        "Рыночная цена, руб./т",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Маршрут"
        verbose_name_plural = "Маршруты"
        ordering = ["route_set", "route_code", "id"]
        indexes = [
            models.Index(fields=["route_set", "route_code"], name="route_set_code_idx"),
            models.Index(fields=["cargo"], name="route_cargo_idx"),
            models.Index(
                fields=["origin_station", "destination_station"],
                name="route_stations_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["route_set", "route_code"],
                name="uniq_route_set_route_code",
            )
        ]

    def __str__(self) -> str:
        return f"{self.route_set.code if self.route_set_id else '-'} / {self.route_code or self.id}"
