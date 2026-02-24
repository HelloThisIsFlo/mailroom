"""Mailroom configuration loaded from MAILROOM_-prefixed environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MailroomSettings(BaseSettings):
    """Application settings with sensible defaults matching the user's Fastmail setup.

    All values are loaded from environment variables with the MAILROOM_ prefix.
    For example, MAILROOM_JMAP_TOKEN sets jmap_token.
    """

    model_config = SettingsConfigDict(
        env_prefix="MAILROOM_",
        case_sensitive=False,
    )

    # Required credentials -- no defaults, fails if missing
    jmap_token: str

    # CardDAV credentials -- not required in Phase 1 (empty defaults for forward compat)
    carddav_username: str = ""
    carddav_password: str = ""

    # Polling
    poll_interval: int = 300  # seconds (5 min)

    # Logging
    log_level: str = "info"

    # Triage label names (Fastmail mailbox names)
    label_to_imbox: str = "@ToImbox"
    label_to_feed: str = "@ToFeed"
    label_to_paper_trail: str = "@ToPaperTrail"
    label_to_jail: str = "@ToJail"

    # Error label (verified at startup alongside other labels)
    label_mailroom_error: str = "@MailroomError"

    # Screener mailbox name (configurable for flexibility)
    screener_mailbox: str = "Screener"

    # Contact group names
    group_imbox: str = "Imbox"
    group_feed: str = "Feed"
    group_paper_trail: str = "Paper Trail"
    group_jail: str = "Jail"

    @property
    def triage_labels(self) -> list[str]:
        """Return all triage label names for mailbox validation at startup."""
        return [
            self.label_to_imbox,
            self.label_to_feed,
            self.label_to_paper_trail,
            self.label_to_jail,
        ]

    @property
    def label_to_group_mapping(self) -> dict[str, dict[str, str]]:
        """Return a mapping from triage label to destination group info.

        Used by the triage workflow to determine where to move emails
        based on which label the user applied.
        """
        return {
            self.label_to_imbox: {
                "group": self.group_imbox,
                "destination": self.group_imbox,
                "destination_mailbox": "Inbox",
            },
            self.label_to_feed: {
                "group": self.group_feed,
                "destination": self.group_feed,
                "destination_mailbox": "Feed",
            },
            self.label_to_paper_trail: {
                "group": self.group_paper_trail,
                "destination": self.group_paper_trail,
                "destination_mailbox": "Paper Trail",
            },
            self.label_to_jail: {
                "group": self.group_jail,
                "destination": self.group_jail,
                "destination_mailbox": "Jail",
            },
        }

    @property
    def contact_groups(self) -> list[str]:
        """Return all contact group names for startup validation."""
        return [
            self.group_imbox,
            self.group_feed,
            self.group_paper_trail,
            self.group_jail,
        ]
