from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import F

from core.models import User
from scenarios.domain.dto import (
    BTDCategoryDTO,
    BTDCategoryValueDTO,
    CreateBTDCategoryDTO,
    UpdateBTDCategoryDTO,
    UpdateBTDCategoryValueDTO,
)
from scenarios.domain.repositories import (
    BTDCategoryRepository,
    BTDCategoryValueRepository,
    ScenarioRepository,
)
from scenarios.domain.services.btd_coefficients import compute_total_coefficient_by_year
from scenarios.models import BTDCategory, BTDCategoryValue


ERR_CATEGORY_NOT_FOUND = "Категория не найдена"


class BTDCategoryService:
    """Сервис для работы с категориями базовых тарифных решений (BTDCategory)."""

    def __init__(self):
        self.repository = BTDCategoryRepository()
        self.scenario_repository = ScenarioRepository()

    def _validate_scenario_access(self, scenario_id: int, user: User):
        scenario = self.scenario_repository.get_by_id(scenario_id)
        if not scenario:
            return None, ["Сценарий не найден"]
        if scenario.author != user:
            return None, ["Нет прав на изменение этого сценария"]
        return scenario, []

    def list_categories(
        self, scenario_id: int, user: User
    ) -> tuple[list[BTDCategoryDTO], list[str]]:
        scenario, errors = self._validate_scenario_access(scenario_id, user)
        if errors:
            return [], errors

        categories = self.repository.list_by_scenario(scenario.id)
        return [BTDCategoryDTO.from_model(c) for c in categories], []

    @transaction.atomic
    def create_category(
        self, dto: CreateBTDCategoryDTO, user: User
    ) -> tuple[Optional[BTDCategoryDTO], list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        scenario, errors = self._validate_scenario_access(
            dto.scenario_id, user
        )
        if errors:
            return None, errors

        data: dict = {"name": dto.name, "scenario": scenario}

        if dto.position is not None:
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
        category = self.repository.get_by_id(category_id)
        if not category:
            return None, [ERR_CATEGORY_NOT_FOUND]

        scenario, errors = self._validate_scenario_access(
            category.scenario_id, user
        )
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

            temp_position = max_pos + 1000
            if new_position < old_position:
                self.repository.update(category_id, {"position": temp_position})
                BTDCategory.objects.filter(
                    scenario=scenario,
                    position__gte=new_position,
                    position__lt=old_position,
                ).update(position=F("position") + 1)
                update_data["position"] = new_position
            elif new_position > old_position:
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

    @transaction.atomic
    def delete_category(
        self, category_id: int, user: User
    ) -> tuple[bool, list[str]]:
        category = self.repository.get_by_id(category_id)
        if not category:
            return False, [ERR_CATEGORY_NOT_FOUND]

        scenario, errors = self._validate_scenario_access(
            category.scenario_id, user
        )
        if errors:
            return False, errors

        deleted_position = category.position
        scenario_id = scenario.id

        success = self.repository.delete(category_id)
        if not success:
            return False, ["Ошибка при удалении категории"]

        self.repository.shift_positions_after_delete(scenario_id, deleted_position)
        return True, []

    def move_category(
        self, category_id: int, direction: str, user: User
    ) -> tuple[Optional[list[BTDCategoryDTO]], list[str]]:
        category = self.repository.get_by_id(category_id)
        if not category:
            return None, [ERR_CATEGORY_NOT_FOUND]

        scenario, errors = self._validate_scenario_access(
            category.scenario_id, user
        )
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

    def get_matrix(self, scenario_id: int, user: User) -> tuple[dict, list[str]]:
        scenario, errors = self._validate_scenario_access(scenario_id, user)
        if errors:
            return {}, errors

        years = list(range(scenario.start_year, scenario.end_year + 1))
        categories = list(self.category_repository.list_by_scenario(scenario_id))
        values = list(self.value_repository.list_by_scenario(scenario_id))

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

        total_coefficient = compute_total_coefficient_by_year(
            years, categories, value_map
        )

        return {
            "years": years,
            "categories": categories_payload,
            "total_coefficient": total_coefficient,
        }, []

    @transaction.atomic
    def update_value(
        self, dto: UpdateBTDCategoryValueDTO, user: User
    ) -> tuple[Optional[BTDCategoryValueDTO], list[str]]:
        basic_errors = dto.validate_basic()
        if basic_errors:
            return None, basic_errors

        scenario, errors = self._validate_scenario_access(dto.scenario_id, user)
        if errors:
            return None, errors

        if not (scenario.start_year <= dto.year <= scenario.end_year):
            return None, [
                "Год должен быть в пределах сценария "
                f"{scenario.start_year}-{scenario.end_year}"
            ]

        category = self.category_repository.get_by_id(dto.category_id)
        if not category:
            return None, [ERR_CATEGORY_NOT_FOUND]
        if category.scenario_id != scenario.id:
            return None, ["Категория не относится к указанному сценарию"]

        try:
            value_obj = BTDCategoryValue(
                scenario=scenario,
                category=category,
                year=dto.year,
                value=dto.value,
            )
            value_obj.full_clean(exclude=["scenario", "category", "year"])
        except Exception:
            return None, ["Некорректный формат значения"]

        saved = self.value_repository.upsert({
            "scenario": scenario,
            "category": category,
            "year": dto.year,
            "value": value_obj.value,
        })
        return BTDCategoryValueDTO.from_model(saved), []
