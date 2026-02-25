"""Shared test fixtures for mailroom."""

import pytest

from mailroom.core.config import MailroomSettings


@pytest.fixture
def mock_settings(monkeypatch):
    """Create MailroomSettings with required env vars set."""
    monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "test-token")
    monkeypatch.setenv("MAILROOM_CARDDAV_USERNAME", "test@fastmail.com")
    monkeypatch.setenv("MAILROOM_CARDDAV_PASSWORD", "test-password")
    return MailroomSettings()


@pytest.fixture
def mock_mailbox_ids():
    """Provide a dict of all required mailbox name -> ID mappings."""
    return {
        "Inbox": "mb-inbox",
        "Screener": "mb-screener",
        "Feed": "mb-feed",
        "Paper Trail": "mb-papertrl",
        "Jail": "mb-jail",
        "@ToImbox": "mb-toimbox",
        "@ToFeed": "mb-tofeed",
        "@ToPaperTrail": "mb-topapertrl",
        "@ToJail": "mb-tojail",
        "@MailroomError": "mb-error",
        "@ToPerson": "mb-toperson",
        "@MailroomWarning": "mb-warning",
    }
