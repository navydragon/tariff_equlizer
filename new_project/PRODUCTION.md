# Развёртывание на production

Краткий runbook для сервера Linux. Первичная загрузка данных — в [FIRST_IMPORT.md](FIRST_IMPORT.md).

Все команды — из каталога `new_project`, виртуальное окружение активировано.

---

## 1. Зависимости

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Окружение

```bash
cp .env.production.example .env
# Отредактируйте .env: SECRET_KEY, ALLOWED_HOSTS, Postgres, Redis, пути кэша
```

Сгенерировать `DJANGO_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Обязательно для прода:

| Переменная | Комментарий |
|------------|-------------|
| `DJANGO_SECRET_KEY` | Уникальный ключ |
| `DJANGO_ALLOWED_HOSTS` | Домен/IP |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://ваш-домен` |
| `USE_POSTGRES=true` | SQLite не для ~2M маршрутов |
| `POSTGRES_PASSWORD` | Пароль БД |
| `REDIS_URL` | При `GUNICORN_WORKERS` > 1 |

Каталоги кэша (создайте и дайте права пользователю сервиса):

```bash
sudo mkdir -p /var/lib/tariff_equlizer/cache/{route_mart,scenario_compute,route_masks}
sudo chown -R tariff:tariff /var/lib/tariff_equlizer
```

---

## 3. Схема и статика

```bash
export DJANGO_SETTINGS_MODULE=config.settings_prod

python manage.py migrate
python manage.py check --deploy
python manage.py collectstatic --noinput
```

---

## 4. Данные

Полная цепочка — [FIRST_IMPORT.md](FIRST_IMPORT.md) (справочники → РЖД → IPEM).

Минимум после миграций:

```bash
python manage.py create_admin --login admin --email admin@example.com --password "$ADMIN_PASSWORD"
# … import_railroads, import_rzd_routes, apply_ipem_economics_to_rzd_2025 и т.д.
```

Если миграция `0027` прервалась на большой БД:

```bash
python manage.py backfill_distance_belt_midpoint
```

---

## 5. Gunicorn

Проверка вручную:

```bash
export DJANGO_SETTINGS_MODULE=config.settings_prod
gunicorn -c deploy/gunicorn.conf.py config.wsgi:application
```

Постоянный запуск — `deploy/tariff-equlizer.service` (отредактируйте пути `/opt/...` и пользователя `tariff`).

```bash
sudo systemctl enable --now tariff-equlizer
sudo journalctl -u tariff-equlizer -f
```

**Workers:** тяжёлые расчёты в pandas/numpy. Начните с `GUNICORN_WORKERS=1` или `2` и смотрите RAM; при OOM уменьшите workers.

**Timeout:** по умолчанию 300 с в gunicorn и в `deploy/nginx.conf.example`.

---

## 6. Nginx + HTTPS

Пошагово (Gunicorn, nginx, certbot, IP vs домен): **[deploy/DEPLOY_NGINX_SSL.md](deploy/DEPLOY_NGINX_SSL.md)**.

Шаблоны:

| Файл | Назначение |
|------|------------|
| `deploy/nginx-http.conf.example` | HTTP, перед certbot |
| `deploy/nginx-ssl.conf.example` | HTTPS + Let's Encrypt (нужен **домен**) |
| `deploy/nginx-ssl-ip.conf.example` | HTTPS по IP (самоподписанный) |

> Certbot/Let's Encrypt **не выдаёт** сертификат на `157.22.172.245` — только на домен с A-записью на этот IP.

После `collectstatic` nginx раздаёт `/static/` из `staticfiles/`.

---

## 7. Проверка после выкладки

```bash
python manage.py test
```

Smoke в браузере:

1. Логин.
2. Сценарий с набором **RZD_2026**.
3. `/route-analysis/` — поиск маршрута.
4. Страница эффектов / куб — первый расчёт (может быть долгим, затем быстрее за счёт кэша).

---

## 8. Обновление релиза

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SETTINGS_MODULE=config.settings_prod
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart tariff-equlizer
```

Кэш на диске (`/var/lib/tariff_equlizer/cache/`) между релизами сохраняйте.

---

## 9. Бэкапы

- PostgreSQL — ежедневно (`pg_dump` / ваш инструмент).
- Дисковый кэш можно не бэкапить (пересоберётся, но первый прогон будет долгим).

---

## 10. Локальная разработка vs prod

| | Dev | Prod |
|---|-----|------|
| Settings | `config.settings` (по умолчанию) | `config.settings_prod` |
| DEBUG | `DJANGO_DEBUG=true` или не задан | всегда `False` |
| Сервер | `runserver` | gunicorn + nginx |
| БД | SQLite или Postgres | Postgres |
