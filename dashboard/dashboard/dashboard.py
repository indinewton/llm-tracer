"""Main Dashboard application."""

import reflex as rx

from .state import DashboardState
from .components import stats_cards, trace_list, trace_detail


def navbar(show_back: bool = False) -> rx.Component:
    """Navigation bar.

    Parameters
    ----------
    show_back : bool
        Whether to show the back link instead of title.
    """
    return rx.hstack(
        rx.cond(
            show_back,
            rx.link(
                rx.hstack(
                    rx.icon("arrow_left", size=16),
                    rx.text("Back"),
                    spacing="1",
                    align="center",
                ),
                href="/",
                on_click=DashboardState.clear_selection,
            ),
            rx.hstack(
                rx.icon("search", size=20),
                rx.text("LLM Tracer Dashboard", font_weight="bold"),
                spacing="2",
                align="center",
            ),
        ),
        rx.spacer(),
        # health status badge
        rx.badge(
            DashboardState.health_status_text,
            color_scheme=DashboardState.health_status_color,
        ),
        padding="1rem",
        border_bottom="1px solid #eee",
        width="100%",
        align="center",
    )


def index() -> rx.Component:
    """Home page: trace list."""
    return rx.box(
        navbar(),
        stats_cards.stats_cards(),
        trace_list.trace_list(),
        on_mount=DashboardState.refresh,
        min_height="100vh",
        background="#f5f5f5",
    )


def trace_page() -> rx.Component:
    """Trace detail page."""
    return rx.box(
        navbar(show_back=True),
        trace_detail.trace_detail(),
        on_mount=DashboardState.load_current_trace,
        min_height="100vh",
        background="#f5f5f5",
    )


# Health check endpoint for Docker healthcheck
@rx.api("/ping")
def ping():
    """Health check endpoint for container orchestration."""
    return {"status": "ok"}


# App configuration
app = rx.App(
    theme=rx.theme(
        accent_color="teal",
        radius="medium",
    ),
)

app.add_page(index, route="/", title="LLM Tracer Dashboard")
app.add_page(
    trace_page,
    route="/trace/[trace_id]",
    title="Trace Detail",
    on_load=DashboardState.load_current_trace,  # Alternative to on_mount, as reflex supports it at page level
)
