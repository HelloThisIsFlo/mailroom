"""Output formatting for the setup command with terraform-style resource tables."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from mailroom.setup.colors import GREEN, YELLOW, RED, DIM, RESET, CYAN, use_color, color


@dataclass
class ResourceAction:
    """A single resource to provision with its current status."""

    kind: str  # "mailbox", "label", "contact_group", "mailroom"
    name: str  # Display name (e.g., "Feed", "@ToFeed")
    status: str  # "exists", "create", "created", "failed", "skipped"
    parent: str | None = None  # For mailbox hierarchy display
    error: str | None = None  # Inline error reason for failures


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
    "exists": GREEN,
    "create": YELLOW,
    "created": GREEN,
    "failed": RED,
    "skipped": DIM,
}


def _format_status(action: ResourceAction) -> str:
    """Format the status column for a resource action with color."""
    if action.status == "failed" and action.error:
        return color(f"FAILED: {action.error}", RED)
    if action.status == "skipped" and action.error:
        return color(f"skipped ({action.error})", DIM)
    if action.status == "exists":
        return color("exists", DIM)
    if action.status == "create":
        return color("create", YELLOW)
    if action.status == "created":
        return color("created", GREEN)
    return action.status


def _print_section(title: str, actions: list[ResourceAction], out: object) -> None:
    """Print a single section (Mailboxes, Action Labels, Contact Groups, Mailroom)."""
    if not actions:
        return
    print(title, file=out)
    for action in actions:
        symbol = _SYMBOLS.get(action.status, "?")
        color_code = _SYMBOL_COLORS.get(action.status)
        colored_symbol = color(symbol, color_code) if color_code else symbol
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
