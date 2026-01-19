"""Trace list table component"""

from typing import Dict, Any
import reflex as rx

from ..state import DashboardState


def trace_row(trace: rx.Var[Dict[str, Any]]) -> rx.Component:
    """Single trace row in the list
    
    Parameters
    ----------
    trace : rx.Var[Dict[str, Any]]
        The enriched trace dictionary from formatted_traces computed var in DashboardState.
    """
    return rx.table.row(
        # Name cell with status indicator
        rx.table.cell(
            rx.hstack(
                rx.cond(
                    trace["has_error"],
                    rx.text("⚠️", color="red"),
                    rx.text("✓", color="green"),
                ),
                rx.link(
                    trace["name"],
                    href=trace["detail_url"],  # Pre-computed: f"/trace/{trace['trace_id']}"
                    font_weight="500",
                    _hover={"text_decoration": "underline"},
                ),
                spacing="2",
            )
        ),
        # Duration cell - pre formatted
        rx.table.cell(
            trace["duration_formatted"],
            font_family="monospace",
        ),
        # Span count cell
        rx.table.cell(
            trace["span_count_display"],  # pre-computed witg fallback
            text_align="center",
        ),
        # Cost cell (pre-formatted)
        rx.table.cell(
            trace["cost_formatted"],
            font_family="monospace",
        ),
        # Start time cell as relative time (pre-formatted)
        rx.table.cell(
            trace["relative_time"],
            color="gray",
        ),
        # Tags cell (pre-formatted as comma-separated string)
        rx.table.cell(
            rx.cond(
                trace["tags_display"] != "",
                rx.text(trace["tags_display"], font_size="0.85rem", color="gray"),
                rx.text("—", color="gray"),
            )
        ),
        _hover={"background": "#f8f9fa"},
        cursor="pointer"
    )


def trace_list() -> rx.Component:
    """Main trace list component.
    
    This UI component utilizes conditional component creation because
    there could multiple outcomes for displaying traces like still loading,
    or error, or no traces at all.
    """
    return rx.box(
        rx.hstack(
            rx.heading("Recent Traces", size="5"),
            rx.spacer(),
            rx.button(
                rx.icon("refresh-cw", size=16),
                "Refresh",
                on_click=DashboardState.refresh,
                loading=DashboardState.loading,
            ),
            padding="1rem",
            align="center",
        ),
        # conditional component: condition, c1 (if condition is true), c2 (if not)
        # 1st condition: if data is still loading
        rx.cond(
            DashboardState.loading,
            rx.center(rx.spinner(size="3"), padding="2rem"),
            # 2nd condition: if data has loaded and there are traces
            rx.cond(
                DashboardState.has_traces,  # pre-computed var
                rx.box(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Name"),  # name
                                rx.table.column_header_cell("Duration"),  # duration_formatted
                                rx.table.column_header_cell("Spans"),  # span_count_display
                                rx.table.column_header_cell("Cost"),  # cost_formatted
                                rx.table.column_header_cell("When"),  # relative_time
                                rx.table.column_header_cell("Tags"),  # tags_display
                            ),
                        ),
                        rx.table.body(
                            rx.foreach(DashboardState.formatted_traces, trace_row),  # using enriched traces
                        ),
                    ),
                    # 3rd condition: if there are more traces to load
                    rx.cond(
                        DashboardState.has_more,
                        rx.center(
                            rx.button(
                                "Load more",
                                variant="soft",
                                on_click=lambda: DashboardState.load_traces(reset=False),
                                loading=DashboardState.loading,
                            ),
                            padding="1rem",
                        ),
                        # If has_more is false
                        rx.fragment(),
                    ),
                ),
                # if has_traces is false
                rx.center(
                    rx.vstack(
                        rx.icon("inbox", size=48, color="gray"),
                        rx.text("No traces yet", color="gray"),
                        rx.text(
                            "Run your first LLM call to see traces here",
                            font_size="0.85rem",
                            color="gray",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    padding="3rem",
                ),
            ),
        ),
        background="white",
        border_radius="12px",
        box_shadow="0 2px 8px rgba(0, 0, 0, 0.1)",
        margin="1rem",
    )

