"""Gantt chart timeline visualisation for spans.

Uses pure CSS/HTML for Gantt chart to avoid JS dependenceis.
All positioning and styling is pre-computed in DashboardState.gantt_spans.
"""

import reflex as rx
from typing import Dict, Any

from ..state import DashboardState


def gantt_bar(span: rx.Var[Dict[str, Any]]) -> rx.Component:
    """Render a single Gantt bar.

    Parameters
    ----------
    span : rx.Var[Dict[str, Any]]
        Enriched span from gantt_spans computed var with:
        - style_color: Color for the bar
        - left_pct_str: CSS left position (e.g., "25%")
        - width_pct_str: CSS width (e.g., "10%")
        - name_truncated: Truncated name for label
        - tooltip_text: Pre-formatted tooltip content

    """
    return rx.box(
        rx.hstack(
            # Label on left
            rx.box(
                rx.text(
                    span["name_truncated"],
                    font_size="0.75rem",
                    white_space="nowrap",
                    overflow="hidden",
                    text_overflow="ellipsis",
                ),
                width="150px",
                flex_shrink="0",
                padding_right="0.5rem",
            ),
            # Gantt bar area
            rx.box(
                rx.tooltip(
                    rx.box(
                        position="absolute",
                        left=span["left_pct_str"],
                        width=span["width_pct_str"],
                        height="20px",
                        top="50%",
                        transform="translateY(-50%)",
                        background=span["style_color"],
                        border_radius="4px",
                        cursor="pointer",
                        _hover={"opacity": "0.8"},
                    ),
                    content=span["tooltip_text"],
                ),
                position="relative",
                flex="1",
                height="28px",
                background="#F3F4F6",
                border_radius="4px",
                overflow="hidden",
            ),
            width="100%",
            align="center",
        ),
        margin_bottom="4px",
    )


def time_axis() -> rx.Component:
    """Render the time axis labels.

    Uses pre computed vars from DashboardState for end labels.
    """
    return rx.hstack(
        rx.box(width="150px", flex_shrink="0"),   # Match label width
        rx.hstack(
            rx.text("0", font_size="0.7rem", color="gray"),
            rx.spacer(),
            rx.text(
                DashboardState.gantt_time_axis_end_label,
                font_size="0.7rem",
                color="gray",
            ),
            width="100%",
        ),
        width="100%",
        padding_bottom="0.5rem",
        border_bottom="1px solid #E5E7EB",
        margin_bottom="0.5rem",
    )


def span_gantt() -> rx.Component:
    """Render the main span Gantt Chart Component."""
    return rx.box(
        rx.hstack(
            rx.heading("Span Timeline", size="4"),
            rx.spacer(),
            rx.badge("Gantt View", variant="soft"),
            margin_bottom="1rem",
            align="center",
        ),
        rx.cond(
            DashboardState.has_gantt_spans,
            rx.box(
                # Time axis
                time_axis(),
                # Gantt bars
                rx.foreach(
                    DashboardState.gantt_spans,
                    gantt_bar,
                ),
                padding="1rem",
                background="white",
                border_radius="8px",
                border="1px solid #E5E7EB",
            ),
            rx.center(
                rx.vstack(
                    rx.icon("clock", size=32, color="gray"),
                    rx.text("No spans to display", color="gray"),
                    spacing="2",
                    align="center",
                ),
                padding="2rem",
            ),
        ),
    )
