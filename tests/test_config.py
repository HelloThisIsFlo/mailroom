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
    """triage_labels returns all four label names."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    labels = settings.triage_labels
    assert labels == ["@ToImbox", "@ToFeed", "@ToPaperTrail", "@ToJail"]


def test_label_group_mapping(monkeypatch):
    """label_to_group_mapping returns correct label-to-group associations."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

    settings = MailroomSettings()

    mapping = settings.label_to_group_mapping

    assert mapping["@ToImbox"] == {"group": "Imbox", "destination": "Imbox"}
    assert mapping["@ToFeed"] == {"group": "Feed", "destination": "Feed"}
    assert mapping["@ToPaperTrail"] == {"group": "Paper Trail", "destination": "Paper Trail"}
    assert mapping["@ToJail"] == {"group": "Jail", "destination": "Jail"}

    # Exactly 4 entries
    assert len(mapping) == 4
