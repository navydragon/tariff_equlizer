from dataclasses import dataclass
from typing import Optional


@dataclass
class ElasticitySetDTO:
    id: int
    name: str
    author_id: int
    author_name: str

    @classmethod
    def from_model(cls, elasticity_set):
        return cls(
            id=elasticity_set.id,
            name=elasticity_set.name,
            author_id=elasticity_set.author_id,
            author_name=str(elasticity_set.author),
        )


@dataclass
class ElasticityRulePointDTO:
    id: int | None
    marginality: str
    coefficient: str

    @classmethod
    def from_model(cls, point):
        return cls(
            id=point.id,
            marginality=str(point.marginality),
            coefficient=str(point.coefficient),
        )


@dataclass
class ElasticityRuleDTO:
    id: int
    elasticity_set_id: int
    name: str
    position: int
    cargo_group_id: int | None
    cargo_group_name: str
    cargo_id: str | None
    cargo_name: str
    message_type_id: int | None
    message_type_name: str
    points_count: int
    points: list[ElasticityRulePointDTO]

    @classmethod
    def from_model(cls, rule, *, include_points: bool = False):
        if include_points:
            all_points = list(rule.points.all())
        else:
            all_points = []
        annotated_count = getattr(rule, "_points_count", None)
        if annotated_count is not None:
            points_count = int(annotated_count)
        else:
            points_count = len(all_points) if include_points else rule.points.count()
        return cls(
            id=rule.id,
            elasticity_set_id=rule.elasticity_set_id,
            name=rule.name,
            position=rule.position,
            cargo_group_id=rule.cargo_group_id,
            cargo_group_name=str(rule.cargo_group) if rule.cargo_group_id else "",
            cargo_id=rule.cargo_id,
            cargo_name=str(rule.cargo) if rule.cargo_id else "",
            message_type_id=rule.message_type_id,
            message_type_name=str(rule.message_type) if rule.message_type_id else "",
            points_count=points_count,
            points=[
                ElasticityRulePointDTO.from_model(point)
                for point in all_points
            ],
        )


@dataclass
class CreateElasticityRuleDTO:
    elasticity_set_id: int
    name: str
    position: Optional[int] = None
    cargo_group_id: Optional[int] = None
    cargo_id: Optional[str] = None
    message_type_id: Optional[int] = None
    points: Optional[list[dict]] = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name or not self.name.strip():
            errors.append("Название правила обязательно")
        if self.position is not None and self.position < 0:
            errors.append("Позиция указана некорректно")
        return errors


@dataclass
class UpdateElasticityRuleDTO:
    name: Optional[str] = None
    position: Optional[int] = None
    cargo_group_id: object = ...
    cargo_id: object = ...
    message_type_id: object = ...
    points: Optional[list[dict]] = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.name is not None and not self.name.strip():
            errors.append("Название правила не может быть пустым")
        if self.position is not None and self.position < 0:
            errors.append("Позиция указана некорректно")
        return errors
