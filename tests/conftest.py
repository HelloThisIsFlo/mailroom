"""Shared test fixtures for mailroom."""

import pytest

from mailroom.core.config import MailroomSettings


@pytest.fixture(autouse=True)
def _set_config_path(monkeypatch, tmp_path):
    """Point MailroomSettings to an empty test config.yaml and clean env.

    This autouse fixture ensures every test has a valid YAML config file,
    preventing 'config.yaml not found' errors. It also removes any real
    MAILROOM_* env vars from the host environment to prevent leakage.

    Tests that need custom config values should write YAML to their own
    tmp_path file and set MAILROOM_CONFIG accordingly.
    """
    # Clean host env vars that could leak into tests
    for var in [
        "MAILROOM_JMAP_TOKEN",
        "MAILROOM_CARDDAV_USERNAME",
        "MAILROOM_CARDDAV_PASSWORD",
        "MAILROOM_POLL_INTERVAL",
        "MAILROOM_LOG_LEVEL",
        "MAILROOM_SCREENER_MAILBOX",
        "MAILROOM_TRIAGE_CATEGORIES",
        "MAILROOM_DEBOUNCE_SECONDS",
        "MAILROOM_LABEL_MAILROOM_ERROR",
        "MAILROOM_LABEL_MAILROOM_WARNING",
        "MAILROOM_WARNINGS_ENABLED",
    ]:
        monkeypatch.delenv(var, raising=False)
    config = tmp_path / "config.yaml"
    config.write_text("")  # empty = all defaults
    monkeypatch.setenv("MAILROOM_CONFIG", str(config))


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
