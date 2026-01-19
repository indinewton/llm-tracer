"""Hierarchical span tree visualization component.

Note: For developers using reflex for the first time:
- there are subtle differences between python data structures
and rx.Var objects usage. It can look confusing but this python code is
rendered to a JS code using react backend. So some common methods do not
work on rx.Vars objects like len(), get() etc.
----
This component renders spans in a flat list with visual indentation based on 
depth. All styling, formatting, and boolean flags are pre-computed in 
DashboardState.flattened_spans to avoid runtime Python operations on rx.Var 
objects.
"""

import reflex as rx
from typing import Dict, Any

from ..state import DashboardState
from .json_viewer import json_viewer_var


def span_type_icon(span_type: rx.Var[str]) -> rx.Component:
    """Render the appropriate icon for a span type using rx.match.

    Since rx.icon() requires a static string at compile time, we use
    rx.match() to conditionally render the correct icon based on span_type.

    Parameters
    ----------
    span_type : rx.Var[str]
        The span type value (e.g., "llm", "agent", "tool").

    Returns
    -------
    rx.Component
        The appropriate Lucide icon component.
    """
    return rx.match(
        span_type,
        ("llm", rx.icon("bot", size=14)),
        ("agent", rx.icon("user", size=14)),
        ("tool", rx.icon("wrench", size=14)),
        ("function", rx.icon("square-function", size=14)),
        ("retrieval", rx.icon("search", size=14)),
        ("embedding", rx.icon("bar-chart", size=14)),
        ("chain", rx.icon("link", size=14)),
        rx.icon("circle", size=14),  # Default for "other" or unknown
    )


def span_header(span: rx.Var[Dict[str, Any]]) -> rx.Component:
    """Render the clickable span header.
    
    Parameters
    ----------
    span : rx.Var[Dict[str, Any]]
        The enriched span dictionary from flattened_spans computed var.
        Contains pre-computed: style_bg, style_color, style_icon, 
        border_left_style, duration_formatted, cost_formatted, 
        has_error, has_cost, etc.
    """
    span_id = span["span_id"]  # rx.Var does not support get()
    is_expanded = DashboardState.expanded_spans_set.contains(span_id)

    return rx.hstack(
        # Expand/Collapse icon - use rx.cond, not python ternary
        rx.cond(
            is_expanded,
            rx.text("▼", font_size="0.7rem", color="gray", width="1rem"),
            rx.text("▶", font_size="0.7rem", color="gray", width="1rem"),
        ),
        # Span type icon and badge - use rx.match for dynamic icon selection
        rx.badge(
            rx.hstack(
                span_type_icon(span["span_type"]),
                rx.text(span["span_type"]),
                spacing="1",
                align="center",
            ),
            color_scheme="gray",
            variant="soft",
        ),
        # Span name - color changes if has_error
        rx.text(
            span["name"],
            weight="medium",
            color=rx.cond(span["has_error"], "red", "inherit"),
        ),
        rx.spacer(),
        # Duration (pre-formatted in State)
        rx.text(
            span["duration_formatted"],
            font_family="monospace",
            font_size="0.85rem",
            color="gray",
        ),
        # Cost (pre-formatted in State, shown only if has_cost)
        rx.cond(
            span["has_cost"],
            rx.text(
                span["cost_formatted"],
                font_family="monospace",
                font_size="0.85rem",
                color="#10B981",
            ),
            rx.fragment(),
        ),
        # Error indicator
        rx.cond(
            span["has_error"],
            rx.badge("Error", color_scheme="red", variant="solid"),
            rx.fragment(),
        ),
        width="100%",
        padding="0.5rem 1rem",
        background=span["style_bg"],  # Pre-computed in state
        border_left=span["border_left_style"],
        border_radius="4px",
        cursor="pointer",
        _hover={"opacity": "0.9"},
        align="center",
    )


