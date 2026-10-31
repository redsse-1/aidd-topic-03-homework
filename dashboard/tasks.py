import logging

from config.celery import app
from dashboard.services.market_data import MarketDataError, get_provider
from dashboard.services.price_history import prune_quotes, refresh_daily_history
from dashboard.services.shares import update_last_prices
from monitoring.services import check_price_targets

logger = logging.getLogger(__name__)


@app.task
def update_last_price():
    try:
        update_last_prices(get_provider())
    except MarketDataError as e:
        logger.error(e)
        return
    check_price_targets()


@app.task
def update_price_history():
    refresh_daily_history(get_provider())
    prune_quotes()
