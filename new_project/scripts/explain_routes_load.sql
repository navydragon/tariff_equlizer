-- EXPLAIN для загрузки маршрутов (pandas compute).
-- Подставьте :route_set_id перед запуском в psql.
--
-- Пример:
--   \set route_set_id 1
--   \i explain_routes_load.sql

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    r.id,
    r.freight_charge_rub,
    r.transport_volume_tons,
    r.shipper_holding,
    r.cargo_id,
    r.origin_station_id,
    r.destination_station_id,
    r.wagon_kind_id,
    r.shipment_type_id,
    r.message_type_id,
    r.distance_loaded_km,
    CAST(c.code AS TEXT) AS cargo_code,
    cg.name AS cargo_group,
    CAST(cg.code AS TEXT) AS cargo_group_code,
    origin_rr.code AS origin_railroad_code,
    origin_rr.direction AS direction_raw,
    dest_rr.code AS destination_railroad_code,
    wk.name AS wagon_kind,
    st.name AS shipment_category,
    mt.name AS transport_type
FROM core_route r
LEFT JOIN core_cargo c ON r.cargo_id = c.code
LEFT JOIN core_cargogroup cg ON c.cargo_group_id = cg.code
LEFT JOIN core_station origin_st ON r.origin_station_id = origin_st.esr_code
LEFT JOIN core_railroad origin_rr ON origin_st.railroad_id = origin_rr.code
LEFT JOIN core_station dest_st ON r.destination_station_id = dest_st.esr_code
LEFT JOIN core_railroad dest_rr ON dest_st.railroad_id = dest_rr.code
LEFT JOIN core_wagonkind wk ON r.wagon_kind_id = wk.id
LEFT JOIN core_shipmenttype st ON r.shipment_type_id = st.id
LEFT JOIN core_messagetype mt ON r.message_type_id = mt.id
WHERE r.route_set_id = :route_set_id
  AND r.freight_charge_rub IS NOT NULL
  AND r.freight_charge_rub > 0;
