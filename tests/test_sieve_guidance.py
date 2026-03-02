"""Tests for sieve rule guidance generation."""

from __future__ import annotations

import pytest

from mailroom.core.config import MailroomSettings, TriageCategory
from mailroom.setup.sieve_guidance import generate_sieve_guidance


@pytest.fixture
def settings(monkeypatch):
    """Create MailroomSettings with required env vars set."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "test-token")
    monkeypatch.setenv("MAILROOM_CARDDAV_USERNAME", "test")
    monkeypatch.setenv("MAILROOM_CARDDAV_PASSWORD", "test")
    return MailroomSettings()


class TestGenerateGuidanceDefaultMode:
    """Tests for default sieve-snippet mode (ui_guide=False)."""

    def test_header_present(self, settings) -> None:
        """Output starts with 'Sieve Rules' header."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert "Sieve Rules" in output

    def test_feed_category(self, settings) -> None:
        """Feed category shows contact group condition and folder action."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Feed"' in output
        assert 'Move to folder "Feed"' in output

    def test_imbox_category(self, settings) -> None:
        """Imbox category shows action mentioning Imbox mailbox (v1.2: own derived name)."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Imbox"' in output
        assert 'Move to folder "Imbox"' in output

    def test_paper_trail_category(self, settings) -> None:
        """Paper Trail category is present."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Paper Trail"' in output
        assert 'Move to folder "Paper Trail"' in output

    def test_jail_category(self, settings) -> None:
        """Jail category is present."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Jail"' in output
        assert 'Move to folder "Jail"' in output

    def test_person_skipped(self, settings) -> None:
        """Person (child of Imbox) does NOT appear as a separate rule section."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        # Person should not appear as a category heading in the per-category rules
        lines = output.split("\n")
        category_headings = [
            line.strip()
            for line in lines
            if line.strip()
            and not line.strip().startswith("#")
            and not line.strip().startswith("Condition:")
            and not line.strip().startswith("Action:")
            and not line.strip().startswith("Step")
            and not line.strip().startswith("Note:")
            and not line.strip().startswith("Routing")
            and not line.strip().startswith("These")
            and not line.strip().startswith("Settings")
            and not line.strip().startswith("require")
            and not line.strip().startswith("if ")
            and not line.strip().startswith("{")
        ]
        # Person should not be a standalone heading
        assert "Person" not in category_headings

    def test_screener_catch_all(self, settings) -> None:
        """Screener catch-all section is present with correct mailbox name."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert "Screener catch-all rule:" in output
        assert "Screener" in output
        assert 'Move to folder "Screener"' in output
        assert "LAST" in output

    def test_sieve_reference_snippets(self, settings) -> None:
        """Output contains sieve reference with fileinto and jmapquery."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert "fileinto" in output
        assert "jmapquery" in output


class TestGenerateGuidanceUIGuideMode:
    """Tests for Fastmail UI guide mode (ui_guide=True)."""

    def test_header_present(self, settings) -> None:
        """Output starts with 'Sieve Rules' header."""
        output = generate_sieve_guidance(settings, ui_guide=True)
        assert "Sieve Rules" in output

    def test_filters_and_rules_reference(self, settings) -> None:
        """Output mentions Filters & Rules UI navigation."""
        output = generate_sieve_guidance(settings, ui_guide=True)
        assert "Filters & Rules" in output

    def test_per_category_steps(self, settings) -> None:
        """Per-category steps mention contact group condition and Move to folder."""
        output = generate_sieve_guidance(settings, ui_guide=True)
        assert "contact group" in output
        assert "Move to folder" in output

    def test_screener_catch_all_with_last(self, settings) -> None:
        """Screener catch-all mentions LAST ordering."""
        output = generate_sieve_guidance(settings, ui_guide=True)
        assert "LAST" in output
        assert "Screener" in output

    def test_no_sieve_code(self, settings) -> None:
        """UI guide mode does NOT contain sieve code."""
        output = generate_sieve_guidance(settings, ui_guide=True)
        assert "fileinto" not in output
        assert "jmapquery" not in output


class TestGenerateGuidanceCustomCategories:
    """Tests with custom category configurations."""

    def test_custom_category_included(self, monkeypatch, tmp_path) -> None:
        """Custom categories appear in guidance output."""
        config = tmp_path / "config.yaml"
        config.write_text(
            "triage:\n"
            "  categories:\n"
            "    - name: Imbox\n"
            "      add_to_inbox: true\n"
            "    - Feed\n"
            "    - Paper Trail\n"
            "    - Jail\n"
            "    - name: Person\n"
            "      parent: Imbox\n"
            "      contact_type: person\n"
            "    - Receipts\n"
        )
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "test-token")
        monkeypatch.setenv("MAILROOM_CARDDAV_USERNAME", "test")
        monkeypatch.setenv("MAILROOM_CARDDAV_PASSWORD", "test")

        settings = MailroomSettings()
        output = generate_sieve_guidance(settings, ui_guide=False)

        assert 'Sender is in contact group "Receipts"' in output
        assert 'Move to folder "Receipts"' in output

    def test_skips_child_categories(self, settings) -> None:
        """Child categories (Person) do not appear as separate rule entries."""
        output = generate_sieve_guidance(settings, ui_guide=False)

        # Count how many times "Condition: Sender is in contact group" appears
        condition_lines = [
            line
            for line in output.split("\n")
            if "Sender is in contact group" in line
        ]
        # Should have one per root category: Imbox, Feed, Paper Trail, Jail = 4
        assert len(condition_lines) == 4

    def test_custom_screener_mailbox(self, monkeypatch, tmp_path) -> None:
        """Screener section uses custom screener_mailbox name."""
        config = tmp_path / "config.yaml"
        config.write_text(
            "triage:\n"
            "  screener_mailbox: MyScreener\n"
        )
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "test-token")
        monkeypatch.setenv("MAILROOM_CARDDAV_USERNAME", "test")
        monkeypatch.setenv("MAILROOM_CARDDAV_PASSWORD", "test")

        settings = MailroomSettings()
        output = generate_sieve_guidance(settings, ui_guide=False)

        assert "MyScreener" in output
        assert 'Move to folder "MyScreener"' in output


class TestOverrideHighlighting:
    """Tests for override name highlighting in sieve guidance output.

    Uses a custom settings fixture with an explicit destination_mailbox
    override (Feed -> CustomBox) to test the highlighting feature.
    """

    @pytest.fixture
    def override_settings(self, monkeypatch, tmp_path):
        """Settings with a destination_mailbox override for testing highlighting."""
        config = tmp_path / "config.yaml"
        config.write_text(
            "triage:\n"
            "  categories:\n"
            "    - name: Imbox\n"
            "      add_to_inbox: true\n"
            "    - name: Feed\n"
            "      destination_mailbox: CustomBox\n"
            "    - Paper Trail\n"
            "    - Jail\n"
        )
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "test-token")
        monkeypatch.setenv("MAILROOM_CARDDAV_USERNAME", "test")
        monkeypatch.setenv("MAILROOM_CARDDAV_PASSWORD", "test")
        return MailroomSettings()

    def test_override_name_not_colored_when_not_tty(self, override_settings) -> None:
        """Override names have no ANSI codes when stdout is not a TTY."""
        output = generate_sieve_guidance(override_settings, ui_guide=True)
        # Non-TTY: no ANSI escape codes anywhere
        assert "\033[" not in output
        # But the override name "CustomBox" is still present
        assert "CustomBox" in output

    def test_override_detected_for_feed(self, override_settings) -> None:
        """Feed category shows CustomBox (destination_mailbox override) in output."""
        output = generate_sieve_guidance(override_settings, ui_guide=True)
        assert 'Move to folder" = "CustomBox"' in output

    def test_override_in_sieve_snippets(self, override_settings) -> None:
        """Override name appears in sieve snippet mode too."""
        output = generate_sieve_guidance(override_settings, ui_guide=False)
        assert 'Move to folder "CustomBox"' in output
        assert 'fileinto "INBOX.CustomBox"' in output

    def test_matching_name_not_marked_as_override(self, override_settings) -> None:
        """Imbox category (name=Imbox, destination_mailbox=Imbox) has no ANSI codes."""
        output = generate_sieve_guidance(override_settings, ui_guide=True)
        # Non-TTY so no codes at all
        assert "\033[" not in output
        assert 'Move to folder" = "Imbox"' in output

    def test_override_name_colored_when_tty(self, override_settings, monkeypatch) -> None:
        """Override names get ANSI color when stdout is a TTY."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.delenv("NO_COLOR", raising=False)
        output = generate_sieve_guidance(override_settings, ui_guide=True)
        # Should contain ANSI cyan around "CustomBox" (override of Feed)
        assert "\033[36m" in output  # cyan code present
        assert "CustomBox" in output

    def test_no_color_for_matching_name_when_tty(self, override_settings, monkeypatch) -> None:
        """Non-override names are NOT wrapped in ANSI color even when TTY."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.delenv("NO_COLOR", raising=False)
        output = generate_sieve_guidance(override_settings, ui_guide=True)
        # Imbox's destination_mailbox matches its name, so no cyan wrapping
        lines = output.split("\n")
        imbox_folder_lines = [
            line for line in lines
            if "Move to folder" in line and "Imbox" in line
        ]
        assert len(imbox_folder_lines) == 1
        # The Imbox folder name should NOT be wrapped in cyan
        assert "\033[36mImbox\033[0m" not in imbox_folder_lines[0]

    def test_override_color_in_sieve_snippets_when_tty(self, override_settings, monkeypatch) -> None:
        """Override names are colored in sieve snippet mode when TTY."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.delenv("NO_COLOR", raising=False)
        output = generate_sieve_guidance(override_settings, ui_guide=False)
        # Cyan should appear for CustomBox override
        assert "\033[36m" in output
        assert "CustomBox" in output
