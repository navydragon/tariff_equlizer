# PostgreSQL для `new_project`

## Что сделано в репозитории
- Добавлена поддержка PostgreSQL в `new_project/config/settings.py` (включается через `USE_POSTGRES=true`).
- Добавлен драйвер БД `psycopg[binary]`.
- Добавлен `docker-compose.yml` для поднятия локального PostgreSQL.
- Добавлен пример окружения `.env.example`.

## План действий
1. Создайте файл `new_project/.env` (скопируйте `new_project/.env.example`).
2. Поднимите базу:
   - из папки `new_project`: `docker compose up -d db`
3. Примените миграции:
   - из папки `new_project`: `python manage.py migrate`
4. (Опционально) создайте суперпользователя:
   - `python manage.py createsuperuser`

## Важное замечание про данные
Переключение SQLite -> PostgreSQL не переносит существующие данные автоматически. Если нужна миграция данных — делайте её отдельно.

