from django.utils import timezone
from plotly.graph_objs import Figure, Scatter

GRAPH_HEIGHT = 450


def get_graph(share, points):
    """Вернуть HTML графика цены по точкам истории или None, если их нет"""
    if not points:
        return None

    figure = Figure(
        Scatter(
            x=[timezone.localtime(point.moment).replace(tzinfo=None) for point in points],
            y=[point.price for point in points],
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
