# LLM Tracer Dashboard - Developer Guide

This guide helps new contributors understand the dashboard project structure, key concepts, and how to run it locally.

## Overview

The LLM Tracer Dashboard is a web application built with [Reflex](https://reflex.dev/) (v0.8.24+), a Python framework that compiles to React/Next.js. It provides a visual interface for viewing LLM traces and spans collected by the LLM Tracer service.

## Project Structure

```
dashboard/
├── pyproject.toml           # Python dependencies (uv/pip)
├── rxconfig.py              # Reflex configuration (ports, plugins)
├── .env.example             # Environment variable template
├── .env                     # Local environment variables (not committed)
├── developer_guide.md       # This file
│
└── dashboard/               # Main application package
    ├── __init__.py          # Package marker
    ├── dashboard.py         # App entry point, routes, and pages
    ├── state.py             # Reactive state management (DashboardState)
    ├── api.py               # HTTP client for Tracer API
    │
    └── components/          # Reusable UI components
        ├── __init__.py
        ├── stats_cards.py   # Aggregate statistics display
        ├── trace_list.py    # Paginated trace table
        ├── trace_detail.py  # Single trace view with header/stats
        ├── span_tree.py     # Hierarchical span tree with expand/collapse
        ├── span_gantt.py    # Gantt chart timeline visualization
        └── json_viewer.py   # Collapsible JSON display for span data
```

## Module Descriptions

### Core Modules

#### `rxconfig.py`
Reflex configuration file. Key settings:
- **Ports**: Frontend on `3000`, Backend on `8002` (avoiding 8000/8001 used by tracer service)
- **Plugins**: TailwindV4Plugin, SitemapPlugin
- **API URL**: Internal Reflex backend communication (not the Tracer API)

#### `dashboard/dashboard.py`
Application entry point defining:
- `navbar()` - Navigation bar with health status badge
- `index()` - Home page with stats cards and trace list
- `trace_page()` - Trace detail page with spans visualization
- Route registration via `app.add_page()`

#### `dashboard/state.py`
Central state management class `DashboardState(rx.State)`. Contains:
- **Base state variables**: `traces`, `selected_trace`, `selected_spans`, `loading`, etc.
- **Data loading methods**: `load_traces()`, `load_trace_detail()`, `refresh()`
- **Computed vars**: Pre-formatted values for UI rendering
- **Event handlers**: `toggle_span()`, `expand_all_spans()`, `clear_selection()`
- **Helper methods**: `_format_duration()`, `_safe_int()`, `_safe_float()`

#### `dashboard/api.py`
Async HTTP client using `httpx` for communicating with the Tracer API:
- `get_stats()` - Fetch aggregate statistics
- `get_traces()` - Fetch paginated trace list
- `get_trace_detail()` - Fetch single trace with spans
- `check_health()` - Health check endpoint

### UI Components

#### `components/stats_cards.py`
Displays aggregate metrics (total traces, spans, tokens, cost) in card format.

#### `components/trace_list.py`
Paginated table of traces with columns: Name, Duration, Spans, Cost, When, Tags. Supports "Load more" pagination.

#### `components/trace_detail.py`
Header section showing trace metadata, statistics row, tags, and trace output.

#### `components/span_tree.py`
Hierarchical span visualization with:
- Expand/collapse individual spans
- Expand All / Collapse All buttons
- Color-coded span types with icons
- Input/output data display using JSON viewer

#### `components/span_gantt.py`
Timeline visualization showing span execution as horizontal bars with positioning based on relative start times.

#### `components/json_viewer.py`
Collapsible accordion for displaying JSON data:
- `json_viewer()` - For static Python dicts
- `json_viewer_var()` - For `rx.Var[Dict]` objects from state

## Key Reflex Concepts

Understanding these concepts is essential for working with Reflex:

### 1. `rx.Var` Objects

Reflex components render to JavaScript/React. Python operations like `len()`, `.get()`, f-strings do **not** work on `rx.Var` objects at runtime.

```python
# WRONG - won't work in components
rx.text(f"Count: {len(state.items)}")

# CORRECT - pre-compute in state as computed var
@rx.var(cache=True)
def item_count(self) -> int:
    return len(self.items)

# Then use in component
rx.text(DashboardState.item_count)
```

### 2. Computed Variables

Use `@rx.var(cache=True)` decorator to pre-compute values that components need:

```python
@rx.var(cache=True)
def formatted_cost(self) -> str:
    """Pre-format cost for display."""
    return f"${self.total_cost:.2f}"
```

### 3. Conditional Rendering with `rx.cond`

Never use Python ternary operators in components. Use `rx.cond()`:

```python
# WRONG
rx.text("Yes" if state.is_active else "No")

# CORRECT
rx.cond(
    DashboardState.is_active,
    rx.text("Yes"),
    rx.text("No"),
)
```

### 4. Dynamic Icons with `rx.match`

`rx.icon()` requires static strings at compile time. For dynamic icons based on state:

```python
def span_type_icon(span_type: rx.Var[str]) -> rx.Component:
    return rx.match(
        span_type,
        ("llm", rx.icon("bot", size=14)),
        ("tool", rx.icon("wrench", size=14)),
        rx.icon("circle", size=14),  # Default
    )
```

### 5. Iterating with `rx.foreach`

Use `rx.foreach()` instead of Python list comprehensions:

```python
rx.foreach(
    DashboardState.formatted_traces,
    lambda trace: trace_row(trace),
)
```

### 6. Event Handlers

Async methods for data loading, sync methods for state changes:

```python
# Async for API calls
async def load_traces(self) -> None:
    self.loading = True
    data = await api.get_traces()
    self.traces = data.get("traces", [])
    self.loading = False

# Sync for UI state changes
def toggle_span(self, span_id: str) -> None:
    if span_id in self.expanded_spans:
        self.expanded_spans.remove(span_id)
    else:
        self.expanded_spans.append(span_id)
```

## Local Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Node.js 18+ (Reflex handles this automatically)
- LLM Tracer service running on `localhost:8001`

### Installation

1. **Clone and navigate to dashboard:**
   ```bash
   cd llm-tracer/dashboard
   ```

2. **Create virtual environment and install dependencies:**
   ```bash
   # Using uv (recommended)
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e .

   # Or using pip
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env if your tracer service runs on a different port
   ```

### Running the Dashboard

```bash
# Development mode with hot reload
reflex run

# Or explicitly specify mode
reflex run --env dev
```

The dashboard will be available at:
- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8002

### Common Reflex Commands

```bash
# Start development server
reflex run

# Initialize a new Reflex project (already done)
reflex init

# Build for production
reflex export

# Check Reflex version
reflex --version

# View all commands
reflex --help
```

### Troubleshooting

#### Port conflicts
If ports 3000 or 8002 are in use, modify `rxconfig.py`:
```python
frontend_port=3001,
backend_port=8003,
```

#### API connection issues
1. Ensure LLM Tracer service is running on port 8001
2. Check `TRACER_API_URL` in `.env`
3. Verify API key matches: `TRACER_API_KEY=project-dev`

#### Reflex compilation errors
```bash
# Clear cache and rebuild
rm -rf .web
reflex run
```

#### Type errors with rx.Var
Remember: you cannot use Python methods on `rx.Var` objects. Pre-compute values in state using `@rx.var(cache=True)`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TRACER_API_URL` | LLM Tracer API endpoint | `http://localhost:8001` |
| `TRACER_API_KEY` | API key for authentication | `project-dev` |
| `REFLEX_API_URL` | Reflex internal backend URL | `http://localhost:8002` |
| `REFLEX_LOG_LEVEL` | Logging verbosity | `debug` |

## Architecture Notes

### State Management Pattern

All UI data flows through `DashboardState`:

```
API Response → State Variables → Computed Vars → Components
```

This ensures:
1. API data is stored in base state variables
2. Formatting/transformation happens in computed vars
3. Components receive ready-to-render values

### Data Flow Example

```
User clicks trace → load_trace_detail(trace_id)
                         ↓
              API call: GET /api/traces/{id}
                         ↓
        State update: self.selected_trace = data["trace"]
                      self.selected_spans = data["spans"]
                         ↓
          Computed vars recalculate: flattened_spans, gantt_spans
                         ↓
              Components re-render with new data
```

### Denormalized Data

The Tracer API returns denormalized data on traces (`span_count`, `total_cost`) to avoid N+1 queries. The dashboard relies on these pre-computed values for the trace list display.

## Contributing

1. Follow the existing code patterns for state management
2. Always pre-compute values needed by components as computed vars
3. Use `rx.cond()` for conditional rendering, never Python conditionals
4. Use `rx.match()` for dynamic icon selection
5. Add type hints to all functions
6. Document complex computed vars with docstrings
