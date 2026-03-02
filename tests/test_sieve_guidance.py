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
        """Feed category shows contact group condition and folder action with archive."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Feed"' in output
        assert "Add label: " in output

    def test_imbox_category(self, settings) -> None:
        """Imbox category shows its own mailbox name (v1.2: derived Imbox, not Inbox)."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Imbox"' in output

    def test_paper_trail_category(self, settings) -> None:
        """Paper Trail category is present."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Paper Trail"' in output

    def test_jail_category(self, settings) -> None:
        """Jail category is present."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Jail"' in output

    def test_person_included(self, settings) -> None:
        """Person (child of Imbox) appears as a separate rule section."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Person"' in output

    def test_billboard_included(self, settings) -> None:
        """Billboard (child of Paper Trail) appears as a separate rule section."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Billboard"' in output

    def test_truck_included(self, settings) -> None:
        """Truck (child of Paper Trail) appears as a separate rule section."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert 'Sender is in contact group "Truck"' in output

    def test_screener_catch_all(self, settings) -> None:
        """Screener catch-all section is present with correct mailbox name."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert "Screener catch-all rule:" in output
        assert "Screener" in output
        assert "LAST" in output

    def test_sieve_reference_snippets(self, settings) -> None:
        """Output contains sieve reference with fileinto and jmapquery."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert "fileinto" in output
        assert "jmapquery" in output

    def test_continue_note_prominent(self, settings) -> None:
        """Prominent note about 'Continue to apply other rules' appears at top."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        lines = output.split("\n")
        # The IMPORTANT note should appear before any per-category rules
        important_idx = None
        first_condition_idx = None
        for i, line in enumerate(lines):
            if "IMPORTANT" in line and "Continue to apply other rules" in line:
                important_idx = i
            if "Sender is in contact group" in line and first_condition_idx is None:
                first_condition_idx = i
        assert important_idx is not None, "IMPORTANT note about Continue not found"
        assert first_condition_idx is not None, "No category conditions found"
        assert important_idx < first_condition_idx, "IMPORTANT note should come before category rules"

    def test_add_to_inbox_no_archive(self, settings) -> None:
        """Imbox (add_to_inbox=True) rule has no archive action."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        lines = output.split("\n")
        # Find the Imbox section and verify no Archive in it
        in_imbox = False
        imbox_lines: list[str] = []
        for line in lines:
            if "Imbox" in line and "Condition" not in line and "Action" not in line:
                in_imbox = True
                imbox_lines = [line]
                continue
            if in_imbox:
                imbox_lines.append(line)
                # Stop at next category or screener section
                stripped = line.strip()
                if stripped and not stripped.startswith(("Condition", "Action", "#", "1.", "2.", "3.", "(", "+")):
                    # Check if this is a new category heading
                    if "Sender is in contact group" not in line and "Add label" not in line and "Continue" not in line and "Archive" not in line and "No archive" not in line and "child of" not in line:
                        break
        imbox_section = "\n".join(imbox_lines)
        # Imbox section should mention "No archive" or not have "Archive" as an action
        assert "Archive" not in imbox_section or "No archive" in imbox_section

    def test_standard_has_archive(self, settings) -> None:
        """Feed (standard, add_to_inbox=False) rule has archive action."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        lines = output.split("\n")
        # Find Feed section and verify Archive is present
        in_feed = False
        feed_lines: list[str] = []
        for line in lines:
            if "Feed" in line and "Condition" not in line:
                in_feed = True
                feed_lines = [line]
                continue
            if in_feed:
                feed_lines.append(line)
                if "Sender is in contact group" in line and "Feed" not in line:
                    break
        feed_section = "\n".join(feed_lines)
        assert "Archive" in feed_section

    def test_all_seven_categories_present(self, settings) -> None:
        """All 7 default categories appear as rules in the output."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        condition_lines = [
            line
            for line in output.split("\n")
            if "Sender is in contact group" in line
        ]
        # Should have one per category: Imbox, Feed, Paper Trail, Jail, Person, Billboard, Truck = 7
        assert len(condition_lines) == 7


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
        """Per-category steps mention contact group condition."""
        output = generate_sieve_guidance(settings, ui_guide=True)
        assert "contact group" in output

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

    def test_all_categories_shown(self, settings) -> None:
        """All 7 categories appear in UI guide mode."""
        output = generate_sieve_guidance(settings, ui_guide=True)
        assert "Imbox" in output
        assert "Feed" in output
        assert "Paper Trail" in output
        assert "Jail" in output
        assert "Person" in output
        assert "Billboard" in output
        assert "Truck" in output

    def test_continue_to_apply_mentioned(self, settings) -> None:
        """UI guide mentions 'Continue to apply other rules' or equivalent checkbox."""
        output = generate_sieve_guidance(settings, ui_guide=True)
        assert "apply other rules" in output.lower() or "continue" in output.lower()


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

    def test_includes_child_categories(self, settings) -> None:
        """Child categories (Person, Billboard, Truck) appear as separate rule entries."""
        output = generate_sieve_guidance(settings, ui_guide=False)

        # Count how many times "Condition: Sender is in contact group" appears
        condition_lines = [
            line
            for line in output.split("\n")
            if "Sender is in contact group" in line
        ]
        # Should have one per category: Imbox, Feed, Paper Trail, Jail, Person, Billboard, Truck = 7
        assert len(condition_lines) == 7

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


class TestGroupedDisplay:
    """Tests that categories are grouped by parent in the output."""

    def test_children_appear_after_parent(self, settings) -> None:
        """Child categories appear after their parent in the output."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        lines = output.split("\n")

        # Find positions of Imbox and Person
        imbox_idx = None
        person_idx = None
        for i, line in enumerate(lines):
            if 'contact group "Imbox"' in line:
                imbox_idx = i
            if 'contact group "Person"' in line:
                person_idx = i
        assert imbox_idx is not None, "Imbox not found"
        assert person_idx is not None, "Person not found"
        assert imbox_idx < person_idx, "Person should appear after Imbox"

    def test_paper_trail_children_after_parent(self, settings) -> None:
        """Billboard and Truck appear after Paper Trail."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        lines = output.split("\n")

        paper_trail_idx = None
        billboard_idx = None
        truck_idx = None
        for i, line in enumerate(lines):
            if 'contact group "Paper Trail"' in line:
                paper_trail_idx = i
            if 'contact group "Billboard"' in line:
                billboard_idx = i
            if 'contact group "Truck"' in line:
                truck_idx = i
        assert paper_trail_idx is not None, "Paper Trail not found"
        assert billboard_idx is not None, "Billboard not found"
        assert truck_idx is not None, "Truck not found"
        assert paper_trail_idx < billboard_idx, "Billboard should appear after Paper Trail"
        assert paper_trail_idx < truck_idx, "Truck should appear after Paper Trail"

    def test_child_of_annotation(self, settings) -> None:
        """Child categories have a '(child of ...)' annotation."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert "child of Imbox" in output
        assert "child of Paper Trail" in output


