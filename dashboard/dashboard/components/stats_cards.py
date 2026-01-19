"""Summary stats cars component."""

import reflex as rx
from ..state import DashboardState


def stat_card(
    title: str,
    value: rx.Var,
    icon: str,
    color: str
) -> rx.Component:
    """Individual Stats card
    
    Parameters
    ----------
    title : str
        The title of the card.
    value : rx.Var
        The value to display.
    icon : str
        The Lucide icon name for display (e.g. "bar-chart", "link")
    color : str
        The color of the value text.
    """
    return rx.card(
        rx.vstack(
            rx.icon(icon, size=28),
            rx.text(
                value,
                size="6",
                weight="bold",
                color=color,
            ),
            rx.text(title, size="2", color="gray"),
            spacing="1",
            align="center",
        ),
        size="2",
        min_width="150px",
        _hover={"box-shadow": "0 4px 12px rgba(0, 0, 0, 0.1)"},
    )


def stats_cards() -> rx.Component:
    """Render the stats cards using the 'stat_card' component"""
    return rx.hstack(
        stat_card(
            "Total Traces",
            DashboardState.total_traces,
            "bar-chart-2",  # Lucide icon name
            "#3B82F6",
        ),
        stat_card(
            "Total Spans",
            DashboardState.total_spans,
            "git-branch",
            "#8B5CF6",
        ),
        stat_card(
            "Total Tokens",
            DashboardState.formatted_total_tokens,  # pre-formatted for K, M readability of token counts
            "type",
            "#10B981",
        ),
        stat_card(
            "Total Cost",
            DashboardState.formatted_total_cost,  # Pre-formatted for dollar readability
            "dollar-sign",
            "#F59E0B",
        ),
        spacing="4",
        padding="1.5rem",
        justify="center",
        flex_wrap="wrap",
    )
