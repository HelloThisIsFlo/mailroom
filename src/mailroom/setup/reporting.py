"""Output formatting for the setup command with terraform-style resource tables."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


@dataclass
class ResourceAction:
    """A single resource to provision with its current status."""

    kind: str  # "mailbox", "label", "contact_group", "mailroom"
    name: str  # Display name (e.g., "Feed", "@ToFeed")
    status: str  # "exists", "create", "created", "failed", "skipped"
    parent: str | None = None  # For mailbox hierarchy display
    error: str | None = None  # Inline error reason for failures


# ANSI color codes
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"


def _use_color() -> bool:
    """Return True if ANSI color should be used."""
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _color(text: str, code: str) -> str:
    """Wrap text in ANSI color if color is enabled."""
    if not _use_color():
        return text
    return f"{code}{text}{_RESET}"


# Status symbols (plain text, colored separately)
_SYMBOLS = {
    "exists": "\u2713",  # checkmark
    "create": "+",
    "created": "\u2713",  # checkmark
    "failed": "\u2717",  # X mark
    "skipped": "\u2298",  # circle-slash
}

# Symbol color mapping
_SYMBOL_COLORS = {
    "exists": _GREEN,
    "create": _YELLOW,
    "created": _GREEN,
    "failed": _RED,
    "skipped": _DIM,
}


def _format_status(action: ResourceAction) -> str:
    """Format the status column for a resource action with color."""
    if action.status == "failed" and action.error:
        return _color(f"FAILED: {action.error}", _RED)
    if action.status == "skipped" and action.error:
        return _color(f"skipped ({action.error})", _DIM)
    if action.status == "exists":
        return _color("exists", _DIM)
    if action.status == "create":
        return _color("create", _YELLOW)
    if action.status == "created":
        return _color("created", _GREEN)
    return action.status


def _print_section(title: str, actions: list[ResourceAction], out: object) -> None:
    """Print a single section (Mailboxes, Action Labels, Contact Groups, Mailroom)."""
    if not actions:
        return
    print(title, file=out)
    for action in actions:
        symbol = _SYMBOLS.get(action.status, "?")
        color_code = _SYMBOL_COLORS.get(action.status)
        colored_symbol = _color(symbol, color_code) if color_code else symbol
        status_text = _format_status(action)
        # Left-align name with padding, right-align status
        print(f"  {colored_symbol} {action.name:<30} {status_text}", file=out)
    print(file=out)


def print_plan(actions: list[ResourceAction], apply: bool) -> None:
    """Print terraform-style resource plan grouped by kind.

    Groups actions into four sections: Mailboxes, Action Labels,
    Contact Groups, Mailroom. Shows colored status symbols and a
    summary line.

    Args:
        actions: List of ResourceAction objects to display.
        apply: Whether this is an apply result (vs. dry-run plan).
    """
    out = sys.stdout

    mailboxes = [a for a in actions if a.kind == "mailbox"]
    labels = [a for a in actions if a.kind == "label"]
    groups = [a for a in actions if a.kind == "contact_group"]
    mailroom = [a for a in actions if a.kind == "mailroom"]

    print(file=out)
    _print_section("Mailboxes", mailboxes, out)
    _print_section("Action Labels", labels, out)
    _print_section("Contact Groups", groups, out)
    _print_section("Mailroom", mailroom, out)

    # Summary line
    existing = sum(1 for a in actions if a.status == "exists")
    failed = sum(1 for a in actions if a.status == "failed")
    skipped = sum(1 for a in actions if a.status == "skipped")

    if apply:
        created = sum(1 for a in actions if a.status == "created")
        parts = [f"{created} created", f"{existing} existing"]
    else:
        to_create = sum(1 for a in actions if a.status == "create")
        parts = [f"{to_create} to create", f"{existing} existing"]

    if failed:
        parts.append(f"{failed} failed")
    if skipped:
        parts.append(f"{skipped} skipped")

    print(" \u00b7 ".join(parts), file=out)
