"""Trace detail page component"""

import reflex as rx
from typing import Dict, Any

from ..state import DashboardState
from .span_tree import span_tree
from .span_gantt import span_gantt


def trace_header() -> rx.Component:
    """Render the trace header with key info."""
    return rx.box(
        rx.vstack(
            # Trace name
            rx.heading(
                DashboardState.trace_name,
                size="6",
            ),
            # Trace ID
            rx.hstack(
                rx.text("ID:", color="gray"),
                rx.code(
                    DashboardState.selected_trace_id,
                    font_size="0.85rem",
                ),
                rx.button(
                    rx.icon("copy", size=14),
                    variant="ghost",
                    size="1",
                    on_click=rx.set_clipboard(DashboardState.selected_trace_id),
                ),
                spacing="2",
            ),
            # Started time
            rx.hstack(
                rx.text("Started:", color="gray"),
                rx.text(DashboardState.trace_start_time_formatted),
                spacing="2",
            ),
            spacing="2",
            align="start",
        ),
        padding="1.5rem",
        background="white",
        border_radius="12px",
        box_shadow="0 2px 8px rgba(0,0,0,0.08)",
        margin_bottom="1rem",
    )


def stat_box(label: str, value: rx.Var, color: str = "inherit") -> rx.Component:
    """Render a stat box component."""
    return rx.box(
        rx.vstack(
            rx.text(label, font_size="0.85rem", color="gray"),
            rx.text(
                value,
                font_size="1.2rem",
                font_weight="bold",
                color=color,
            ),
            spacing="1",
            align="center",
        ),
        padding="1rem",
        background="white",
        border_radius="8px",
        box_shadow="0 1px 4px rgba(0,0,0,0.06)",
        min_width="100px",
    )


def trace_stats() -> rx.Component:
    """Render the trace statistics card."""
    return rx.hstack(
        stat_box("Duration", DashboardState.trace_duration_formatted),
        stat_box("Spans", DashboardState.trace_span_count),
        stat_box("Tokens", DashboardState.trace_total_tokens),
        stat_box("Cost", DashboardState.trace_total_cost, color="#10B981"),
        stat_box("User", DashboardState.trace_user_id),
        spacing="3",
        flex_wrap="wrap",
        margin_bottom="1rem",
    )


def trace_tags() -> rx.Component:
    """Render the trace tags."""
    return rx.cond(
        DashboardState.has_trace_tags,
        rx.hstack(
            rx.text("Tags:", color="gray"),
            rx.foreach(
                DashboardState.trace_tags,
                lambda tag: rx.badge(tag, variant="soft"),
            ),
            spacing="2",
            flex_wrap="wrap",
            margin_bottom="1rem",
        ),
        rx.fragment(),
    )


def trace_output_section() -> rx.Component:
    """Render the trace output section."""
    return rx.cond(
        DashboardState.has_trace_output,
        rx.box(
            rx.text("Trace Output:", size="4", margin_bottom="0.5rem"),
            rx.code_block(
                DashboardState.trace_output,
                language="log",  # Use "log" for plain text output
                wrap_long_lines=True,
            ),
            padding="1rem",
            background="white",
            border_radius="8px",
            margin_top="1rem",
        ),
        rx.fragment(),
    )


def trace_detail() -> rx.Component:
    """Render the main trace detail component."""
    return rx.box(
        rx.cond(
            DashboardState.loading,
            rx.center(rx.spinner(size="3"), padding="4rem"),
            rx.cond(
                DashboardState.has_selected_trace,
                rx.vstack(
                    trace_header(),
                    trace_stats(),
                    trace_tags(),
                    # Span visualisation
                    rx.box(
                        span_gantt(),
                        margin_bottom="1.5rem",
                    ),
                    rx.box(
                        span_tree(),
                    ),
                    # Trace output
                    trace_output_section(),
                    spacing="0",
                    align="stretch",
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("file-x", size=48, color="gray"),
                        rx.text("Trace not found", color="gray"),
                        rx.button(
                            "Go back",
                            variant="soft",
                            on_click=rx.redirect("/"),  # TODO: Redirect to traces home page if doesn't work
                        ),
                        spacing="3",
                        align="center",
                    ),
                    padding="4rem",
                ),
            ),
        ),
        padding="1rem",
    )
