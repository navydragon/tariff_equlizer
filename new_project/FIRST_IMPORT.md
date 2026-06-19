# Первичная установка данных (fresh install)

Инструкция для развёртывания **с нуля**: справочники → маршруты РЖД (~2.1 млн) → экономика из IPEM.  
Все команды выполняются из каталога `new_project`.

Подробные параметры команд — в [commands.md](commands.md).  
Развёртывание на сервере (gunicorn, nginx, `.env`) — в [PRODUCTION.md](PRODUCTION.md).

---

## 0. Предварительные условия

### Окружение

```bash
cd new_project
python -m venv .venv

# Linux / macOS / WSL
source .venv/bin/activate

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Переменные окружения

Создайте `new_project/.env` (минимум):

```env
ADMIN_PASSWORD=ваш_пароль
# При необходимости PostgreSQL:
# USE_POSTGRES=true
# DATABASE_URL=postgres://...
```

Для `create_base_scenario` без предварительного `create_admin` может понадобиться `BOOTSTRAP_ADMIN_PASSWORD`.

### Файлы данных (должны быть в репозитории или скопированы вручную)

| Файл | Назначение |
|------|------------|
| `core/data/railroads.csv` | Железные дороги |
| `data/refs-01/regions.csv` | Регионы |
| `data/refs-01/stations.csv` | Станции |
| `core/data/cargo_groups.csv` | Группы грузов |
| `data/refs-01/cargos.csv` | Грузы ETSNG |
| `data/refs-01/shippers.csv` | Грузоотправители |
| `../data/01_2026-05-19.db` | SQLite РЖД (таблица `ИХ_ГП`) — **вне** `new_project`, в `data/` корня репозитория |
| `total_ipem.csv` | Маршруты и экономика IPEM (~550 строк) |

Опционально: `core/data/settings.csv` — `import_settings`.

---

## 1. Схема БД

```bash
python manage.py migrate
```

---

## 2. Администратор

```bash
python manage.py create_admin --login admin --email admin@example.com --password "%ADMIN_PASSWORD%"
```

В PowerShell задайте пароль заранее: `$env:ADMIN_PASSWORD="ваш_пароль"`, затем подставьте в команду или используйте `--password` явно.

---

## 3. Справочники

Порядок важен. Команды **идемпотентны** (повторный запуск обновляет данные), если не указан `--clear`.

```bash
python manage.py import_railroads
python manage.py import_regions
python manage.py import_stations
python manage.py import_cargo_groups
python manage.py import_cargos
python manage.py import_shippers
python manage.py init_route_refs
```

Опционально:

```bash
python manage.py import_settings
```

---

## 4. Базовый сценарий

Создаёт сценарий «Базовый сценарий» (2025–2035), BTD, прогнозы инфляции и курса USD/RUB.

```bash
python manage.py create_base_scenario
python manage.py load_base_btd
```

> По умолчанию сценарий привязан к техническому набору `DEFAULT_ROUTE_SET`. После импорта РЖД (шаг 5) в интерфейсе укажите для рабочего сценария набор **RZD_2026** (или создайте отдельный сценарий с этим набором).

---

## 5. Маршруты РЖД

Импорт из SQLite в набор `RZD_2026`. Занимает **долго** (миллионы строк, десятки минут и больше — зависит от диска и CPU).

Проверка на 1000 строк без записи:

```bash
python manage.py import_rzd_routes --dry-run --limit 1000
```

Полный импорт (при повторной загрузке — с очисткой набора):

```bash
python manage.py import_rzd_routes --clear
```

Параметры по умолчанию: `--db ../data/01_2026-05-19.db`, `--route-set-code RZD_2026`.

После импорта в маршрутах есть объёмы перевозок (т, т·км, провозная плата), но **нет** блока экономики и расходов РЖД из IPEM — их добавляет шаг 6.

---

## 6. Экономика IPEM → маршруты RZD_2026

### 6.0. Уголь 2026: model-маршруты и эластичность (рекомендуется)

Импорт из `data/ipem/Уголь_эластика_2026.xlsx`:

- лист **Уголь_эластика** → **model-маршруты** (`is_model=true`) в `RouteSet RZD_2026`;
- лист **Уголь_коэфф** → набор эластичности **«2026»** (правила «Уголь экспорт» / «Уголь внутренние») и привязка к сценарию.

Operational-маршруты РЖД связываются через `model_route_id` по ключу: **станция + станция + груз + род вагона + тип отправки**.

Правило эластичности **не хранится на маршруте**: при расчётах выбирается runtime по `message_type` из набора сценария (`Scenario.elasticity_set`).

Model-маршруты **не участвуют** в расчётах «Эффект решений» и «Куб эффектов»; в «Экономике грузов» в поиске показываются только они.

```bash
python manage.py import_ipem_coal_2026_routes ^
  --file ../data/ipem/Уголь_эластика_2026.xlsx ^
  --route-set-code RZD_2026 ^
  --scenario-id 1
