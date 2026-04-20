"""
Сервисы для бизнес-логики сценариев.
Реализуют бизнес-кейсы поверх репозиториев и DTO.
"""
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction
from django.db.models import F

from scenarios.domain.dto import (
    ScenarioDTO,
    CreateScenarioDTO,
    UpdateScenarioDTO,
    ScenarioListDTO,
    BTDCategoryDTO,
    CreateBTDCategoryDTO,
    UpdateBTDCategoryDTO,
    BTDCategoryValueDTO,
    UpdateBTDCategoryValueDTO,
    TariffRuleDTO,
    CreateTariffRuleDTO,
    UpdateTariffRuleDTO,
)
from scenarios.domain.repositories import (
    ScenarioRepository,
    BTDCategoryRepository,
    BTDCategoryValueRepository,
    TariffRuleRepository,
)
from core.models import User, RouteSet
from scenarios.models import BTDCategory, BTDCategoryValue


class ScenarioService:
    """Сервис для работы со сценариями."""

    def __init__(self):
        self.repository = ScenarioRepository()

    def get_user_scenarios(self) -> list[ScenarioListDTO]:
        """
        Получить доступные сценарии для пользователя.
        Возвращает все сценарии.
        """
        all_scenarios = self.repository.get_all()

        return [
            ScenarioListDTO.from_model(scenario)
            for scenario in all_scenarios
        ]

    def get_scenario(self, scenario_id: int) -> Optional[ScenarioDTO]:
        """
        Получить сценарий с проверкой доступа.
        Пока все сценарии доступны всем пользователям.
        """
        scenario = self.repository.get_by_id(scenario_id)
        if not scenario:
            return None
        return ScenarioDTO.from_model(scenario)

    @transaction.atomic
    def create_scenario(
        self, dto: CreateScenarioDTO, user: User
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        """
        Создать сценарий с нуля.
        Возвращает (сценарий, список ошибок).
        
        ВНИМАНИЕ: Этот метод предназначен только для внутреннего использования
        (например, для создания первого базового сценария через management команды).
        Для обычного создания сценариев через API используйте create_scenario_from_base.
        """
        errors = dto.validate()
        if errors:
            return None, errors

        # Создание с нуля
        scenario = self.repository.create({
            "name": dto.name,
            "description": dto.description,
            "start_year": dto.start_year,
            "end_year": dto.end_year,
            "author": user,
        })
        return ScenarioDTO.from_model(scenario), []

    @transaction.atomic
    def create_scenario_from_base(
        self, dto: CreateScenarioDTO, user: User
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        """
        Создать сценарий на базе существующего.
        Копирует все данные из базового сценария.
        Возвращает (сценарий, список ошибок).
        
        В будущем здесь можно будет добавлять параметры копирования:
        - какие данные копировать
        - какие параметры переопределить
        - и т.д.
        """
        if not dto.base_scenario_id:
            return None, ["Не указан базовый сценарий"]

        errors = dto.validate()
        if errors:
            return None, errors

        # Копируем сценарий через репозиторий
        scenario = self.repository.copy_scenario(
            source_id=dto.base_scenario_id,
            new_name=dto.name,
            new_author=user,
        )
        if not scenario:
            return None, ["Исходный сценарий не найден"]

        # Обновляем название, описание и годы из DTO (если они указаны)
        update_data = {}
        if dto.name:
            update_data["name"] = dto.name
        if dto.description is not None:
            update_data["description"] = dto.description
        if dto.start_year is not None:
            update_data["start_year"] = dto.start_year
        if dto.end_year is not None:
            update_data["end_year"] = dto.end_year

        if update_data:
            updated_scenario = self.repository.update(scenario.id, update_data)
            if updated_scenario:
                scenario = updated_scenario

        return ScenarioDTO.from_model(scenario), []

    def update_scenario(
        self, scenario_id: int, dto: UpdateScenarioDTO, user: User
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        """
        Обновить сценарий.
        Возвращает (обновленный сценарий, список ошибок).
        """
        scenario = self.repository.get_by_id(scenario_id)
        if not scenario:
            return None, ["Сценарий не найден"]

        # Проверка прав: только автор может редактировать
        if scenario.author != user:
            return None, ["Нет прав на редактирование этого сценария"]

        errors = dto.validate()
        if errors:
            return None, errors

        update_data = {}
        if dto.name is not None:
            update_data["name"] = dto.name
        if dto.description is not None:
            update_data["description"] = dto.description
        if dto.start_year is not None:
            update_data["start_year"] = dto.start_year
        if dto.end_year is not None:
            update_data["end_year"] = dto.end_year
        if dto.route_set_id is not None:
            try:
                route_set = RouteSet.objects.get(id=dto.route_set_id)
            except RouteSet.DoesNotExist:
                return None, ["Набор маршрутов не найден"]
            update_data["route_set"] = route_set

        updated_scenario = self.repository.update(scenario_id, update_data)
        if not updated_scenario:
            return None, ["Ошибка при обновлении сценария"]

        return ScenarioDTO.from_model(updated_scenario), []

    def delete_scenario(self, scenario_id: int, user: User) -> tuple[bool, list[str]]:
        """
        Удалить сценарий.
        Возвращает (успех, список ошибок).
        """
        scenario = self.repository.get_by_id(scenario_id)
        if not scenario:
            return False, ["Сценарий не найден"]

        # Проверка прав: только автор может удалять
        if scenario.author != user:
            return False, ["Нет прав на удаление этого сценария"]

        # Нельзя удалять активный сценарий пользователя
        if user.active_scenario_id == scenario_id:
            return False, ["Нельзя удалить активный сценарий. Сначала выберите другой активный сценарий."]

        success = self.repository.delete(scenario_id)
        if not success:
            return False, ["Ошибка при удалении сценария"]

        return True, []

    def set_active_scenario(
        self, user: User, scenario_id: Optional[int]
    ) -> tuple[bool, list[str]]:
        """
        Установить активный сценарий для пользователя.

        Если scenario_id is None, активный сценарий снимается.
        """
        if scenario_id is not None:
            scenario = self.repository.get_by_id(scenario_id)
            if not scenario:
                return False, ["Сценарий не найден"]

        user.active_scenario_id = scenario_id
        user.save(update_fields=["active_scenario"])
        return True, []


class BTDCategoryService:
    """Сервис для работы с категориями базовых тарифных решений (BTDCategory)."""

    def __init__(self):
        self.repository = BTDCategoryRepository()
        self.scenario_repository = ScenarioRepository()

    def _validate_scenario_access(self, scenario_id: int, user: User):
        scenario = self.scenario_repository.get_by_id(scenario_id)
        if not scenario:
            return None, ["Сценарий не найден"]
        # Право редактировать имеет только автор сценария
        if scenario.author != user:
            return None, ["Нет прав на изменение этого сценария"]
        return scenario, []

    def list_categories(
        self, scenario_id: int, user: User
    ) -> tuple[list[BTDCategoryDTO], list[str]]:
        """
        Получить список категорий для сценария.
        Используется на странице редактирования сценария.
        """
        scenario, errors = self._validate_scenario_access(scenario_id, user)
        if errors:
            return [], errors

        categories = self.repository.list_by_scenario(scenario.id)
        return [BTDCategoryDTO.from_model(c) for c in categories], []

    @transaction.atomic
    def create_category(
        self, dto: CreateBTDCategoryDTO, user: User
    ) -> tuple[Optional[BTDCategoryDTO], list[str]]:
        """Создать категорию BTD для указанного сценария."""
        errors = dto.validate()
        if errors:
            return None, errors

        scenario, errors = self._validate_scenario_access(dto.scenario_id, user)
        if errors:
            return None, errors

        data: dict = {
            "name": dto.name,
            "scenario": scenario,
        }

        # Если позиция указана, вставляем с сдвигом остальных вниз
        if dto.position is not None:
            # Сдвигаем все категории с позицией >= новой
            BTDCategory.objects.filter(
                scenario=scenario,
                position__gte=dto.position,
            ).update(position=F("position") + 1)
            data["position"] = dto.position

        category = self.repository.create(data)
        return BTDCategoryDTO.from_model(category), []

    @transaction.atomic
    def update_category(
        self, category_id: int, dto: UpdateBTDCategoryDTO, user: User
    ) -> tuple[Optional[BTDCategoryDTO], list[str]]:
        """Обновить категорию BTD."""
        category = self.repository.get_by_id(category_id)
        if not category:
            return None, ["Категория не найдена"]

        # Проверка прав по сценарию
        scenario, errors = self._validate_scenario_access(category.scenario_id, user)
        if errors:
            return None, errors

        errors = dto.validate()
        if errors:
            return None, errors

        update_data: dict = {}

        if dto.name is not None:
            update_data["name"] = dto.name

        # При изменении позиции пересчитываем порядок в рамках сценария.
        # UNIQUE(scenario_id, position) — нельзя bulk-update без временной позиции.
        if dto.position is not None and dto.position != category.position:
            old_position = category.position

            max_pos = (
                BTDCategory.objects.filter(scenario=scenario)
                .order_by("-position")
                .values_list("position", flat=True)
                .first()
            )
            if not max_pos:
                max_pos = 1
            new_position = max(1, min(dto.position, max_pos))

            # Временная позиция вне диапазона, чтобы не нарушить UNIQUE
            temp_position = max_pos + 1000

            if new_position < old_position:
                # Поднять: сначала освобождаем нашу позицию, сдвигаем соседа, ставим себя
                self.repository.update(category_id, {"position": temp_position})
                BTDCategory.objects.filter(
                    scenario=scenario,
                    position__gte=new_position,
                    position__lt=old_position,
                ).update(position=F("position") + 1)
                update_data["position"] = new_position
            elif new_position > old_position:
                # Опустить: сначала освобождаем нашу позицию, сдвигаем соседа, ставим себя
                self.repository.update(category_id, {"position": temp_position})
                BTDCategory.objects.filter(
                    scenario=scenario,
                    position__gt=old_position,
                    position__lte=new_position,
                ).update(position=F("position") - 1)
                update_data["position"] = new_position

        updated = self.repository.update(category_id, update_data)
        if not updated:
            return None, ["Ошибка при обновлении категории"]

        return BTDCategoryDTO.from_model(updated), []


class TariffRuleService:
    def __init__(self):
        self.repository = TariffRuleRepository()
        self.scenario_repository = ScenarioRepository()

    def _validate_scenario_access(self, scenario_id: int, user: User):
        scenario = self.scenario_repository.get_by_id(scenario_id)
        if not scenario:
            return None, ["Сценарий не найден"]
        if scenario.author != user:
            return None, ["Нет прав на изменение этого сценария"]
        return scenario, []

    def list_rules(self, scenario_id: int, user: User) -> tuple[list[TariffRuleDTO], list[str]]:
        _scenario, errors = self._validate_scenario_access(scenario_id, user)
        if errors:
            return [], errors
        rules = self.repository.list_by_scenario(scenario_id)
        return [TariffRuleDTO.from_model(r) for r in rules], []

    def get_rule(self, rule_id: int, user: User) -> tuple[Optional[TariffRuleDTO], list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return None, ["Тарифное решение не найдено"]
        _scenario, errors = self._validate_scenario_access(rule.scenario_id, user)
        if errors:
            return None, errors
        return TariffRuleDTO.from_model(rule), []

    @transaction.atomic
    def create_rule(
        self, dto: CreateTariffRuleDTO, user: User
    ) -> tuple[Optional[TariffRuleDTO], list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        scenario, errors = self._validate_scenario_access(dto.scenario_id, user)
        if errors:
            return None, errors

        base_percent = dto.base_percent if dto.base_percent is not None else "100"
        try:
            base_percent_dec = Decimal(str(base_percent))
        except (InvalidOperation, TypeError):
            return None, ["% покрытия базы указан некорректно"]
        if base_percent_dec < 0 or base_percent_dec > 200:
            return None, ["% покрытия базы должен быть в диапазоне 0–200"]

        position = int(dto.position) if dto.position is not None else 0

        rule = self.repository.create(
            {
                "scenario": scenario,
                "name": dto.name.strip(),
                "base_percent": base_percent_dec,
                "position": position,
            }
        )
        if dto.conditions is not None:
            self.repository.replace_conditions(rule, dto.conditions)
        if dto.year_values is not None:
            self._upsert_year_values_checked(rule, dto.year_values, scenario.start_year, scenario.end_year)

        rule = self.repository.get_by_id(rule.id)
        return TariffRuleDTO.from_model(rule), []

    @transaction.atomic
    def update_rule(
        self, rule_id: int, dto: UpdateTariffRuleDTO, user: User
    ) -> tuple[Optional[TariffRuleDTO], list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return None, ["Тарифное решение не найдено"]

        scenario, errors = self._validate_scenario_access(rule.scenario_id, user)
        if errors:
            return None, errors

        errors = dto.validate()
        if errors:
            return None, errors

        update_data: dict = {}
        if dto.name is not None:
            update_data["name"] = dto.name.strip()
        if dto.position is not None:
            update_data["position"] = int(dto.position)
        if dto.base_percent is not None:
            try:
                base_percent_dec = Decimal(str(dto.base_percent))
            except (InvalidOperation, TypeError):
                return None, ["% покрытия базы указан некорректно"]
            if base_percent_dec < 0 or base_percent_dec > 200:
                return None, ["% покрытия базы должен быть в диапазоне 0–200"]
            update_data["base_percent"] = base_percent_dec

        updated = self.repository.update(rule_id, update_data) if update_data else rule
        if not updated:
            return None, ["Ошибка при обновлении тарифного решения"]

        if dto.conditions is not None:
            self.repository.replace_conditions(updated, dto.conditions)
        if dto.year_values is not None:
            self._upsert_year_values_checked(updated, dto.year_values, scenario.start_year, scenario.end_year)

        refreshed = self.repository.get_by_id(rule_id)
        return TariffRuleDTO.from_model(refreshed), []

    def delete_rule(self, rule_id: int, user: User) -> tuple[bool, list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return False, ["Тарифное решение не найдено"]
        _scenario, errors = self._validate_scenario_access(rule.scenario_id, user)
        if errors:
            return False, errors
        ok = self.repository.delete(rule_id)
        return (True, []) if ok else (False, ["Ошибка при удалении тарифного решения"])

    def _upsert_year_values_checked(self, rule, year_values: dict, start_year: int, end_year: int) -> None:
        cleaned: dict = {}
        for year_str, coef in (year_values or {}).items():
            try:
                year = int(year_str)
            except (TypeError, ValueError):
                continue
            if year < start_year or year > end_year:
                continue
            try:
                coef_dec = Decimal(str(coef))
            except (InvalidOperation, TypeError):
                continue
            cleaned[str(year)] = coef_dec
        self.repository.upsert_year_values(rule, cleaned)

    @transaction.atomic
    def delete_category(
        self, category_id: int, user: User
    ) -> tuple[bool, list[str]]:
        """Удалить категорию BTD с пересчетом позиций."""
        category = self.repository.get_by_id(category_id)
        if not category:
            return False, ["Категория не найдена"]

        scenario, errors = self._validate_scenario_access(category.scenario_id, user)
        if errors:
            return False, errors

        deleted_position = category.position
        scenario_id = scenario.id

        success = self.repository.delete(category_id)
        if not success:
            return False, ["Ошибка при удалении категории"]

        # Сдвигаем позиции следующих категорий
        self.repository.shift_positions_after_delete(scenario_id, deleted_position)

        return True, []

    def move_category(
        self, category_id: int, direction: str, user: User
    ) -> tuple[Optional[list[BTDCategoryDTO]], list[str]]:
        """
        Поднять выше (direction='up') или опустить ниже (direction='down').
        Меняет позицию с соседним элементом.
        Возвращает (обновлённый список категорий, ошибки).
        """
        category = self.repository.get_by_id(category_id)
        if not category:
            return None, ["Категория не найдена"]

        scenario, errors = self._validate_scenario_access(category.scenario_id, user)
        if errors:
            return None, errors

        categories = list(self.repository.list_by_scenario(scenario.id))
        max_pos = max((c.position for c in categories), default=1)

        if direction == "up":
            new_position = category.position - 1
            if new_position < 1:
                return None, ["Уже на первой позиции"]
        elif direction == "down":
            new_position = category.position + 1
            if new_position > max_pos:
                return None, ["Уже на последней позиции"]
        else:
            return None, ["Неверное направление: up или down"]

        dto = UpdateBTDCategoryDTO(name=None, position=new_position)
        _, errs = self.update_category(category_id, dto, user)
        if errs:
            return None, errs

        updated = self.repository.list_by_scenario(scenario.id)
        return [BTDCategoryDTO.from_model(c) for c in updated], []

    def set_active_scenario(self, user: User, scenario_id: Optional[int]) -> tuple[bool, list[str]]:
        """
        Установить активный сценарий для пользователя.
        Если scenario_id=None, снимает активный сценарий.
        Возвращает (успех, список ошибок).
        """
        if scenario_id is not None:
            scenario = self.repository.get_by_id(scenario_id)
            if not scenario:
                return False, ["Сценарий не найден"]

        # Обновляем активный сценарий пользователя
        user.active_scenario_id = scenario_id
        user.save(update_fields=["active_scenario"])

        return True, []


class BTDCategoryValueService:
    """Сервис для работы со значениями категорий BTD по годам сценария."""

    def __init__(self):
        self.scenario_repository = ScenarioRepository()
        self.category_repository = BTDCategoryRepository()
        self.value_repository = BTDCategoryValueRepository()

    def _validate_scenario_access(self, scenario_id: int, user: User):
        scenario = self.scenario_repository.get_by_id(scenario_id)
        if not scenario:
            return None, ["Сценарий не найден"]
        if scenario.author != user:
            return None, ["Нет прав на изменение этого сценария"]
        return scenario, []

    def _compute_total_coefficient(
        self,
        years: list[int],
        categories: list[BTDCategory],
        value_map: dict[tuple[int, int], str],
    ) -> dict[str, str]:
        """
        Рассчитывает строку «Итоговый коэффициент» по годам.

        Для первого года возвращает пустое значение.
        Для последующих лет:
        - берем значение первой категории в текущем году;
        - последовательно умножаем на отношение значений остальных категорий:
          value(year_i) / value(year_{i-1});
        - если какое-либо значение отсутствует, не парсится в Decimal
          или знаменатель равен нулю — возвращаем пустую строку для этого года.
        """
        if not years or not categories:
            return {}

        result: dict[str, str] = {}

        # Первый год всегда пустой
        first_year = years[0]
        result[str(first_year)] = ""

        if len(years) == 1:
            return result

        first_category = categories[0]

        for index in range(1, len(years)):
            year = years[index]
            prev_year = years[index - 1]

            base_key = (first_category.id, year)
            base_value_str = value_map.get(base_key)
            if base_value_str is None:
                result[str(year)] = ""
                continue

            try:
                accumulator = Decimal(base_value_str)
            except InvalidOperation:
                result[str(year)] = ""
                continue

            invalid = False

            for category in categories[1:]:
                num_str = value_map.get((category.id, year))
                denom_str = value_map.get((category.id, prev_year))

                if num_str is None or denom_str is None:
                    invalid = True
                    break

                try:
                    numerator = Decimal(num_str)
                    denominator = Decimal(denom_str)
                except InvalidOperation:
                    invalid = True
                    break

                if denominator == 0:
                    invalid = True
                    break

                accumulator *= numerator / denominator

            if invalid:
                result[str(year)] = ""
            else:
                # Округляем до 4 знаков после запятой, как в DecimalField.
                try:
                    quantized = accumulator.quantize(Decimal("0.0001"))
                except InvalidOperation:
                    result[str(year)] = ""
                else:
                    result[str(year)] = str(quantized)

        return result

    def get_matrix(self, scenario_id: int, user: User) -> tuple[dict, list[str]]:
        """
        Получить матрицу значений: годы + категории с их значениями по годам.
        Структура:
        {
            "years": [2025, 2026, ...],
            "categories": [
                {"id": ..., "name": ..., "position": ..., "values": {"2025": "1.076", ...}},
                ...
            ]
        }
        """
        scenario, errors = self._validate_scenario_access(scenario_id, user)
        if errors:
            return {}, errors

        years = list(range(scenario.start_year, scenario.end_year + 1))

        categories = list(self.category_repository.list_by_scenario(scenario_id))
        values = list(self.value_repository.list_by_scenario(scenario_id))

        # Индексируем значения по (category_id, year)
        value_map: dict[tuple[int, int], str] = {}
        for v in values:
            value_map[(v.category_id, v.year)] = str(v.value)

        categories_payload: list[dict] = []
        for c in categories:
            cat_values: dict[str, str] = {}
            for y in years:
                key = (c.id, y)
                if key in value_map:
                    cat_values[str(y)] = value_map[key]
            categories_payload.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "position": c.position,
                    "values": cat_values,
                }
            )

        total_coefficient = self._compute_total_coefficient(years, categories, value_map)

        return {
            "years": years,
            "categories": categories_payload,
            "total_coefficient": total_coefficient,
        }, []

    @transaction.atomic
    def update_value(
        self,
        dto: UpdateBTDCategoryValueDTO,
        user: User,
    ) -> tuple[Optional[BTDCategoryValueDTO], list[str]]:
        """Создать или обновить значение для (scenario, category, year)."""
        basic_errors = dto.validate_basic()
        if basic_errors:
            return None, basic_errors

        scenario, errors = self._validate_scenario_access(dto.scenario_id, user)
        if errors:
            return None, errors

        # Проверяем, что год в диапазоне сценария
        if not (scenario.start_year <= dto.year <= scenario.end_year):
            return None, [
                "Год должен быть в пределах сценария "
                f"{scenario.start_year}-{scenario.end_year}"
            ]

        category = self.category_repository.get_by_id(dto.category_id)
        if not category:
            return None, ["Категория не найдена"]
        if category.scenario_id != scenario.id:
            return None, ["Категория не относится к указанному сценарию"]

        # Пробуем привести значение к Decimal через модель
        try:
            value_obj = BTDCategoryValue(
                scenario=scenario,
                category=category,
                year=dto.year,
                value=dto.value,
            )
            # Вызов full_clean, чтобы дать Django провалидировать DecimalField
            value_obj.full_clean(exclude=["scenario", "category", "year"])
        except Exception:
            return None, ["Некорректный формат значения"]

        data = {
            "scenario": scenario,
            "category": category,
            "year": dto.year,
            "value": value_obj.value,
        }
        saved = self.value_repository.upsert(data)
        return BTDCategoryValueDTO.from_model(saved), []