def span_details(span: rx.Var[Dict[str, Any]]) -> rx.Component:
    """Render expanded span details.
    
    Parameters
    ----------
    span : rx.Var[Dict[str, Any]]
        The enriched span dictionary from flattened_spans computed var.
        Contains pre-computed boolean flags for conditional rendering.
    """
    return rx.box(
        rx.vstack(
            # Model info (if LLM span)
            rx.cond(
                span["has_model"],
                rx.hstack(
                    rx.text("Model:", weight="medium", width="80px"),
                    rx.code(span["model"]),
                    spacing="2",
                ),
                rx.fragment(),
            ),
            # Token counts
            rx.cond(
                span["has_tokens"],
                rx.hstack(
                    rx.text("Tokens:", weight="medium", width="80px"),
                    rx.hstack(
                        rx.text(span["tokens_input"]),
                        rx.text(" in /"),
                        rx.text(span["tokens_output"]),
                        rx.text(" out"),
                        spacing="1",
                    ),
                    spacing="2",
                ),
                rx.fragment(),
            ),
            # Error message
            rx.cond(
                span["has_error"],
                rx.box(
                    rx.text("Error:", weight="medium", color="red"),
                    rx.code(span["error"], color_scheme="red"),
                    padding="0.5rem",
                    border_radius="4px",
                    background="#FEF2F2",
                    width="100%",
                ),
                rx.fragment(),
            ),
            # Input data - use json_viewer_var that handled Var objects
            rx.cond(
                span["has_input_data"],
                json_viewer_var(span["input_data"], "Input Data"),
                rx.fragment(),
            ),
            # Output data
            rx.cond(
                span["has_output_data"],
                json_viewer_var(span["output_data"], "Output Data"),
                rx.fragment(),
            ),
            # Metadata
            rx.cond(
                span["has_metadata"],
                json_viewer_var(span["metadata"], "Metadata"),
                rx.fragment(),
            ),
            spacing="3",
            align="stretch",
            width="100%",
        ),
        padding="1rem",
        padding_left="2rem",
        background="#FAFAFA",
        border_left="1px solid #E5E7EB",
        margin_left="0.5rem",
    )


def render_span_node(span: rx.Var[Dict[str, Any]]) -> rx.Component:
    """Render a single span item (flat list approach, no recursion).

    The span tree is flattened in DashboardState.flattened_spans with depth info,
    so we render a flat list with visual indentation based on depth.

    Parameters
    ----------
    span : rx.Var[Dict[str, Any]]
        The enriched span dictionary from flattened_spans.
    """
    span_id = span["span_id"]
    # Check if span is expanded
    is_expanded = DashboardState.expanded_spans_set.contains(span_id)
    depth = span["depth"]  # used for indentation during viewing in tree

    return rx.box(
        # Span header - clickable to toggle expansion
        rx.box(
            span_header(span),
            on_click=lambda: DashboardState.toggle_span(span_id),
        ),
        # Expanded details - shown only when expanded
        rx.cond(
            is_expanded,
            span_details(span),
            rx.fragment(),
        ),
        margin_bottom="0.5rem",
        # Indent based on depth using margin_left (pre-computed in state)
        margin_left=span["margin_left_style"],
    )


def span_tree() -> rx.Component:
    """Main span tree component.
    
    Renders the hierarchical span tree as a flattened list with visual
    indentation. Uses DashboardState.flattened_spans which contains pre-
    computed styling and formatting for each span.
    """
    return rx.box(
        # header with expand/collaps controls
        rx.hstack(
            rx.heading("Span Details", size="4"),
            rx.spacer(),
            rx.hstack(
                rx.button(
                    rx.icon("chevrons-down", size=16),
                    rx.text("Expand All"),
                    variant="ghost",
                    size="1",
                    on_click=DashboardState.expand_all_spans,
                ),
                rx.button(
                    rx.icon("chevrons-up", size=16),
                    rx.text("Collapse All"),
                    variant="ghost",
                    size="1",
                    on_click=DashboardState.collapse_all_spans,
                ),
                spacing="2",
            ),
            width="100%",
            margin_bottom="1rem",
            align="center",
        ),
        # Span list
        rx.cond(
            DashboardState.has_selected_spans,
            rx.box(
                rx.foreach(
                    DashboardState.flattened_spans,
                    render_span_node,
                ),
            ),
            rx.center(
                rx.vstack(
                    rx.icon("inbox", size=48, color="gray"),
                    rx.text("No spans found", color="gray"),
                    spacing="2",
                    align="center",
                ),
                padding="2rem",
            ),
        ),
    )
