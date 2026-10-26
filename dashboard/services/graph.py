from collections.abc import Sequence

from plotly.graph_objs import Scatter
from plotly.offline import plot

from dashboard.models import Share, SharePriceHistory


def get_graph(share: Share, history: Sequence[SharePriceHistory]) -> str:
    return plot(
        [
            Scatter(
                x=[point.date for point in history],
                y=[float(point.close) for point in history],
                mode="lines",
                name=share.ticker,
                opacity=0.8,
                marker_color="red",
            )
        ],
        output_type="div",
    )
