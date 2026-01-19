"""Dashboard state management for LLM Tracer.

This module contains the reactive state class for the Reflex dashboard application.
It manages all UI state, data fetching, and computed properties needed for rendering
components without runtime Python operations on rx.Var objects.

The state is organized into logical sections:
    - Base State Variables: Raw data from API
    - Data Loading Methods: Async methods to fetch data
    - Computed Vars by Component: Pre-computed values for each UI component
    - Event Handlers: User interaction handlers
    - Helper Methods: Internal utility functions

Note
----
Reflex components cannot use Python methods like `.get()`, `len()`, or f-strings
on rx.Var objects at runtime. All such operations must be pre-computed in state
as computed vars (decorated with @rx.var).
"""

import reflex as rx
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import api


# =============================================================================
# CONSTANTS
# =============================================================================

# Visual styling configuration for different span types.
#
# Each span type maps to a dict containing:
#     - color: Border and accent color (hex)
#     - icon: Lucide icon name for the span type
#     - bg: Background color (hex)
SPAN_STYLES: Dict[str, Dict[str, str]] = {
    "llm": {"color": "#3B82F6", "icon": "bot", "bg": "#EFF6FF"},
    "agent": {"color": "#8B5CF6", "icon": "user-secret", "bg": "#F5F3FF"},
    "tool": {"color": "#10B981", "icon": "wrench", "bg": "#ECFDF5"},
    "function": {"color": "#F59E0B", "icon": "function-square", "bg": "#FFFBEB"},
    "retrieval": {"color": "#06B6D4", "icon": "search", "bg": "#ECFEFF"},
    "embedding": {"color": "#EC4899", "icon": "bar-chart", "bg": "#FDF2F8"},
    "chain": {"color": "#EAB308", "icon": "link", "bg": "#FEFCE8"},
    "other": {"color": "#6B7280", "icon": "circle", "bg": "#F9FAFB"},
}

# Default placeholder for missing values
PLACEHOLDER = "—"


# =============================================================================
# DASHBOARD STATE
# =============================================================================

