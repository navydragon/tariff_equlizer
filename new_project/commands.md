# Management-команды `new_project`

Запуск из каталога `new_project` (после `python manage.py migrate`):

```bash
cd new_project
python manage.py <команда> [параметры]
```

Переменные из `new_project/.env` подхватываются автоматически (`config/settings.py`).

---

## Сводная команда для dev

### `prepare_dev`

Полная подготовка локальной среды: админ → справочники → базовый сценарий → **100 000** случайных маршрутов.

```bash
python manage.py prepare_dev
```

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--skip-admin` | — | Не вызывать `create_admin` |
| `--login` | `admin` | Логин суперпользователя |
| `--email` | `admin@emiit.ru` | Email |
| `--password` | из `ADMIN_PASSWORD` | Пароль (обязателен, если не `--skip-admin`) |
| `--route-set-code` | `DEFAULT_ROUTE_SET` | Набор маршрутов для генерации |
| `--routes-count` | `100000` | Число случайных маршрутов |
| `--skip-routes` | — | Не генерировать маршруты |
| `--clear-routes` | — | Удалить маршруты набора перед генерацией |
| `--batch-size` | `1000` | Пакет для `bulk_create` |
| `--clear-references` | — | Очистить справочники перед импортом |

Пример без админа и с меньшим числом маршрутов (быстрая проверка):

```bash
python manage.py prepare_dev --skip-admin --routes-count 1000
```

**Аналог в bash:** `tasks/load_startup_data.sh` — импорт справочников, базовый сценарий, по умолчанию **реальные** маршруты из `total_ipem.csv`; случайные 100k включаются через `GENERATE_RANDOM_ROUTES=1`.

---

## Пользователи и сценарии

### `create_admin` (core)

Создаёт суперпользователя для входа в приложение.

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--login` | `admin@emiit.ru` | Логин |
| `--email` | `admin@emiit.ru` | Email |
| `--password` | `ADMIN_PASSWORD` | Пароль |
| `--first-name` | `Admin` | Имя |
| `--last-name` | `Admin` | Фамилия |
| `--middle-name` | `""` | Отчество |
| `--reset-password` | — | Сбросить пароль, если пользователь уже есть |

### `create_base_scenario` (scenarios)

Создаёт или обновляет сценарий **«Базовый сценарий»** (2025–2035): технический `RouteSet`, BTD, наборы **«Прогноз ЦБ»** (инфляция и USD/RUB по данным Банка России).

Параметров нет. Если нет суперпользователя — нужен `BOOTSTRAP_ADMIN_PASSWORD` в `.env`.

```bash
python manage.py create_base_scenario
```

### `load_base_btd` (scenarios)

Перезагружает матрицу базовых тарифных решений в сценарий «Базовый сценарий».

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--scenario-name` | `Базовый сценарий` | Имя целевого сценария |

```bash
python manage.py load_base_btd
```

---

## Справочники (core)

Импорты идемпотентны (повторный запуск обновляет записи), если не указан `--clear`.

### `import_railroads`

Железные дороги из `core/data/railroads.csv`.

| Параметр | Описание |
|----------|----------|
| `--clear` | Очистить таблицу перед импортом |

### `import_regions`

Регионы из `data/refs-01/regions.csv`.

| Параметр | Описание |
|----------|----------|
| `--file` | Путь к CSV (по умолчанию `data/refs-01/regions.csv`) |
| `--clear` | Удалить станции и регионы перед импортом |

### `import_stations`

Станции из `data/refs-01/stations.csv` (регионы — из `import_regions` или создаются при импорте станции).

| Параметр | Описание |
|----------|----------|
| `--file` | Путь к CSV (по умолчанию `data/refs-01/stations.csv`) |
| `--clear` | Очистить только станции перед импортом |

### `import_cargo_groups`

Группы грузов из `core/data/cargo_groups.csv`. Параметров нет.

### `import_cargos`

Номенклатура ETSNG из `data/refs-01/cargos.csv` (нужен предварительный `import_cargo_groups`).

| Параметр | Описание |
|----------|----------|
| `--file` | Путь к CSV (по умолчанию `data/refs-01/cargos.csv`) |
| `--clear` | Очистить справочник грузов перед импортом |

### `import_shippers`

Грузоотправители из `data/refs-01/shippers.csv`.

| Параметр | Описание |
|----------|----------|
| `--file` | Путь к CSV (по умолчанию `data/refs-01/shippers.csv`) |
| `--clear` | Очистить справочник перед импортом |

### `init_route_refs`

Справочники маршрута: род вагона, тип отправки, вид сообщения.

| Параметр | Описание |
|----------|----------|
| `--clear` | Очистить таблицы перед инициализацией |

### `import_settings`

Настройки приложения из CSV (`code;description;value`).

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--file` | `core/data/settings.csv` | Путь к файлу |

---

## Маршруты (core)

### `import_total_ipem`

Импорт **реальных** маршрутов из CSV (формат total_ipem, разделитель `;`).

| Параметр | Обязательный | Описание |
|----------|--------------|----------|
| `--file` | да | Путь к CSV |
| `--route-set-code` | да | Код `RouteSet` |
| `--route-set-name` | нет | Название набора (по умолчанию = коду) |
| `--similarity-threshold` | нет | Порог нечёткого поиска груза/станции (0–100), по умолчанию `90` |
| `--dry-run` | нет | Только отчёт, без записи в БД |

```bash
python manage.py import_total_ipem --file total_ipem.csv --route-set-code DEFAULT_ROUTE_SET
```

### `generate_random_routes`

Генерация **случайных** тестовых маршрутов (нужны справочники и `init_route_refs`).

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--route-set-code` | — | Код набора (обязательный) |
| `--count` | `100000` | Количество маршрутов |
| `--route-set-name` | = коду | Название при создании набора |
| `--batch-size` | `1000` | Размер пакета `bulk_create` |
| `--clear-existing` | — | Удалить маршруты набора перед генерацией |

```bash
python manage.py generate_random_routes --route-set-code DEFAULT_ROUTE_SET --count 100000
```

---

## Рекомендуемые цепочки

**Быстрый dev (случайные 100k маршрутов):**

```bash
python manage.py migrate
python manage.py prepare_dev
```

**Продакшен-подобные данные (CSV total_ipem):**

```bash
python manage.py migrate
python manage.py create_admin --login admin --password "$ADMIN_PASSWORD"
python manage.py import_railroads
python manage.py import_regions
python manage.py import_stations
python manage.py import_cargo_groups
python manage.py import_cargos
python manage.py import_shippers
python manage.py init_route_refs
python manage.py create_base_scenario
python manage.py import_total_ipem --file total_ipem.csv --route-set-code DEFAULT_ROUTE_SET
```

**Только обновить базовый сценарий (BTD, курсы, инфляция):**

```bash
python manage.py create_base_scenario
```

---

## Стандартные команды Django

| Команда | Назначение |
|---------|------------|
| `python manage.py migrate` | Применить миграции |
| `python manage.py runserver` | Dev-сервер |
| `python manage.py test` | Тесты |
| `python manage.py shell` | Интерактивная оболочка |

При `USE_POSTGRES=true` в `.env` тесты по умолчанию всё равно используют SQLite (`config/settings.py`).
