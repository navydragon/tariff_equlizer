from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from calculations.domain.services.route_mart_store import bump_route_mart_refs_version
from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Route,
    RouteSet,
    ShipmentType,
    Shipper,
    Station,
    WagonKind,
)


def _touch_route_set(route_set_id: int | None) -> None:
    if not route_set_id:
        return
    RouteSet.objects.filter(pk=route_set_id).update(updated_at=timezone.now())


@receiver(post_save, sender=Route)
def route_mart_touch_routeset_on_save(sender, instance: Route, **kwargs) -> None:  # noqa: ARG001
    _touch_route_set(instance.route_set_id)


@receiver(post_delete, sender=Route)
def route_mart_touch_routeset_on_delete(sender, instance: Route, **kwargs) -> None:  # noqa: ARG001
    _touch_route_set(instance.route_set_id)


def _bump_refs_on_commit() -> None:
    transaction.on_commit(bump_route_mart_refs_version)


@receiver(post_save, sender=Cargo)
@receiver(post_delete, sender=Cargo)
@receiver(post_save, sender=CargoGroup)
@receiver(post_delete, sender=CargoGroup)
@receiver(post_save, sender=Station)
@receiver(post_delete, sender=Station)
@receiver(post_save, sender=RailRoad)
@receiver(post_delete, sender=RailRoad)
@receiver(post_save, sender=WagonKind)
@receiver(post_delete, sender=WagonKind)
@receiver(post_save, sender=ShipmentType)
@receiver(post_delete, sender=ShipmentType)
@receiver(post_save, sender=MessageType)
@receiver(post_delete, sender=MessageType)
@receiver(post_save, sender=Shipper)
@receiver(post_delete, sender=Shipper)
def route_mart_bump_refs_version(sender, instance, **kwargs) -> None:  # noqa: ANN001,ARG001
    _bump_refs_on_commit()

