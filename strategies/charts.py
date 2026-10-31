from plotly.graph_objs import Figure, Scatter

GRAPH_HEIGHT = 400


def to_html(figure, include_plotlyjs):
    figure.update_layout(legend={"orientation": "h"})
    return figure.to_html(
        full_html=False, include_plotlyjs=include_plotlyjs, default_height=GRAPH_HEIGHT
    )


def trade_markers(trades, side, name, color, symbol):
    selected = [trade for trade in trades if trade.side == side]
    return Scatter(
        x=[trade.date for trade in selected],
        y=[float(trade.price) for trade in selected],
        mode="markers",
        name=name,
        marker={"color": color, "size": 11, "symbol": symbol},
    )


def price_chart(closes, trades):
    """График цены с отметками сделок"""
    figure = Figure(
        [
            Scatter(
                x=[day for day, _ in closes],
                y=[float(price) for _, price in closes],
                mode="lines",
                name="Цена закрытия",
                line={"color": "gray"},
            ),
            trade_markers(trades, "buy", "Покупка", "seagreen", "triangle-up"),
            trade_markers(trades, "sell", "Продажа", "crimson", "triangle-down"),
        ]
    )
    return to_html(figure, "cdn")


def equity_chart(equity):
    """График стоимости виртуального портфеля"""
    figure = Figure(
        Scatter(
            x=[day for day, _ in equity],
            y=[float(value) for _, value in equity],
            mode="lines",
            name="Стоимость портфеля",
            line={"color": "royalblue"},
        )
    )
    return to_html(figure, False)
