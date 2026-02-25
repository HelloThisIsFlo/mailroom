"""Tests for the configuration module."""

import pytest
from pydantic import ValidationError

from mailroom.core.config import MailroomSettings

# Env vars that might leak into tests from the host environment
MAILROOM_ENV_VARS = [
    "MAILROOM_JMAP_TOKEN",
    "MAILROOM_CARDDAV_PASSWORD",
    "MAILROOM_POLL_INTERVAL",
    "MAILROOM_LOG_LEVEL",
    "MAILROOM_LABEL_TO_IMBOX",
    "MAILROOM_LABEL_TO_FEED",
    "MAILROOM_LABEL_TO_PAPER_TRAIL",
    "MAILROOM_LABEL_TO_JAIL",
    "MAILROOM_GROUP_IMBOX",
    "MAILROOM_GROUP_FEED",
    "MAILROOM_GROUP_PAPER_TRAIL",
    "MAILROOM_GROUP_JAIL",
    "MAILROOM_SCREENER_MAILBOX",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove any MAILROOM_ env vars so tests start from a clean slate."""
    for var in MAILROOM_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults(monkeypatch):
    """Setting only the required JMAP token gives sensible defaults."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "test-token-abc")

    settings = MailroomSettings()

    assert settings.jmap_token == "test-token-abc"
    assert settings.carddav_password == ""
    assert settings.poll_interval == 300
    assert settings.log_level == "info"

    # Label defaults match the user's Fastmail setup
    assert settings.label_to_imbox == "@ToImbox"
    assert settings.label_to_feed == "@ToFeed"
    assert settings.label_to_paper_trail == "@ToPaperTrail"
    assert settings.label_to_jail == "@ToJail"

    # Group defaults match the user's Fastmail setup
    assert settings.group_imbox == "Imbox"
    assert settings.group_feed == "Feed"
    assert settings.group_paper_trail == "Paper Trail"
    assert settings.group_jail == "Jail"


def test_required_jmap_token():
    """Missing MAILROOM_JMAP_TOKEN causes a validation error."""
    with pytest.raises(ValidationError) as exc_info:
        MailroomSettings()

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("jmap_token",) for e in errors)


def test_env_override(monkeypatch):
    """Environment variables override defaults."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")
    monkeypatch.setenv("MAILROOM_POLL_INTERVAL", "60")
    monkeypatch.setenv("MAILROOM_LOG_LEVEL", "debug")

    settings = MailroomSettings()

    assert settings.poll_interval == 60
    assert settings.log_level == "debug"


def test_triage_labels_property(monkeypatch):
    """triage_labels returns all five label names including @ToPerson."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    labels = settings.triage_labels
    assert labels == ["@ToImbox", "@ToFeed", "@ToPaperTrail", "@ToJail", "@ToPerson"]


def test_label_group_mapping(monkeypatch):
    """label_to_group_mapping returns correct label-to-group associations."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    mapping = settings.label_to_group_mapping

    assert mapping["@ToImbox"] == {
        "group": "Imbox",
        "destination": "Imbox",
        "destination_mailbox": "Inbox",
        "contact_type": "company",
    }
    assert mapping["@ToFeed"] == {
        "group": "Feed",
        "destination": "Feed",
        "destination_mailbox": "Feed",
        "contact_type": "company",
    }
    assert mapping["@ToPaperTrail"] == {
        "group": "Paper Trail",
        "destination": "Paper Trail",
        "destination_mailbox": "Paper Trail",
        "contact_type": "company",
    }
    assert mapping["@ToJail"] == {
        "group": "Jail",
        "destination": "Jail",
        "destination_mailbox": "Jail",
        "contact_type": "company",
    }

    # 5 entries (4 original + @ToPerson)
    assert len(mapping) == 5


def test_screener_mailbox_default(monkeypatch):
    """screener_mailbox defaults to 'Screener'."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    assert settings.screener_mailbox == "Screener"


def test_screener_mailbox_override(monkeypatch):
    """screener_mailbox can be overridden via env var."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")
    monkeypatch.setenv("MAILROOM_SCREENER_MAILBOX", "MyScreener")

    settings = MailroomSettings()

    assert settings.screener_mailbox == "MyScreener"


def test_destination_mailbox_in_mapping(monkeypatch):
    """Each label mapping includes destination_mailbox field."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()
    mapping = settings.label_to_group_mapping

    # Imbox destination is Inbox (the actual mailbox, not the group name)
    assert mapping["@ToImbox"]["destination_mailbox"] == "Inbox"
    # Others match the group/destination name
    assert mapping["@ToFeed"]["destination_mailbox"] == "Feed"
    assert mapping["@ToPaperTrail"]["destination_mailbox"] == "Paper Trail"
    assert mapping["@ToJail"]["destination_mailbox"] == "Jail"


# --- Phase 3.1 Config Extension Tests ---


def test_label_to_person_default(monkeypatch):
    """label_to_person field defaults to '@ToPerson'."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    assert settings.label_to_person == "@ToPerson"


def test_label_mailroom_warning_default(monkeypatch):
    """label_mailroom_warning field defaults to '@MailroomWarning'."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    assert settings.label_mailroom_warning == "@MailroomWarning"


def test_warnings_enabled_default(monkeypatch):
    """warnings_enabled field defaults to True."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    assert settings.warnings_enabled is True


def test_triage_labels_includes_toperson(monkeypatch):
    """triage_labels property includes @ToPerson (5 labels total)."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    labels = settings.triage_labels
    assert "@ToPerson" in labels
    assert len(labels) == 5


def test_toperson_mapping_entry(monkeypatch):
    """label_to_group_mapping has @ToPerson entry with contact_type='person'."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()
    mapping = settings.label_to_group_mapping

    assert "@ToPerson" in mapping
    entry = mapping["@ToPerson"]
    assert entry["contact_type"] == "person"
    assert entry["group"] == "Imbox"
    assert entry["destination_mailbox"] == "Inbox"


def test_existing_mapping_entries_have_company_contact_type(monkeypatch):
    """All existing mapping entries have contact_type='company'."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()
    mapping = settings.label_to_group_mapping

    for label in ["@ToImbox", "@ToFeed", "@ToPaperTrail", "@ToJail"]:
        assert mapping[label]["contact_type"] == "company", (
            f"{label} should have contact_type='company'"
        )


def test_toperson_routes_same_as_toimbox(monkeypatch):
    """@ToPerson routes to same group/destination as @ToImbox."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()
    mapping = settings.label_to_group_mapping

    imbox_entry = mapping["@ToImbox"]
    person_entry = mapping["@ToPerson"]

    assert person_entry["group"] == imbox_entry["group"]
    assert person_entry["destination_mailbox"] == imbox_entry["destination_mailbox"]


def test_startup_validates_warning_label_when_enabled(monkeypatch):
    """required_mailboxes includes @MailroomWarning when warnings_enabled=True."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()
    assert settings.warnings_enabled is True

    required = settings.required_mailboxes
    assert "@MailroomWarning" in required


def test_startup_succeeds_without_warning_label_when_disabled(monkeypatch):
    """required_mailboxes does NOT include @MailroomWarning when warnings_enabled=False."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")
    monkeypatch.setenv("MAILROOM_WARNINGS_ENABLED", "false")

    settings = MailroomSettings()
    assert settings.warnings_enabled is False

    required = settings.required_mailboxes
    assert "@MailroomWarning" not in required


def test_mapping_has_five_entries_with_toperson(monkeypatch):
    """label_to_group_mapping has 5 entries (4 original + @ToPerson)."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()
    mapping = settings.label_to_group_mapping

    assert len(mapping) == 5
