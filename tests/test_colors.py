"""Tests for the shared ANSI color helpers module."""

from __future__ import annotations

from mailroom.setup.colors import GREEN, YELLOW, RED, DIM, RESET, CYAN, use_color, color


class TestUseColor:
    """Tests for the use_color() function."""

    def test_returns_false_when_no_color_env_set(self, monkeypatch) -> None:
        """NO_COLOR env var disables color output."""
        monkeypatch.setenv("NO_COLOR", "1")
        assert use_color() is False

    def test_returns_false_when_not_tty(self, monkeypatch) -> None:
        """Non-TTY stdout disables color output."""
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        assert use_color() is False

    def test_returns_true_when_tty(self, monkeypatch) -> None:
        """TTY stdout with no NO_COLOR enables color output."""
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert use_color() is True


class TestColor:
    """Tests for the color() wrapping function."""

    def test_wraps_text_when_color_enabled(self, monkeypatch) -> None:
        """Text is wrapped in ANSI codes when color is enabled."""
        monkeypatch.setattr("mailroom.setup.colors.use_color", lambda: True)
        result = color("hello", GREEN)
        assert result == f"{GREEN}hello{RESET}"

    def test_returns_plain_text_when_color_disabled(self, monkeypatch) -> None:
        """Text is returned unchanged when color is disabled."""
        monkeypatch.setattr("mailroom.setup.colors.use_color", lambda: False)
        result = color("hello", GREEN)
        assert result == "hello"


class TestConstants:
    """Tests for ANSI color constants."""

    def test_all_constants_are_ansi_escape_sequences(self) -> None:
        """All color constants start with the ANSI escape prefix."""
        for name, value in [
            ("GREEN", GREEN),
            ("YELLOW", YELLOW),
            ("RED", RED),
            ("DIM", DIM),
            ("RESET", RESET),
            ("CYAN", CYAN),
        ]:
            assert value.startswith("\033["), f"{name} does not start with ANSI escape"
