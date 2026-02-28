"""Shared ANSI color helpers for setup output."""

import os
import sys

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"


def use_color() -> bool:
    """Return True if stdout supports ANSI color."""
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def color(text: str, code: str) -> str:
    """Wrap text in ANSI color code if color is enabled."""
    if not use_color():
        return text
    return f"{code}{text}{RESET}"
