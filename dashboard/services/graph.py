import logging

from plotly.graph_objs import Scatter
from plotly.offline import plot

from .market_data import MarketDataError, get_provider

logger = logging.getLogger(__name__)

GRAPH_DAYS = 180


def get_graph(share):
    """Вернуть HTML графика цен закрытия или None, если данных нет"""
    try:
        candles = get_provider().get_daily_candles(share, GRAPH_DAYS)
    except MarketDataError as e:
        logger.error("График %s не построен: %s", share.ticker, e)
        return None

    if not candles:
        return None

    return plot(
        [
            Scatter(
                x=[candle.date for candle in candles],
                y=[candle.close for candle in candles],
                mode="lines",
                name=share.ticker,
                opacity=0.8,
                marker_color="red",
            )
        ],
        output_type="div",
        include_plotlyjs="cdn",
        show_link=False,
        link_text="",
    )
