from django.db import models
from django.db.models import Q
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


class Setting(models.Model):
    code = models.CharField("Код", max_length=100, unique=True, db_index=True)
    description = models.TextField("Описание", blank=True)
    value = models.CharField("Значение", max_length=255)

    class Meta:
        verbose_name = "Настройка"
        verbose_name_plural = "Настройки"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code}={self.value}"


class CargoGroup(models.Model):
    code = models.PositiveSmallIntegerField("Код", primary_key=True)
    name = models.CharField("Название", max_length=255)
    position = models.PositiveIntegerField("Позиция")
    name_search = models.CharField(
        max_length=255,
        editable=False,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Группа груза"
        verbose_name_plural = "Группы груза"
        ordering = ["position", "code"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name_search = (self.name or "").casefold()
        return super().save(*args, **kwargs)


class Cargo(models.Model):
    code = models.CharField("Код ETSNG", max_length=6, primary_key=True)
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
        verbose_name = "Вид сообщения"
        verbose_name_plural = "Виды сообщения"
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


class Shipper(models.Model):
    okpo = models.BigIntegerField("ОКПО", null=True, blank=True)
    inn = models.CharField("ИНН", max_length=12, blank=True, default="")
    name = models.CharField("Грузоотправитель", max_length=255)
    holding = models.CharField(
        "Холдинг грузоотправителя",
        max_length=255,
        blank=True,
        default="",
    )
    name_search = models.CharField(
        max_length=255,
        editable=False,
        default="",
        db_index=True,
    )
    holding_search = models.CharField(
        max_length=255,
        editable=False,
        default="",
        db_index=True,
    )

    class Meta:
        verbose_name = "Грузоотправитель"
        verbose_name_plural = "Грузоотправители"
        ordering = ["name", "okpo"]
        constraints = [
            models.UniqueConstraint(
                fields=["okpo", "inn", "name"],
                name="uniq_shipper_okpo_inn_name",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.name_search = (self.name or "").casefold()
        self.holding_search = (self.holding or "").casefold()
        self.inn = (self.inn or "").strip()
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


class RouteQuerySet(models.QuerySet):
    def operational(self) -> "RouteQuerySet":
        return self.filter(is_model=False)

    def model_routes(self) -> "RouteQuerySet":
        return self.filter(is_model=True)


class RouteManager(models.Manager.from_queryset(RouteQuerySet)):
    pass


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
        verbose_name="Вид сообщения",
        on_delete=models.PROTECT,
        related_name="routes",
        null=True,
        blank=True,
    )

    shipper = models.ForeignKey(
        Shipper,
        verbose_name="Грузоотправитель",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="routes",
    )
    route_code = models.CharField(
        "Код маршрута (index в ИХ_ГП)",
        max_length=50,
        blank=True,
        db_index=True,
    )
    distance_belt = models.CharField(
        "Пояс дальности",
        max_length=50,
        blank=True,
        default="",
    )
    distance_belt_midpoint_km = models.PositiveIntegerField(
        "Середина пояса дальности, км",
        null=True,
        blank=True,
    )
    shipment_category = models.CharField(
        "Категория отправки",
        max_length=100,
        blank=True,
        default="",
    )
    park_type = models.CharField(
        "Тип парка",
        max_length=100,
        blank=True,
        default="",
    )
    special_container_type = models.CharField(
        "Вид спец. контейнера",
        max_length=255,
        blank=True,
        default="",
    )
    cargo_group_cmtp = models.CharField(
        "Группа груза ЦМТП",
        max_length=255,
        blank=True,
        default="",
    )
    cargo_code_izpod = models.CharField(
        "Код груза (изпод)",
        max_length=50,
        blank=True,
        default="",
    )
    cargo_group_izpod = models.CharField(
        "Группа груза (изпод)",
        max_length=255,
        blank=True,
        default="",
    )
    cargo_code_3 = models.CharField(
        "Код груза 3 знака",
        max_length=3,
        blank=True,
        default="",
    )
    cargo_code_izpod_3 = models.CharField(
        "Код груза из-под (3 знака)",
        max_length=3,
        blank=True,
        default="",
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
    transport_volume_tons = models.DecimalField(
        "Объём перевозок, т",
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )
    freight_turnover_tkm = models.DecimalField(
        "Грузооборот, т·км",
        max_digits=22,
        decimal_places=4,
        null=True,
        blank=True,
    )
    freight_charge_rub = models.DecimalField(
        "Провозная плата, руб.",
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
    )
    enterprise_load_coefficient = models.DecimalField(
        "Коэффициент загрузки предприятия",
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
    )
    turnover_change_coef_2025 = models.DecimalField(
        "Коэфф. изменения грузооборота 2025",
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    turnover_change_coef_2026 = models.DecimalField(
        "Коэфф. изменения грузооборота 2026",
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    turnover_change_coef_2027 = models.DecimalField(
        "Коэфф. изменения грузооборота 2027",
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    turnover_change_coef_2028 = models.DecimalField(
        "Коэфф. изменения грузооборота 2028",
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    turnover_change_coef_2029 = models.DecimalField(
        "Коэфф. изменения грузооборота 2029",
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    turnover_change_coef_2030 = models.DecimalField(
        "Коэфф. изменения грузооборота 2030",
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
    )
    is_model = models.BooleanField(
        "Модельный маршрут IPEM",
        default=False,
        db_index=True,
    )
    model_route = models.ForeignKey(
        "self",
        verbose_name="Модельный маршрут",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="linked_operational_routes",
    )

    class ElasticitySource(models.TextChoices):
        NONE = "none", "Не рассчитывается"
        DIRECT_MODEL = "direct_model", "Модельный маршрут"
        HOLDING_AGGREGATE = "holding_aggregate", "Среднее по холдингу"
        CARGO_GROUP_AGGREGATE = "cargo_group_aggregate", "Среднее по группе груза"

    skip_elasticity = models.BooleanField(
        "Не учитывать эластичность",
        default=True,
    )
    elasticity_source = models.CharField(
        "Источник эластичности",
        max_length=32,
        choices=ElasticitySource.choices,
        default=ElasticitySource.NONE,
    )

    objects = RouteManager()

    class Meta:
        verbose_name = "Маршрут"
        verbose_name_plural = "Маршруты"
        ordering = ["route_set", "route_code", "id"]
        indexes = [
            models.Index(fields=["route_set", "route_code"], name="route_set_code_idx"),
            models.Index(
                fields=["route_set", "freight_charge_rub"],
                name="route_set_charge_idx",
            ),
            models.Index(fields=["route_set", "id"], name="route_set_id_idx"),
            models.Index(
                fields=["route_set", "origin_station"],
                name="route_set_origin_idx",
            ),
            models.Index(
                fields=["route_set", "destination_station"],
                name="route_set_dest_idx",
            ),
            models.Index(fields=["cargo"], name="route_cargo_idx"),
            models.Index(
                fields=["origin_station", "destination_station"],
                name="route_stations_idx",
            ),
            models.Index(fields=["route_set", "shipper"], name="route_set_shipper_idx"),
            models.Index(
                fields=["route_set", "id"],
                name="route_set_economics_idx",
                condition=Q(market_price_per_ton__isnull=False),
            ),
            models.Index(fields=["route_set", "is_model"], name="route_set_is_model_idx"),
            models.Index(fields=["model_route"], name="route_model_route_idx"),
            models.Index(
                fields=[
                    "route_set",
                    "origin_station",
                    "destination_station",
                    "cargo",
                    "wagon_kind",
                    "shipment_type",
                ],
                name="route_operational_link_idx",
                condition=Q(is_model=False),
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["route_set", "route_code"],
                name="uniq_route_set_route_code",
            ),
            models.CheckConstraint(
                condition=Q(is_model=False) | Q(model_route__isnull=True),
                name="route_model_no_parent",
            ),
        ]

    def save(self, *args, **kwargs):
        from core.domain.distance_belt import sync_distance_belt_midpoint

        sync_distance_belt_midpoint(self)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "distance_belt" in update_fields:
            kwargs["update_fields"] = list(
                set(update_fields) | {"distance_belt_midpoint_km"},
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.route_set.code if self.route_set_id else '-'} / {self.route_code or self.id}"
