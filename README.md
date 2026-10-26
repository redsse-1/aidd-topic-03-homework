# Investing Demo

Django application for browsing and maintaining a share catalogue, with a REST
API and periodically refreshed market prices.

## Windows setup

Use Python 3.12 or later. From PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a private `SECRET_KEY` and `POSTGRES_PASSWORD` in `.env`. The `.env` file
is ignored by Git and must not be committed.

Start PostgreSQL and Redis, then initialize the database and import shares:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py add_shares
.\.venv\Scripts\python.exe manage.py load_price_history --days 365
```

Run the web application and Celery processes in separate PowerShell windows:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe -m celery -A config worker -l info -P solo
.\.venv\Scripts\python.exe -m celery -A config beat -l info
```

The `solo` worker pool is used on Windows to avoid unsupported prefork workers
and the obsolete Eventlet workaround.

## Market data

The default provider is the public MOEX ISS API; it requires no token. Set
`MARKET_DATA_PROVIDER=moex` in `.env`. Share metadata and all current prices are
requested in batches. Price refreshes run every 15 minutes: this is a
deliberate interval aligned with delayed ISS quotes that avoids unnecessary
requests while keeping displayed prices reasonably current.
When ISS reports that the board is not trading, the provider uses the latest
closing price instead of the stale intraday quote.
`load_price_history` backfills daily candles (default: 365 calendar days); use
`--ticker SBER` to load one instrument. The command is safe to rerun: each
instrument/date pair is unique and existing daily rows are updated. Scheduled
quote refreshes also keep the current market day updated. The share detail page
plots stored history and supports 7, 30, 90, 180, 365 days, or all available
history, including absolute and percentage change for the selected interval.

ISS does not expose FIGI or T-Invest UID. The application stores the stable
synthetic identifier `MOEX:{BOARDID}:{SECID}` in both `figi` and `uid`, takes
ISIN from ISS `ISIN`, ticker from `SECID`, name from `SHORTNAME` (falling back
to `SECNAME`), and currency from `CURRENCYID` (`SUR` is normalized to `RUB`).
Rows without an ISIN/name or with a ticker longer than the model's 10-character
limit are skipped.

T-Invest is an optional, read-only provider. Install its SDK only if selecting
it:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-tinvest.txt
```

Then set `MARKET_DATA_PROVIDER=t-invest` and `TINVEST_TOKEN` in `.env`.
`TINVEST_API_TARGET` defaults to `invest-public-api.tbank.ru:443`;
`TINVEST_ROOT_CERT_PATH` can point to a PEM root certificate when a custom
certificate is needed. The provider only calls instrument, quote, and candle
read methods. After switching providers, run `manage.py add_shares` to map the
catalogue's records to the newly selected provider by ticker.

## API

The shares API is available at `/api/v1/shares/`. Anonymous clients can read;
creating, changing, and deleting shares requires authentication.