```

Только маршруты (без эластичности), как раньше:

```bash
python manage.py import_ipem_coal_2026_routes ^
  --file ../data/ipem/Уголь_эластика_2026.xlsx ^
  --route-set-code RZD_2026
```

Проверка без записи:

```bash
python manage.py import_ipem_coal_2026_routes --dry-run --scenario-id 1
```

После импорта пересобрать витрины:

```bash
python manage.py refresh_deploy_caches
```

Проверка пересечения IPEM ↔ РЖД (отчёт CSV):

```bash
python scripts/check_ipem_coal_2026_rzd.py
```

### 6.1. Legacy: total_ipem.csv (старый пайплайн)

Сопоставление: **ЕСР отправления + ЕСР назначения + груз** (имя из колонки «Груз», fuzzy, порог 90).  
Во все совпавшие записи РЖД проставляются расходы РЖД (груж./порожн./итого) и блок экономики (операторы, перевалка, акциз, себестоимость, рыночная цена и т.д.).

#### 6.1.1. Экспорт совпадений (для проверки)

```bash
python manage.py export_ipem_rzd_economics_2025 ^
  --file total_ipem.csv ^
  --route-set-code RZD_2026 ^
  --output scripts/ipem_rzd_economics_2025.csv
```

На Linux/macOS замените `^` на `\` в конце строк.

В консоли — сводка: сколько строк IPEM совпало, сколько пропущено (нет груза / нет пары в РЖД).  
Результат: `scripts/ipem_rzd_economics_2025.csv` — только строки с `rzd_match_count > 0`.

### 6.2. Проставление в БД (legacy)

Сначала dry-run:

```bash
python manage.py apply_ipem_economics_to_rzd_2025 ^
  --file scripts/ipem_rzd_economics_2025.csv ^
  --from-export ^
  --route-set-code RZD_2026 ^
  --dry-run
```

Запись в БД:

```bash
python manage.py apply_ipem_economics_to_rzd_2025 ^
  --file scripts/ipem_rzd_economics_2025.csv ^
  --from-export ^
  --route-set-code RZD_2026
```

Альтернатива без промежуточного CSV (сразу из `total_ipem.csv`):

```bash
python manage.py apply_ipem_economics_to_rzd_2025 --file total_ipem.csv --route-set-code RZD_2026
```

---

## 7. Запуск приложения

```bash
python manage.py runserver
```

Войти под `admin`, выбрать сценарий с набором **RZD_2026**, открыть «Экономика грузов» (`/route-analysis/`) — в поиске маршрутов видны **model-маршруты IPEM** (`is_model=true`).

---

## Альтернативные сценарии установки

### A. Быстрый dev (случайные 100k маршрутов, без РЖД и IPEM)

```bash
python manage.py migrate
python manage.py prepare_dev
```

Требуется `ADMIN_PASSWORD` в окружении. Набор по умолчанию: `DEFAULT_ROUTE_SET`.

### B. Только IPEM (~550 маршрутов с полной карточкой)

Без SQLite РЖД. Удобно для лёгкой локальной проверки UI.

После шагов **1–4** (миграции, админ, справочники, сценарий):

```bash
python manage.py import_total_ipem --file total_ipem.csv --route-set-code DEFAULT_ROUTE_SET
```

В сценарии укажите набор `DEFAULT_ROUTE_SET`.

### C. Bash-скрипт (IPEM + опционально random)

Аналог части цепочки B; **без** импорта РЖД и `apply_ipem_economics_to_rzd_2025`:

```bash
# из корня репозитория, Linux/WSL/Git Bash
ADMIN_PASSWORD="ваш_пароль" bash new_project/tasks/load_startup_data.sh
```

Случайные 100k маршрутов в тот же набор:

```bash
GENERATE_RANDOM_ROUTES=1 ADMIN_PASSWORD="ваш_пароль" bash new_project/tasks/load_startup_data.sh
```

---

## Краткая шпаргалка (основной путь)

| # | Команда |
|---|---------|
| 1 | `migrate` |
| 2 | `create_admin` |
| 3 | `import_railroads` → `import_regions` → `import_stations` → `import_cargo_groups` → `import_cargos` → `import_shippers` → `init_route_refs` |
| 4 | `create_base_scenario` → `load_base_btd` |
| 5 | `import_rzd_routes --clear` |
| 6 | `export_ipem_rzd_economics_2025` → `apply_ipem_economics_to_rzd_2025 --from-export` |
| 7 | В UI: сценарий → набор маршрутов **RZD_2026** |
| 8 | `runserver` |

---

## Проверка

```bash
python manage.py test
```

Отдельно тесты IPEM/RZD:

```bash
python manage.py test core.management.tests.test_ipem_economics_2025
```
