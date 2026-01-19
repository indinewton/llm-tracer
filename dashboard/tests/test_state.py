"""Tests for Dashboard state logic.

Tests the pure Python logic in DashboardState without requiring Reflex runtime.
Focuses on formatting functions and data transformations.
"""

import pytest
from datetime import datetime, timezone, timedelta

from dashboard.state import DashboardState, SPAN_STYLES, PLACEHOLDER


class TestSafeInt:
    """Tests for _safe_int helper, used in formatting.

    For all the types of responses that client can get from API,
    this function converts them to int if valid.
    """

    def test_converts_int(self):
        assert DashboardState._safe_int(42) == 42

    def test_converts_string_int(self):
        assert DashboardState._safe_int("123") == 123
    
    def test_returns_zero_for_none(self):
        assert DashboardState._safe_int(None) == 0
    
    def test_returns_zero_for_invalid_string(self):
        assert DashboardState._safe_int("not a number") == 0
    
    def test_returns_zero_for_empty_string(self):
        assert DashboardState._safe_int("") == 0


class TestSafeFloat:
    """Tests for _safe_float helper, used in formatting.
    
    For all the types of responses that client can get from API,
    this function converts them to float if valid.
    """

    def test_converts_float(self):
        assert DashboardState._safe_float(3.14) == 3.14
    
    def test_converts_int_to_float(self):
        assert DashboardState._safe_float(42) == 42.0
    
    def test_converts_string_float(self):
        assert DashboardState._safe_float("1.25") == 1.25
    
    def test_returns_zero_for_none(self):
        assert DashboardState._safe_float(None) == 0
    
    def test_returns_zero_for_invalid_string(self):
        assert DashboardState._safe_float("invalid") == 0


class TestFormatDuration:
    """Tests for _format_duration method."""

    @pytest.fixture
    def state(self):
        """Create a state instance for testing."""
        # We can't fully instantiate DashboardState without Reflex,
        # but we can test the static/instance methods directly
        return DashboardState

    def test_formats_milliseconds(self, state):
        assert state._format_duration(state, 0) == "0ms"
        assert state._format_duration(state, 999) == "999ms"

    def test_formats_seconds(self, state):
        assert state._format_duration(state, 1500) == "1.50s"
        assert state._format_duration(state, 12345) == "12.35s"

    def test_handles_none(self, state):
        assert state._format_duration(state, None) == PLACEHOLDER

    def test_handles_string_input(self, state):
        assert state._format_duration(state, "500") == "500ms"
        assert state._format_duration(state, "2000") == "2.00s"


class TestFormatCost:
    """Tests for _format_cost method."""

    @pytest.fixture
    def state(self):
        return DashboardState

    def test_formats_usd(self, state):
        assert state._format_cost(state, 1.25) == "$1.25"
        assert state._format_cost(state, 0.50) == "$0.50"


    def test_returns_placeholder_for_zero(self, state):
        assert state._format_cost(state, 0) == PLACEHOLDER
        assert state._format_cost(state, 0.0) == PLACEHOLDER

    def test_returns_placeholder_for_none(self, state):
        assert state._format_cost(state, None) == PLACEHOLDER


class TestFormatSpanCount:
    """Tests for _format_span_count method."""

    @pytest.fixture
    def state(self):
        return DashboardState

    def test_formats_count(self, state):
        assert state._format_span_count(state, 5) == "5"
        assert state._format_span_count(state, 0) == "0"

    def test_returns_dashes_for_none(self, state):
        assert state._format_span_count(state, None) == "--"


class TestFormatRelativeTime:
    """Tests for _format_relative_time method."""

    @pytest.fixture
    def state(self):
        return DashboardState

    def test_formats_seconds_ago(self, state):
        now = datetime.now(timezone.utc)
        iso = (now - timedelta(seconds=30)).isoformat()
        assert state._format_relative_time(state, iso) == "< 1m ago"

    def test_formats_minutes_ago(self, state):
        now = datetime.now(timezone.utc)
        iso = (now - timedelta(minutes=5)).isoformat()
        assert state._format_relative_time(state, iso) == "5m ago"

    def test_formats_hours_ago(self, state):
        now = datetime.now(timezone.utc)
        iso = (now - timedelta(hours=3)).isoformat()
        assert state._format_relative_time(state, iso) == "3h ago"

    def test_formats_days_ago(self, state):
        now = datetime.now(timezone.utc)
        iso = (now - timedelta(days=2)).isoformat()
        assert state._format_relative_time(state, iso) == "2d ago"

    def test_returns_dashes_for_none(self, state):
        assert state._format_relative_time(state, None) == "--"

    def test_returns_dashes_for_empty(self, state):
        assert state._format_relative_time(state, "") == "--"


class TestBuildSpanTree:
    """Tests for _build_span_tree method."""

    @pytest.fixture
    def state(self):
        return DashboardState

    def test_builds_flat_list_as_roots(self, state):
        """Spans without parents become roots."""
        spans = [
            {"span_id": "a", "parent_span_id": None},
            {"span_id": "b", "parent_span_id": None},
        ]

        tree = state._build_span_tree(state, spans)

        assert len(tree) == 2
        assert tree[0]["span_id"] == "a"
        assert tree[1]["span_id"] == "b"
    
    def test_builds_parent_child_relationship(self, state):
        """Child spans are nested under parents."""
        spans = [
            {"span_id": "parent", "parent_span_id": None},
            {"span_id": "child", "parent_span_id": "parent"},
        ]

        tree = state._build_span_tree(state, spans)

        assert len(tree) == 1
        assert tree[0]["span_id"] == "parent"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["span_id"] == "child"
    
    def test_builds_deep_hierarchy(self, state):
        """Supports multiple nesting levels."""
        spans = [
            {"span_id": "root", "parent_span_id": None},
            {"span_id": "child", "parent_span_id": "root"},
            {"span_id": "grandchild", "parent_span_id": "child"}
        ]

        tree = state._build_span_tree(state, spans)

        assert len(tree) == 1
        
        root = tree[0]
        assert root["span_id"] == "root"
        assert len(root["children"]) == 1

        child = root["children"][0]
        assert child["span_id"] == "child"
        assert len(child["children"]) == 1
        
        grandchild = child["children"][0]
        assert grandchild["span_id"] == "grandchild"

    def test_handles_orphaned_spans(self, state):
        """Spans with missing parents become roots."""
        spans = [
            {"span_id": "orphan", "parent_span_id": "nonexistent"},
        ]

        tree = state._build_span_tree(state, spans)

        assert len(tree) == 1
        assert tree[0]["span_id"] == "orphan"

    def test_handles_empty_list(self, state):
        """Handles empty list of spans."""
        tree = state._build_span_tree(state, [])
        assert len(tree) == 0


class TestSpanStyles:
    """Tests for SPAN_STYLES configuration."""

    def test_all_span_types_have_required_keys(self):
        """Each span type must have color, icon, and bg."""
        required_keys = {"color", "icon", "bg"}
        
        for span_type, style in SPAN_STYLES.items():
            assert required_keys.issubset(style.keys()), (
                f"Span type '{span_type}' is missing keys: {required_keys - style.keys()}"
            )
        
    def test_has_fallback_type(self):
        """Must have 'other' type for unknown span types."""
        assert "other" in SPAN_STYLES, "'other' span type required for unknown span types."

    def test_has_common_span_types(self):
        """Common span types should be defined."""
        common_types = ["llm", "tool", "agent", "function"]
        for span_type in common_types:
            assert span_type in SPAN_STYLES, f"Missing common span type: '{span_type}'."
