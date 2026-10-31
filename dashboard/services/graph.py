import logging

from plotly.graph_objs import Figure, Scatter

from .market_data import MarketDataError, get_provider

logger = logging.getLogger(__name__)

GRAPH_DAYS = 180
GRAPH_HEIGHT = 450


def get_graph(share):
    """Вернуть HTML графика цен закрытия или None, если данных нет"""
    try:
        candles = get_provider().get_daily_candles(share, GRAPH_DAYS)
    except MarketDataError as e:
        logger.error("График %s не построен: %s", share.ticker, e)
        return None

    if not candles:
        return None

    figure = Figure(
        Scatter(
            x=[candle.date for candle in candles],
            y=[candle.close for candle in candles],
            mode="lines",
            name=share.ticker,
            opacity=0.8,
            marker_color="red",
        )
    )
    # Без явной высоты блок графика в странице схлопывается в полоску
    return figure.to_html(
        full_html=False, include_plotlyjs="cdn", default_height=GRAPH_HEIGHT
    )
