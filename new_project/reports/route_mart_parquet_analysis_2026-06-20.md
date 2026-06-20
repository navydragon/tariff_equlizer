# Анализ parquet-витрины маршрутов (2026-06-20)

**RouteSet id:** 3  
**Файл:** `C:\Users\Пользователь\Documents\projects\tariff_equlizer\new_project\cache\route_mart\3\refs7917_20260525T184316371849Z.parquet`  
**Строк:** 1,934,733  
**Колонок в parquet:** 2

## 1. Summary — размеры файлов

| Файл | Размер, МБ |
|------|------------|
| parquet | 1.21 |
| charge.npy | 14.76 |
| dims.npz | 20.30 |
| masks.npz | 18.45 |
| meta.json | 0.05 |
| **Итого** | 54.77 |

- In-memory DataFrame: **11.07 МБ**
- Байт на строку (in-memory): **6.0**

## 2. Column inventory

| Колонка | Arrow dtype | Pandas dtype | Memory МБ | nunique | null% | min | max |
|---------|-------------|--------------|-----------|---------|-------|-----|-----|
| `transport_volume_tons` | float | float32 | 7.38 | 20,453 | 0.0 | 0.0 | 1.1143046e+07 |
| `cargo_group_code` | uint16 | uint16 | 3.69 | 11 | 0.0 | 1 | 11 |

## 3. Redundancy table

### KEEP (parquet-only) (11.07 МБ)

`transport_volume_tons`, `cargo_group_code`

**Итого избыточно в parquet:** REDUNDANT 0.00 МБ + SIDECAR_ONLY 0.00 МБ = **0.00 МБ**

**Минимальный theoretical slim-parquet:** `transport_volume_tons`, `cargo_group_code` (+ опционально `freight_charge_rub` как fallback без charge.npy).

## 4. Type recommendations (KEEP-колонки)

| Колонка | Текущий | min | max | nunique | Рекомендация | Экономия МБ |
|---------|---------|-----|-----|---------|--------------|-------------|
| `cargo_group_code` | uint16 | 1 | 11 | 11 | uint8 | 1.85 |
| `transport_volume_tons` | float32 | 0.0 | 1.1143046e+07 | 20,453 | float32 | 0.00 |

## 5. Estimated savings (теоретически, без внедрения)

| Метрика | МБ |
|---------|-----|
| Память REDUNDANT колонок | 0.00 |
| Память SIDECAR_ONLY (dim_*) | 0.00 |
| Downcast KEEP-колонок | 1.85 |
| **Суммарная экономия in-memory** | **1.85** |
| Theoretical slim-parquet in-memory | 9.23 |

Экстраполяция на диск (snappy): ориентир **30–50%** от in-memory для строковых колонок; числовые сжимаются слабее.

## 6. Sidecar masks.npz

- schema_version: 3
- keys: distance_belt, distance_belt_midpoint_km, message_type_id, shipment_type_id, shipper_id, special_container_type
- dtypes:
  - `distance_belt`: uint8
  - `distance_belt_midpoint_km`: uint16
  - `special_container_type`: uint8
  - `shipper_id`: uint16
  - `shipment_type_id`: uint16
  - `message_type_id`: uint16

## Примечания

- Hot-path расчёта (`resolve_light_mart_columns`) читает sidecar, не parquet.
- `transport_volume_tons` не имеет sidecar — deferred compute читает full parquet.
- `cargo_group_code` нужен как fallback для matching правил.
