from decimal import Decimal
from typing import Optional

from django.db.models import Count

from scenarios.models import ElasticityRule, ElasticityRulePoint, ElasticitySet


class ElasticitySetRepository:
    """Репозиторий наборов эластичности."""

    def get_by_id(self, elasticity_set_id: int) -> Optional[ElasticitySet]:
        try:
            return ElasticitySet.objects.select_related("author").get(
                id=elasticity_set_id,
            )
        except ElasticitySet.DoesNotExist:
            return None

    def list_by_author(self, user) -> list[ElasticitySet]:
        return list(
            ElasticitySet.objects.filter(author=user).order_by(
                "-updated_at", "-created_at", "id",
            ),
        )

    def list_all(self) -> list[ElasticitySet]:
        return list(
            ElasticitySet.objects.select_related("author").order_by(
                "-updated_at", "-created_at", "id",
            ),
        )

    def create(self, data: dict) -> ElasticitySet:
        elasticity_set = ElasticitySet.objects.create(**data)
        return ElasticitySet.objects.select_related("author").get(
            id=elasticity_set.id,
        )

    def delete(self, elasticity_set_id: int) -> bool:
        deleted, _ = ElasticitySet.objects.filter(id=elasticity_set_id).delete()
        return deleted > 0


class ElasticityRuleRepository:
    """Репозиторий правил эластичности."""

    def list_by_set(self, elasticity_set_id: int) -> list[ElasticityRule]:
        return list(
            ElasticityRule.objects.filter(elasticity_set_id=elasticity_set_id)
            .select_related("cargo_group", "cargo", "message_type")
            .annotate(_points_count=Count("points"))
            .order_by("position", "id"),
        )

    def get_by_id(self, rule_id: int) -> Optional[ElasticityRule]:
        try:
            return (
                ElasticityRule.objects.select_related(
                    "elasticity_set",
                    "cargo_group",
                    "cargo",
                    "message_type",
                )
                .prefetch_related("points")
                .get(id=rule_id)
            )
        except ElasticityRule.DoesNotExist:
            return None

    def create(self, data: dict) -> ElasticityRule:
        rule = ElasticityRule.objects.create(**data)
        return self.get_by_id(rule.id)

    def update(self, rule_id: int, data: dict) -> Optional[ElasticityRule]:
        try:
            rule = ElasticityRule.objects.get(id=rule_id)
        except ElasticityRule.DoesNotExist:
            return None

        for key, value in data.items():
            setattr(rule, key, value)
        rule.save()
        return self.get_by_id(rule.id)

    def delete(self, rule_id: int) -> bool:
        try:
            ElasticityRule.objects.get(id=rule_id).delete()
            return True
        except ElasticityRule.DoesNotExist:
            return False

    def replace_points(self, rule: ElasticityRule, points: list[dict]) -> None:
        ElasticityRulePoint.objects.filter(rule=rule).delete()
        if not points:
            return
        ElasticityRulePoint.objects.bulk_create(
            [
                ElasticityRulePoint(
                    rule=rule,
                    marginality=point["marginality"],
                    coefficient=point["coefficient"],
                )
                for point in points
            ],
        )


class ElasticityRulePointRepository:
    """Репозиторий точек кривой эластичности."""

    def list_by_rule(self, rule_id: int) -> list[ElasticityRulePoint]:
        return list(
            ElasticityRulePoint.objects.filter(rule_id=rule_id).order_by(
                "marginality",
                "id",
            ),
        )

    def get_by_marginality(
        self,
        rule_id: int,
        marginality: Decimal,
    ) -> Optional[ElasticityRulePoint]:
        return ElasticityRulePoint.objects.filter(
            rule_id=rule_id,
            marginality=marginality,
        ).first()

    def find_floor_point(
        self,
        rule_id: int,
        marginality: Decimal,
    ) -> Optional[ElasticityRulePoint]:
        return (
            ElasticityRulePoint.objects.filter(
                rule_id=rule_id,
                marginality__lte=marginality,
            )
            .order_by("-marginality", "-id")
            .first()
        )

    def find_ceiling_point(
        self,
        rule_id: int,
        marginality: Decimal,
    ) -> Optional[ElasticityRulePoint]:
        return (
            ElasticityRulePoint.objects.filter(
                rule_id=rule_id,
                marginality__gte=marginality,
            )
            .order_by("marginality", "id")
            .first()
        )
