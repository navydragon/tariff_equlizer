from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from core.domain.cargo.formatting import normalize_optional_izpod_cargo_code
from core.models import Route


@dataclass(frozen=True)
class RecomputeCargoIzpodResult:
    scanned: int = 0
    updated: int = 0
    cleared_invalid: int = 0


def recompute_route_cargo_izpod_codes(
    *,
    route_set_id: int,
    dry_run: bool = False,
    batch_size: int = 2000,
) -> RecomputeCargoIzpodResult:
    """Пересчитать cargo_code_izpod / cargo_code_izpod_3 из сырого из-под.

    Обрабатывает маршруты с непустым из-под кодом или 3-значным полем
    (в т.ч. мусорные значения вроде «0»).
    """
    qs = (
        Route.objects.filter(route_set_id=route_set_id)
        .filter(~Q(cargo_code_izpod="") | ~Q(cargo_code_izpod_3=""))
        .only("id", "cargo_code_izpod", "cargo_code_izpod_3")
        .order_by("id")
    )

    scanned = 0
    updated = 0
    cleared_invalid = 0
    pending: list[Route] = []

    def flush() -> None:
        nonlocal pending
        if not pending or dry_run:
            pending = []
            return
        Route.objects.bulk_update(
            pending,
            ["cargo_code_izpod", "cargo_code_izpod_3"],
            batch_size=batch_size,
        )
        pending = []

    for route in qs.iterator(chunk_size=batch_size):
        scanned += 1
        raw_before = (route.cargo_code_izpod or "").strip()
        izpod_code, izpod_3, _warnings = normalize_optional_izpod_cargo_code(
            route.cargo_code_izpod,
        )
        if (
            izpod_code == (route.cargo_code_izpod or "")
            and izpod_3 == (route.cargo_code_izpod_3 or "")
        ):
            continue

        if raw_before and not izpod_code:
            cleared_invalid += 1

        route.cargo_code_izpod = izpod_code
        route.cargo_code_izpod_3 = izpod_3
        updated += 1
        pending.append(route)
        if len(pending) >= batch_size:
            flush()

    flush()
    return RecomputeCargoIzpodResult(
        scanned=scanned,
        updated=updated,
        cleared_invalid=cleared_invalid,
    )