class DashboardState(rx.State):
    """Reactive state for the LLM Tracer Dashboard.

    This class manages all application state including:
        - Aggregate statistics (traces, spans, tokens, cost)
        - Trace listing with pagination
        - Selected trace details and spans
        - UI state (loading, health, errors)
        - Span tree expansion state

    All data that needs to be displayed in components is pre-processed into
    computed vars to avoid runtime Python operations on Var objects.

    Attributes
    ----------
    total_traces : int
        Total number of traces in the system.
    total_spans : int
        Total number of spans across all traces.
    total_tokens : int
        Aggregate token count (input + output) across all spans.
    total_cost : float
        Aggregate cost in USD across all spans.
    traces : List[Dict[str, Any]]
        List of trace summaries for the trace list view.
    selected_trace : Optional[Dict[str, Any]]
        Currently selected trace details.
    selected_spans : List[Dict[str, Any]]
        Spans belonging to the selected trace.
    loading : bool
        Whether a data loading operation is in progress.
    healthy : bool
        Whether the tracer API is healthy/reachable.
    error_message : str
        Current error message to display, if any.
    expanded_spans : List[str]
        List of span IDs that are expanded in the tree view.

    See Also
    --------
    api : Module containing async API client functions.
    """

    # -------------------------------------------------------------------------
    # Base State Variables: Aggregate Statistics
    # -------------------------------------------------------------------------

    total_traces: int = 0
    total_spans: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0

    # -------------------------------------------------------------------------
    # Base State Variables: Trace List (with pagination)
    # -------------------------------------------------------------------------

    traces: List[Dict[str, Any]] = []
    next_cursor: Optional[str] = None
    has_more: bool = False

    # -------------------------------------------------------------------------
    # Base State Variables: Selected Trace & Spans
    # -------------------------------------------------------------------------

    selected_trace: Optional[Dict[str, Any]] = None
    selected_spans: List[Dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # Base State Variables: UI State
    # -------------------------------------------------------------------------

    loading: bool = False
    healthy: bool = True
    error_message: str = ""

    # -------------------------------------------------------------------------
    # Base State Variables: Span Tree View State
    # -------------------------------------------------------------------------

    expanded_spans: List[str] = []

    # =========================================================================
    # DATA LOADING METHODS
    # =========================================================================

    async def load_stats(self) -> None:
        """Load aggregate statistics from the API.

        Fetches total counts for traces, spans, tokens, and cost.
        Updates corresponding state variables on success.
        Sets error_message on failure.
        """
        try:
            data = await api.get_stats()
            self.total_traces = data.get("total_traces", 0)
            self.total_spans = data.get("total_spans", 0)
            self.total_tokens = data.get("total_tokens", 0)
            self.total_cost = data.get("total_cost", 0.0)
        except Exception as e:
            self.error_message = str(e)

    async def load_traces(self, reset: bool = True) -> None:
        """Load paginated list of traces from the API.

        Parameters
        ----------
        reset : bool, optional
            If True, replaces existing traces (default).
            If False, appends to existing traces (for "load more").
        """
        self.loading = True
        try:
            cursor = None if reset else self.next_cursor
            data = await api.get_traces(limit=20, cursor=cursor)

            new_traces = data.get("traces", [])
            if reset:
                self.traces = new_traces
            else:
                self.traces = self.traces + new_traces

            self.next_cursor = data.get("next_cursor")
            self.has_more = data.get("has_more", False)

        except Exception as e:
            self.error_message = str(e)
        finally:
            self.loading = False

    async def load_trace_detail(self, trace_id: str) -> None:
        """Load a single trace with all its spans.

        Parameters
        ----------
        trace_id : str
            The unique identifier of the trace to load.
        """
        self.loading = True
        try:
            data = await api.get_trace_detail(trace_id)
            self.selected_trace = data.get("trace")
            self.selected_spans = data.get("spans", [])
            self.expanded_spans = []  # Reset expansion state for new trace
        except Exception as e:
            self.error_message = str(e)
        finally:
            self.loading = False

    async def load_current_trace(self) -> None:
        """Load trace detail based on current route parameters.

        Reads trace_id from URL params and loads the trace.
        Used as on_mount/on_load handler for trace detail page.
        """
        trace_id = self.router.page.params.get("trace_id", "")
        if trace_id:
            await self.load_trace_detail(trace_id)

    async def check_health(self) -> None:
        """Check if the tracer API is healthy and update state."""
        self.healthy = await api.check_health()

    async def refresh(self) -> None:
        """Refresh all dashboard data.

        Performs health check, loads stats, and reloads trace list.
        Used as on_mount handler for the index page.
        """
        await self.check_health()
        await self.load_stats()
        await self.load_traces(reset=True)

    # =========================================================================
    # COMPUTED VARS: Stats Cards Component
    # =========================================================================

    @rx.var(cache=True)
    def formatted_total_tokens(self) -> str:
        """Format total tokens with K/M suffix for display.

        Returns
        -------
        str
            Formatted token count (e.g., "1.5M", "250K", "999").
        """
        value = self.total_tokens
        if value >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        elif value >= 1_000:
            return f"{value / 1_000:.1f}K"
        return str(value)

    @rx.var(cache=True)
    def formatted_total_cost(self) -> str:
        """Format total cost as USD currency.

        Returns
        -------
        str
            Formatted cost (e.g., "$12.34").
        """
        return f"${self.total_cost:.2f}"

    # =========================================================================
    # COMPUTED VARS: Trace List Component
    # =========================================================================

    @rx.var(cache=True)
    def has_traces(self) -> bool:
        """Check if any traces exist.

        Returns
        -------
        bool
            True if traces list is non-empty.
        """
        return len(self.traces) > 0

    @rx.var(cache=True)
    def formatted_traces(self) -> List[Dict[str, Any]]:
        """Enrich traces with pre-formatted values for frontend rendering.

        Adds computed fields to each trace for direct use in components:
            - detail_url: Link to trace detail page
            - duration_formatted: Human-readable duration
            - cost_formatted: USD formatted cost
            - relative_time: Time ago string
            - span_count_display: Span count as string
            - tags_display: First 3 tags
            - has_error: Boolean error flag

        Returns
        -------
        List[Dict[str, Any]]
            List of enriched trace dictionaries.
        """
        result: List[Dict[str, Any]] = []

        for trace in self.traces:
            trace_id = trace.get("trace_id", "")

            enriched_trace = {
                **trace,
                "detail_url": f"/trace/{trace_id}",
                "duration_formatted": self._format_duration(
                    trace.get("duration_ms")
                ),
                "cost_formatted": self._format_cost(trace.get("total_cost")),
                "relative_time": self._format_relative_time(
                    trace.get("start_time")
                ),
                "span_count_display": self._format_span_count(
                    trace.get("span_count")
                ),
                "tags_display": ", ".join((trace.get("tags") or [])[:3]),
                "has_error": bool(trace.get("has_error", False)),
            }
            result.append(enriched_trace)

        return result

    # =========================================================================
    # COMPUTED VARS: Trace Detail Component
    # =========================================================================

    @rx.var(cache=True)
    def has_selected_trace(self) -> bool:
        """Check if a trace is currently selected.

        Returns
        -------
        bool
            True if selected_trace is not None.
        """
        return self.selected_trace is not None

    @rx.var(cache=True)
    def trace_name(self) -> str:
        """Get name of the selected trace.

        Returns
        -------
        str
            Trace name or "Loading..." if not selected.
        """
        if not self.selected_trace:
            return "Loading..."
        return self.selected_trace.get("name", "Unnamed Trace")

    @rx.var(cache=True)
    def selected_trace_id(self) -> str:
        """Get ID of the selected trace.

        Note do not rename it trace_id as it is used in router.

        Returns
        -------
        str
            Trace ID or empty string if not selected.
        """
        if not self.selected_trace:
            return ""
        return self.selected_trace.get("trace_id", "")

    @rx.var(cache=True)
    def trace_start_time_formatted(self) -> str:
        """Get formatted start time of selected trace.

        Returns
        -------
        str
            Formatted datetime (e.g., "Jan 15, 2025 at 02:30:45 PM").
        """
        if not self.selected_trace:
            return PLACEHOLDER

        iso_time = self.selected_trace.get("start_time", "")
        if not iso_time:
            return PLACEHOLDER

        try:
            dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
            return dt.strftime("%b %d, %Y at %I:%M:%S %p")
        except (ValueError, TypeError):
            return iso_time

    @rx.var(cache=True)
    def trace_duration_formatted(self) -> str:
        """Get formatted duration of selected trace.

        Returns
        -------
        str
            Duration in seconds (e.g., "1.23s").
        """
        if not self.selected_trace:
            return PLACEHOLDER
        duration_ms = self._safe_int(self.selected_trace.get("duration_ms"))
        if duration_ms == 0:
            return PLACEHOLDER
        return f"{duration_ms / 1000:.2f}s"

    @rx.var(cache=True)
    def trace_span_count(self) -> int:
        """Get number of spans in selected trace.

        Returns
        -------
        int
            Count of spans in selected_spans list.
        """
        return len(self.selected_spans)

    @rx.var(cache=True)
    def trace_total_tokens(self) -> str:
        """Calculate total tokens across all spans in selected trace.

        Returns
        -------
        str
            Formatted token count or placeholder if none.
        """
        if not self.selected_spans:
            return PLACEHOLDER

        total = sum(
            self._safe_int(span.get("tokens_input", 0))
            + self._safe_int(span.get("tokens_output", 0))
            for span in self.selected_spans
        )

        if total == 0:
            return PLACEHOLDER
        if total >= 1_000_000:
            return f"{total / 1_000_000:.1f}M"
        elif total >= 1_000:
            return f"{total / 1_000:.1f}K"
        return str(total)

    @rx.var(cache=True)
    def trace_total_cost(self) -> str:
        """Calculate total cost across all spans in selected trace.

        Returns
        -------
        str
            Formatted cost (e.g., "$0.0234") or placeholder if none.
        """
        if not self.selected_spans:
            return PLACEHOLDER

        total = sum(self._safe_float(span.get("cost_usd", 0)) for span in self.selected_spans)

        if total == 0:
            return PLACEHOLDER
        return f"${total:.4f}"

    @rx.var(cache=True)
    def trace_user_id(self) -> str:
        """Get user ID associated with selected trace.

        Returns
        -------
        str
            User ID or placeholder if not available.
        """
        if not self.selected_trace:
            return PLACEHOLDER
        return self.selected_trace.get("user_id") or PLACEHOLDER

    @rx.var(cache=True)
    def trace_tags(self) -> List[str]:
        """Get tags from selected trace.

        Returns
        -------
        List[str]
            List of tag strings, empty if none.
        """
        if not self.selected_trace:
            return []
        return self.selected_trace.get("tags", []) or []

    @rx.var(cache=True)
    def has_trace_tags(self) -> bool:
        """Check if selected trace has any tags.

        Returns
        -------
        bool
            True if trace has one or more tags.
        """
        return len(self.trace_tags) > 0

    @rx.var(cache=True)
    def trace_output(self) -> str:
        """Get output/result from selected trace.

        Returns
        -------
        str
            Trace output or empty string if none.
        """
        if not self.selected_trace:
            return ""
        return self.selected_trace.get("output", "") or ""

    @rx.var(cache=True)
    def has_trace_output(self) -> bool:
        """Check if selected trace has output.

        Returns
        -------
        bool
            True if trace has non-empty output.
        """
        return bool(self.trace_output)

    # =========================================================================
    # COMPUTED VARS: Span Tree Component
    # =========================================================================

    @rx.var(cache=True)
    def has_selected_spans(self) -> bool:
        """Check if any spans are selected.

        Returns
        -------
        bool
            True if selected_spans is non-empty.
        """
        return len(self.selected_spans) > 0

    @rx.var(cache=True)
    def expanded_spans_set(self) -> List[str]:
        """Get expanded span IDs for frontend .contains() check.

        Returns
        -------
        List[str]
            List of expanded span IDs.
        """
        return self.expanded_spans

    @rx.var(cache=True)
    def flattened_spans(self) -> List[Dict[str, Any]]:
        """Flatten hierarchical spans with styling and formatting.

        Builds a tree structure from flat spans, then flattens it with
        depth information for indentation. Each span is enriched with:
            - depth: Nesting level (0 = root)
            - style_color, style_icon, style_bg: Visual styling
            - border_left_style: CSS border string
            - duration_formatted: Human-readable duration
            - cost_formatted: USD formatted cost
            - has_*: Boolean flags for conditional rendering

        Returns
        -------
        List[Dict[str, Any]]
            Flattened list of enriched spans in tree order.
        """
        if not self.selected_spans:
            return []

        result: List[Dict[str, Any]] = []

        def flatten(spans: List[Dict[str, Any]], depth: int = 0) -> None:
            """Recursively flatten spans with depth tracking."""
            sorted_spans = sorted(spans, key=lambda s: s.get("start_time", ""))

            for span in sorted_spans:
                span_type = span.get("span_type", "other")
                style = SPAN_STYLES.get(span_type, SPAN_STYLES["other"])
                cost_usd_raw = span.get("cost_usd")
                cost_usd = self._safe_float(cost_usd_raw)

                enriched_span = {
                    **span,
                    # Hierarchy
                    "depth": depth,
                    "margin_left_style": (
                        f"calc({depth} * 1.5rem)" if depth > 0 else "0"
                    ),
                    # Styling
                    "style_color": style["color"],
                    "style_icon": style["icon"],
                    "style_bg": style["bg"],
                    "border_left_style": f"3px solid {style['color']}",
                    # Formatted values
                    "duration_formatted": self._format_duration(
                        span.get("duration_ms")
                    ),
                    "cost_formatted": (
                        f"${cost_usd:.4f}" if cost_usd > 0 else ""
                    ),
                    # Boolean flags for rx.cond
                    "has_error": bool(span.get("error")),
                    "has_model": bool(span.get("model")),
                    "has_tokens": bool(
                        span.get("tokens_input") or span.get("tokens_output")
                    ),
                    "has_cost": cost_usd > 0,
                    "has_input_data": bool(span.get("input_data")),
                    "has_output_data": bool(span.get("output_data")),
                    "has_metadata": bool(span.get("metadata")),
                }
                result.append(enriched_span)

                # Recurse into children
                children = span.get("children", [])
                if children:
                    flatten(children, depth + 1)

        # Build tree, then flatten
        tree = self._build_span_tree(self.selected_spans)
        flatten(tree)
        return result

    # =========================================================================
    # COMPUTED VARS: Span Gantt Component
    # =========================================================================

    @rx.var(cache=True)
    def has_gantt_spans(self) -> bool:
        """Check if spans exist for Gantt chart.

        Returns
        -------
        bool
            True if gantt_spans is non-empty.
        """
        return len(self.selected_spans) > 0 and self.selected_trace is not None

    @rx.var(cache=True)
    def gantt_total_duration_ms(self) -> int:
        """Get total trace duration in milliseconds.

        Returns
        -------
        int
            Duration in ms, or 0 if not available.
        """
        if not self.selected_trace:
            return 0
        return self._safe_int(self.selected_trace.get("duration_ms", 0))

    @rx.var(cache=True)
    def gantt_time_axis_end_label(self) -> str:
        """Format end label for Gantt chart time axis.

        Returns
        -------
        str
            Formatted duration (e.g., "500ms", "1.5s", "10s").
        """
        duration_ms = self.gantt_total_duration_ms
        if duration_ms <= 0:
            return "0"
        elif duration_ms < 1000:
            return f"{duration_ms}ms"
        elif duration_ms < 10000:
            return f"{duration_ms / 1000:.1f}s"
        else:
            return f"{duration_ms / 1000:.0f}s"

    @rx.var(cache=True)
    def gantt_spans(self) -> List[Dict[str, Any]]:
        """Compute Gantt chart layout with positioning for each span.

        Calculates horizontal positioning (left %, width %) for each span
        based on start/end times relative to total trace duration.

        Returns
        -------
        List[Dict[str, Any]]
            List of spans with added positioning and styling:
                - left_pct, width_pct: Numeric percentages
                - left_pct_str, width_pct_str: CSS percentage strings
                - style_color: Bar color
                - name_truncated: Shortened name for label
                - duration_display: Formatted duration
                - tooltip_text: Hover tooltip content
        """
        if not self.selected_spans or not self.selected_trace:
            return []

        trace_start = self.selected_trace.get("start_time")
        if not trace_start:
            return []

        try:
            trace_start_dt = datetime.fromisoformat(
                trace_start.replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            return []

        # Find max end time to determine total duration
        max_end = trace_start_dt
        for span in self.selected_spans:
            end_time = span.get("end_time")
            if end_time:
                try:
                    end_dt = datetime.fromisoformat(
                        end_time.replace("Z", "+00:00")
                    )
                    if end_dt > max_end:
                        max_end = end_dt
                except (ValueError, TypeError):
                    pass

        total_duration = (max_end - trace_start_dt).total_seconds()
        if total_duration <= 0:
            total_duration = 1  # Avoid division by zero

        result: List[Dict[str, Any]] = []

        for span in self.selected_spans:
            span_type = span.get("span_type", "other")
            style = SPAN_STYLES.get(span_type, SPAN_STYLES["other"])

            # Calculate positioning
            try:
                start_time = span.get("start_time", "")
                end_time = span.get("end_time")

                start_dt = datetime.fromisoformat(
                    start_time.replace("Z", "+00:00")
                )
                end_dt = (
                    datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                    if end_time
                    else max_end
                )

                offset = (start_dt - trace_start_dt).total_seconds()
                duration = (end_dt - start_dt).total_seconds()

                left_pct = (offset / total_duration) * 100
                width_pct = max(
                    (duration / total_duration) * 100, 1
                )  # Min 1% width

            except (ValueError, TypeError):
                left_pct = 0
                width_pct = 100

            # Prepare display values
            name = span.get("name", "Unnamed")
            name_truncated = (name[:20] + "...") if len(name) > 20 else name
            duration_display = self._format_duration(span.get("duration_ms"))

            enriched_span = {
                **span,
                # Positioning
                "left_pct": left_pct,
                "width_pct": width_pct,
                "left_pct_str": f"{left_pct}%",
                "width_pct_str": f"{width_pct}%",
                # Styling
                "style_color": style["color"],
                # Display values
                "name_truncated": name_truncated,
                "duration_display": duration_display,
                "tooltip_text": f"{name} | {duration_display} | {span_type}",
            }
            result.append(enriched_span)

        # Sort by start time
        result.sort(key=lambda s: s.get("start_time", ""))
        return result

    # =========================================================================
    # COMPUTED VARS: Navbar Component
    # =========================================================================

    @rx.var(cache=True)
    def health_status_text(self) -> str:
        """Get health status display text.

        Returns
        -------
        str
            "Healthy" if API is reachable, "Offline" otherwise.
        """
        return "Healthy" if self.healthy else "Offline"

    @rx.var(cache=True)
    def health_status_color(self) -> str:
        """Get health status badge color.

        Returns
        -------
        str
            Radix color scheme name ("green" or "red").
        """
        return "green" if self.healthy else "red"

    # =========================================================================
    # COMPUTED VARS: Router
    # =========================================================================

    @rx.var
    def current_trace_id(self) -> str:
        """Get trace_id from current route parameters.

        Returns
        -------
        str
            The trace_id URL parameter, or empty string if not present.
        """
        return self.router.page.params.get("trace_id", "")

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    def toggle_span(self, span_id: str) -> None:
        """Toggle expansion state of a span in tree view.

        Parameters
        ----------
        span_id : str
            The ID of the span to toggle.
        """
        if span_id in self.expanded_spans:
            self.expanded_spans = [
                s for s in self.expanded_spans if s != span_id
            ]
        else:
            self.expanded_spans = self.expanded_spans + [span_id]

    def expand_all_spans(self) -> None:
        """Expand all spans in the tree view."""
        self.expanded_spans = [s["span_id"] for s in self.selected_spans]

    def collapse_all_spans(self) -> None:
        """Collapse all spans in the tree view."""
        self.expanded_spans = []

    def clear_error(self) -> None:
        """Clear the current error message."""
        self.error_message = ""

    def clear_selection(self) -> None:
        """Clear selected trace and reset related state."""
        self.selected_trace = None
        self.selected_spans = []
        self.expanded_spans = []

    # =========================================================================
    # HELPER METHODS (Private)
    # =========================================================================

    @staticmethod
    def _safe_int(val: Any) -> int:
        """Safely convert value to int (handles str, None, etc).

        Parameters
        ----------
        val : Any
            Value to convert.

        Returns
        -------
        int
            Integer value, or 0 if conversion fails.
        """
        if val is None:
            return 0
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _safe_float(val: Any) -> float:
        """Safely convert value to float (handles str, None, etc).

        Parameters
        ----------
        val : Any
            Value to convert.

        Returns
        -------
        float
            Float value, or 0.0 if conversion fails.
        """
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def _format_duration(self, duration_ms: Any) -> str:
        """Format duration in milliseconds to human-readable string.

        Parameters
        ----------
        duration_ms : Any
            Duration in milliseconds (int, str, or None).

        Returns
        -------
        str
            Formatted duration (e.g., "500ms", "1.23s") or placeholder.
        """
        ms = self._safe_int(duration_ms)
        if ms == 0 and duration_ms is None:
            return PLACEHOLDER
        if ms < 1000:
            return f"{ms}ms"
        return f"{ms / 1000:.2f}s"

    def _format_cost(self, cost: Any) -> str:
        """Format cost as USD currency string.

        Parameters
        ----------
        cost : Any
            Cost in USD (float, str, or None).

        Returns
        -------
        str
            Formatted cost (e.g., "$1.23") or placeholder.
        """
        c = self._safe_float(cost)
        if c == 0:
            return PLACEHOLDER
        return f"${c:.2f}"

    def _format_span_count(self, count: Optional[int]) -> str:
        """Format span count for display.

        Parameters
        ----------
        count : Optional[int]
            Span count, or None.

        Returns
        -------
        str
            Count as string or "--" if None.
        """
        return str(count) if count is not None else "--"

    def _format_relative_time(self, iso_time: Optional[str]) -> str:
        """Format ISO timestamp to relative time string.

        Parameters
        ----------
        iso_time : Optional[str]
            ISO 8601 timestamp string, or None.

        Returns
        -------
        str
            Relative time (e.g., "5m ago", "2h ago", "3d ago") or "--".
        """
        if not iso_time:
            return "--"

        try:
            dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
            now = datetime.now(dt.tzinfo)
            diff = now - dt

            seconds = diff.total_seconds()
            if seconds < 60:
                return "< 1m ago"
            elif seconds < 3600:
                return f"{int(seconds // 60)}m ago"
            elif seconds < 86400:
                return f"{int(seconds // 3600)}h ago"
            else:
                return f"{int(seconds // 86400)}d ago"

        except (ValueError, TypeError):
            return str(iso_time)[:16] if iso_time else "--"

    def _build_span_tree(
        self, spans: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build hierarchical tree structure from flat span list.

        Parameters
        ----------
        spans : List[Dict[str, Any]]
            Flat list of spans with span_id and parent_span_id fields.

        Returns
        -------
        List[Dict[str, Any]]
            List of root spans, each with a "children" list containing
            nested child spans.
        """
        if not spans:
            return []

        # Create lookup map with children lists
        span_map: Dict[str, Dict[str, Any]] = {
            s["span_id"]: {**s, "children": []} for s in spans
        }
        roots: List[Dict[str, Any]] = []

        # Build tree by linking children to parents
        for span in spans:
            span_id = span["span_id"]
            parent_id = span.get("parent_span_id")

            if parent_id and parent_id in span_map:
                span_map[parent_id]["children"].append(span_map[span_id])
            else:
                roots.append(span_map[span_id])

        return roots
