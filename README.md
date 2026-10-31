# investing

Справочник акций Мосбиржи: список с текущими ценами, график за 180 дней, управление
акциями и REST API. Токен не нужен: данные по умолчанию берутся из публичного API
Мосбиржи ISS с задержкой около 15 минут.

Требуется Python 3.12+ и Docker Desktop. Команды даны для PowerShell.

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

В файле `.env` задайте свои `SECRET_KEY` и `POSTGRES_PASSWORD`.

## Запуск

```powershell
docker compose up -d --wait
python manage.py migrate
python manage.py add_shares
python manage.py backfill_prices
python manage.py runserver
```

Сайт: <http://127.0.0.1:8000/>. Обновление цен запускается в двух отдельных окнах:

```powershell
# Celery Worker. На Windows нужен пул solo: стандартный prefork там не работает
celery -A config worker -l info -P solo

# Celery Beat
celery -A config beat -l info
```

Интервал обновления задаётся в `PRICE_UPDATE_INTERVAL`, по умолчанию 300 секунд.

## История цен

`backfill_prices` загружает закрытия за год из дневных свечей (около 8 минут на все
акции). Команду можно запускать повторно: дублей не будет. Параметры: `--days`,
`--ticker`. Каждую ночь в 01:00 по Москве beat догружает последние дни и удаляет
внутридневные котировки старше `HISTORY_QUOTE_RETENTION_DAYS`. График на странице акции
строится только из базы приложения.

## Тесты

```powershell
python manage.py test
```

Нужна запущенная PostgreSQL. Обращений к внешним API в тестах нет.

## Рыночные данные

Источник выбирается переменной `MARKET_DATA_PROVIDER`:

| Значение | Источник | Что нужно |
|---|---|---|
| `iss` (по умолчанию) | публичное API Мосбиржи ISS | ничего |
| `tinvest` | T-Invest API | `pip install -r requirements-tinvest.txt` и `TINVEST_TOKEN` |

Для `tinvest` нужен токен только на чтение. Если для соединения требуется корневой
сертификат, укажите путь к PEM-файлу в `TINVEST_ROOT_CA_PATH`. После смены источника
выполните `python manage.py add_shares`: команда заменит условные FIGI на настоящие.

## API

`/api/v1/shares/` — работа с акциями. Чтение доступно всем, изменение только после
входа: Basic-авторизация (email и пароль) или сессия сайта.

История цен: `/api/v1/shares/<id>/history/?period=1m`, где `period` — это `1w`, `1m`,
`3m`, `6m`, `1y`, `all`, либо `date_from` и `date_to`.

Параметры списка: `limit`, `offset`, `ticker`, `name`, `search` (регулярное выражение
по названию), `ordering` (`name`, `ticker`, `-name`, `-ticker`).
