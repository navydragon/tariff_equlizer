# Nginx + Gunicorn + HTTPS (production)

Пошаговая настройка для сервера `/opt/tariff_equlizer/new_project`.

**Важно про HTTPS и IP:** [Let's Encrypt](https://letsencrypt.org/docs/faq/) **не выдаёт** сертификаты на адрес вида `157.22.172.245`. Certbot сработает только если у вас есть **доменное имя** (A-запись на этот IP). Для доступа только по IP — см. [вариант B: самоподписанный сертификат](#вариант-b-https-по-ip-самоподписанный-сертификат).

---

## 0. Предусловия

- `migrate` и `collectstatic` уже выполнены
- PostgreSQL и Redis работают
- `.env` заполнен, пользователь `tariff` владеет `/opt/tariff_equlizer`

```bash
mkdir -p /var/lib/tariff_equlizer/cache/{route_mart,scenario_compute,route_masks}
chown -R tariff:tariff /var/lib/tariff_equlizer
```

---

## 1. Переменные `.env` для Django

Отредактируйте `/opt/tariff_equlizer/new_project/.env`:

```env
# Gunicorn (в systemd можно не дублировать — см. gunicorn.conf.py)
GUNICORN_WORKERS=1
GUNICORN_BIND=127.0.0.1:8000

# Хосты — IP и/или домен
DJANGO_ALLOWED_HOSTS=157.22.172.245,ваш-домен.ru
DJANGO_CSRF_TRUSTED_ORIGINS=https://157.22.172.245,https://ваш-домен.ru

# За nginx с HTTPS (прокси)
DJANGO_SECURE_SSL=true
DJANGO_SECURE_SSL_REDIRECT=false
```

После смены `.env`:

```bash
sudo -u tariff bash -c '
  cd /opt/tariff_equlizer/new_project
  source .venv/bin/activate
  export DJANGO_SETTINGS_MODULE=config.settings_prod
  python manage.py collectstatic --noinput
'
```

---

## 2. Gunicorn (systemd)

Файл уже в репозитории: `deploy/tariff-equlizer.service`.

```bash
cp /opt/tariff_equlizer/new_project/deploy/tariff-equlizer.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable tariff-equlizer
systemctl start tariff-equlizer
systemctl status tariff-equlizer
```

Проверка сокета (должен отвечать Django):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
```

Логи:

```bash
journalctl -u tariff-equlizer -f
```

Параметры Gunicorn — `deploy/gunicorn.conf.py` и переменные `GUNICORN_*` в `.env`.

---

## 3. Nginx — HTTP (перед сертификатом)

### 3.1. Установка

```bash
apt install -y nginx
systemctl enable nginx
```

### 3.2. Конфиг только HTTP (для certbot или теста)

```bash
cp /opt/tariff_equlizer/new_project/deploy/nginx-http.conf.example \
   /etc/nginx/sites-available/tariff-equlizer

ln -sf /etc/nginx/sites-available/tariff-equlizer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx
```

Откройте в браузере: `http://157.22.172.245/`

---

## 4. Firewall (рекомендуется)

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
ufw status
```

---

## Вариант A: HTTPS через Certbot (нужен домен)

### 4.1. DNS

У регистратора/AdminVPS создайте **A-запись**:

| Имя | Тип | Значение |
|-----|-----|----------|
| `@` или `tariff` | A | `157.22.172.245` |

Проверка (с вашего ПК):

```bash
dig +short ваш-домен.ru
# должно вернуть 157.22.172.245
```

### 4.2. Certbot

```bash
apt install -y certbot python3-certbot-nginx
```

В `.env` добавьте домен в `DJANGO_ALLOWED_HOSTS` и `DJANGO_CSRF_TRUSTED_ORIGINS` (см. шаг 1).

Выпустить сертификат (nginx должен слушать :80):

```bash
certbot --nginx -d ваш-домен.ru --non-interactive --agree-tos -m admin@example.com
```

Или интерактивно:

```bash
certbot --nginx -d ваш-домен.ru
```

Certbot сам поправит nginx и добавит `listen 443 ssl`. Проверка автообновления:

```bash
certbot renew --dry-run
```

Сайт: `https://ваш-домен.ru/`

### 4.3. Ручной SSL-конфиг (если certbot не трогает файл)

Скопируйте шаблон и подставьте пути Let's Encrypt:

```bash
cp /opt/tariff_equlizer/new_project/deploy/nginx-ssl.conf.example \
   /etc/nginx/sites-available/tariff-equlizer
nano /etc/nginx/sites-available/tariff-equlizer
# server_name ваш-домен.ru;
# ssl_certificate /etc/letsencrypt/live/ваш-домен.ru/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/ваш-домен.ru/privkey.pem;

nginx -t && systemctl reload nginx
```

---

## Вариант B: HTTPS по IP (самоподписанный сертификат)

Браузер покажет предупреждение — нормально для теста без домена.

```bash
mkdir -p /etc/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/tariff_equlizer.key \
  -out /etc/nginx/ssl/tariff_equlizer.crt \
  -subj "/CN=157.22.172.245"
chmod 600 /etc/nginx/ssl/tariff_equlizer.key
```

```bash
cp /opt/tariff_equlizer/new_project/deploy/nginx-ssl-ip.conf.example \
   /etc/nginx/sites-available/tariff-equlizer

ln -sf /etc/nginx/sites-available/tariff-equlizer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx
```

Сайт: `https://157.22.172.245/` (примите исключение в браузере).

---

## 5. Проверка после выкладки

```bash
systemctl is-active tariff-equlizer nginx
curl -sI http://127.0.0.1:8000/ | head -5
curl -sI https://157.22.172.245/ -k | head -5   # -k для self-signed
```

В браузере: логин admin, сценарий RZD_2026, `/route-analysis/`.

---

## 6. Обновление релиза

```bash
cd /opt/tariff_equlizer
git pull   # или scp/rsync
chown -R tariff:tariff /opt/tariff_equlizer

sudo -u tariff bash -c '
  cd /opt/tariff_equlizer/new_project
  source .venv/bin/activate
  export DJANGO_SETTINGS_MODULE=config.settings_prod
  pip install -r requirements.txt
  python manage.py migrate
  python manage.py collectstatic --noinput
'

systemctl restart tariff-equlizer
systemctl reload nginx
```

---

## Устранение неполадок

| Симптом | Действие |
|---------|----------|
| 502 Bad Gateway | `systemctl status tariff-equlizer`, порт 8000: `ss -lntp \| grep 8000` |
| 400 Bad Request | Проверьте `DJANGO_ALLOWED_HOSTS` |
| CSRF ошибка при POST | Добавьте URL в `DJANGO_CSRF_TRUSTED_ORIGINS` с `https://` |
| Статика 404 | `collectstatic`, путь `alias` в nginx → `staticfiles/` |
| Certbot failed | Домен не указывает на сервер, закрыт порт 80, нет домена для IP |
