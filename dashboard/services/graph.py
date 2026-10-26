from plotly.graph_objs import Scatter
from plotly.offline import plot

from dashboard.models import Share
from dashboard.services.market_data import get_market_data_provider


def get_graph(share: Share) -> str:
    history = get_market_data_provider().get_history(share, days=180)
    return plot(
        [
            Scatter(
                x=[point.time for point in history],
                y=[float(point.close) for point in history],
                mode="lines",
                name=share.ticker,
                opacity=0.8,
                marker_color="red",
            )
        ],
        output_type="div",
        show_link=False,
        link_text="",
    )
