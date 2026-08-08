from core.models import CargoGroup, Route

cg = CargoGroup.objects.get(code=10)
target = 170_000.0

print("--- nearest singles to 0.17 mln t ---")
band = list(
    Route.objects.filter(
        is_model=False,
        cargo__cargo_group=cg,
        freight_charge_rub__gt=0,
        skip_elasticity=True,
        transport_volume_tons__gte=140_000,
        transport_volume_tons__lte=200_000,
    )
    .order_by("transport_volume_tons")
    .values(
        "id",
        "route_code",
        "transport_volume_tons",
        "message_type_id",
        "message_type__name",
        "origin_station__railroad__direction",
        "cargo_id",
        "origin_station_id",
        "freight_charge_rub",
    )
)

ranked = sorted(band, key=lambda r: abs(float(r["transport_volume_tons"]) - target))
for row in ranked[:20]:
    v = float(row["transport_volume_tons"])
    print(
        "id=%s code=%s vol=%.0f (%.4f mln) delta=%.0f dir=%r mt=%s:%s cargo=%s charge_mln=%.1f"
        % (
            row["id"],
            row["route_code"],
            v,
            v / 1e6,
            v - target,
            row["origin_station__railroad__direction"],
            row["message_type_id"],
            row["message_type__name"],
            row["cargo_id"],
            float(row["freight_charge_rub"] or 0) / 1e6,
        )
    )

print("--- exact-ish 165k..175k ---")
for row in band:
    v = float(row["transport_volume_tons"])
    if 165_000 <= v <= 175_000:
        print(
            "id=%s code=%s vol=%.0f (%.4f mln) dir=%r mt=%s:%s"
            % (
                row["id"],
                row["route_code"],
                v,
                v / 1e6,
                row["origin_station__railroad__direction"],
                row["message_type_id"],
                row["message_type__name"],
            )
        )