class TestSyntaxHighlighting:
    """Tests for syntax highlighting in sieve guidance output."""

    @pytest.fixture
    def tty_settings(self, settings, monkeypatch):
        """Settings with TTY stdout for color output."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.delenv("NO_COLOR", raising=False)
        return settings

    def test_bold_category_names_when_tty(self, tty_settings) -> None:
        """Category names are wrapped in BOLD when TTY is detected."""
        output = generate_sieve_guidance(tty_settings, ui_guide=False)
        assert "\033[1m" in output  # BOLD code present

    def test_cyan_mailbox_names_when_tty(self, tty_settings) -> None:
        """Mailbox names are wrapped in CYAN when TTY is detected."""
        output = generate_sieve_guidance(tty_settings, ui_guide=False)
        assert "\033[36m" in output  # CYAN code present

    def test_magenta_keywords_when_tty(self, tty_settings) -> None:
        """Sieve keywords (Archive, Continue) are wrapped in MAGENTA when TTY."""
        output = generate_sieve_guidance(tty_settings, ui_guide=False)
        assert "\033[35m" in output  # MAGENTA code present

    def test_no_ansi_when_not_tty(self, settings) -> None:
        """No ANSI codes when stdout is not a TTY."""
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert "\033[" not in output

    def test_no_ansi_when_no_color_env(self, settings, monkeypatch) -> None:
        """No ANSI codes when NO_COLOR env var is set."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.setenv("NO_COLOR", "1")
        output = generate_sieve_guidance(settings, ui_guide=False)
        assert "\033[" not in output
