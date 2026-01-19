"""Collapsible JSON viewer component"""

import reflex as rx
import json
from typing import Dict, Any


def json_viewer(
    data: dict,
    title: str = "Data",
    max_height: str = "300px", 
) -> rx.Component:
    """Render a collapsible JSON viewer for static Python Dicts.

    Use this when data is a regular Python dict available at compile time.
    
    Parameters
    ----------
    data : dict
        Dictionary data to display.
    title : str, optional
        Section Title.
    max_height : str, optional
        The maximum height before scroll.
    """
    if not data:
        return rx.text("No data", color="gray", font_style="italic")
    
    try:
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
    except:
        formatted = str(data)
    
    # accordion is a special UI component that organizes content into vertically
    # stacked, collapsible sections - allowing users to expand/collapse sections
    # to view content.
    return rx.accordion.root(
        rx.accordion.item(
            value="json-data",
            header=rx.text(title, weight="medium"),
            content=rx.box(
                rx.code_block(
                    code=formatted,
                    language="json",
                    show_line_numbers=True,
                    wrap_long_lines=True,
                ),
                max_height=max_height,
                overflow_y="auto",
            ),
        ),
        type="multiple",
        variant="ghost",
    )


def json_viewer_var(
    data: rx.Var[Dict[str, Any]],
    title: str = "Data",
    max_height: str = "300px", 
) -> rx.Component:
    """Render a collapsible JSON viewer for rx.Vars.

    Use this when data is an rx.Var[dict] from state or foreach loops.
    Data is serialized at runtime, not compile time.
    
    Parameters
    ----------
    data : rx.Var[Dict[str, Any]]
        Dictionary data to display.
    title : str, optional
        Section Title.
    max_height : str, optional
        The maximum height before scroll.
    """
    return rx.accordion.root(
        rx.accordion.item(
            value="json-data",
            header=rx.text(title, weight="medium"),
            content=rx.box(
                rx.code_block(
                    code=data.to_string(),
                    language="json",
                    show_line_numbers=True,
                    wrap_long_lines=True,
                ),
                max_height=max_height,
                overflow_y="auto",
            ),
        ),
        type="multiple",
        variant="ghost",
    )


def inline_json(data: dict, max_length: int = 100) -> rx.Component:
    """Render inline JSON preview with truncation.
    
    Parameters
    ----------
    data : dict
        Dictionary data to display.
    max_length : int, optional
        Maximum length of JSON string before truncation.
    """
    if not data:
        return rx.text("--", color="gray")
    
    try:
        text = json.dumps(data, ensure_ascii=False)
        if len(text) > max_length:
            text = text[:max_length] + "..."
    except:
        text = str(data)[:max_length] + "..."
    
    return rx.text(
        text,
        font_family="monospace",
        font_size="0.8rem",
        color="gray",
        overflow="hidden",
        text_overflow="ellipsis",
        white_space="nowrap",
    )
