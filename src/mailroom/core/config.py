"""Mailroom configuration loaded from MAILROOM_-prefixed environment variables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Phase 6: Configurable triage category models
# ---------------------------------------------------------------------------


class TriageCategory(BaseModel):
    """A single triage category as provided by the user.

    Only ``name`` is required. All other fields are optional and will be
    derived from the name when left unset (see ``resolve_categories``).
    """

    name: str
    label: str | None = None
    contact_group: str | None = None
    destination_mailbox: str | None = None
    contact_type: Literal["company", "person"] = "company"
    parent: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """Strip whitespace and reject empty names."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Category name must not be empty")
        return stripped


@dataclass(frozen=True)
class ResolvedCategory:
    """A fully resolved triage category -- all fields concrete."""

    name: str
    label: str
    contact_group: str
    destination_mailbox: str
    contact_type: str
    parent: str | None


# -- Derivation helpers -----------------------------------------------------


def derive_label(name: str) -> str:
    """Derive triage label from category name: 'Paper Trail' -> '@ToPaperTrail'."""
    return f"@To{''.join(name.split())}"


def derive_contact_group(name: str) -> str:
    """Derive contact group from category name (identity)."""
    return name


def derive_destination_mailbox(name: str) -> str:
    """Derive destination mailbox from category name (identity)."""
    return name


# -- Default factory --------------------------------------------------------


def _default_categories() -> list[TriageCategory]:
    """Return the v1.0 default categories.

    Used when ``MAILROOM_TRIAGE_CATEGORIES`` is not set.
    """
    return [
        TriageCategory(name="Imbox", destination_mailbox="Inbox"),
        TriageCategory(name="Feed"),
        TriageCategory(name="Paper Trail"),
        TriageCategory(name="Jail"),
        TriageCategory(name="Person", parent="Imbox", contact_type="person"),
    ]


# -- Resolution logic -------------------------------------------------------


def resolve_categories(
    categories: list[TriageCategory],
) -> list[ResolvedCategory]:
    """Resolve a list of user-provided categories into fully concrete objects.

    Two-pass resolution:
      1. Derive missing fields from the category name.
      2. Apply parent inheritance (children inherit parent's contact_group
         and destination_mailbox unless explicitly overridden).
    """
    # First pass: resolve own fields
    first_pass: dict[str, ResolvedCategory] = {}
    for cat in categories:
        first_pass[cat.name] = ResolvedCategory(
            name=cat.name,
            label=cat.label if cat.label is not None else derive_label(cat.name),
            contact_group=(
                cat.contact_group
                if cat.contact_group is not None
                else derive_contact_group(cat.name)
            ),
            destination_mailbox=(
                cat.destination_mailbox
                if cat.destination_mailbox is not None
                else derive_destination_mailbox(cat.name)
            ),
            contact_type=cat.contact_type,
            parent=cat.parent,
        )

    # Second pass: apply parent inheritance
    # Build a lookup from category name -> original TriageCategory for
    # checking whether an override was explicitly set.
    originals = {cat.name: cat for cat in categories}
    resolved: list[ResolvedCategory] = []

    for cat in categories:
        r = first_pass[cat.name]
        if cat.parent and cat.parent in first_pass:
            parent_resolved = first_pass[cat.parent]
            new_group = r.contact_group
            new_mailbox = r.destination_mailbox

            # Inherit contact_group if NOT explicitly set by user
            if originals[cat.name].contact_group is None:
                new_group = parent_resolved.contact_group

            # Inherit destination_mailbox if NOT explicitly set by user
            if originals[cat.name].destination_mailbox is None:
                new_mailbox = parent_resolved.destination_mailbox

            r = ResolvedCategory(
                name=r.name,
                label=r.label,
                contact_group=new_group,
                destination_mailbox=new_mailbox,
                contact_type=r.contact_type,
                parent=r.parent,
            )

        resolved.append(r)

    return resolved


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
    label_to_person: str = "@ToPerson"

    # Error label (verified at startup alongside other labels)
    label_mailroom_error: str = "@MailroomError"

    # Warning label (non-blocking alerts, e.g. name mismatch)
    label_mailroom_warning: str = "@MailroomWarning"
    warnings_enabled: bool = True

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
            self.label_to_person,
        ]

    @property
    def label_to_group_mapping(self) -> dict[str, dict[str, str]]:
        """Return a mapping from triage label to destination group info.

        Used by the triage workflow to determine where to move emails
        based on which label the user applied. Each entry includes
        contact_type ("company" or "person") for vCard construction.
        """
        return {
            self.label_to_imbox: {
                "group": self.group_imbox,
                "destination": self.group_imbox,
                "destination_mailbox": "Inbox",
                "contact_type": "company",
            },
            self.label_to_feed: {
                "group": self.group_feed,
                "destination": self.group_feed,
                "destination_mailbox": "Feed",
                "contact_type": "company",
            },
            self.label_to_paper_trail: {
                "group": self.group_paper_trail,
                "destination": self.group_paper_trail,
                "destination_mailbox": "Paper Trail",
                "contact_type": "company",
            },
            self.label_to_jail: {
                "group": self.group_jail,
                "destination": self.group_jail,
                "destination_mailbox": "Jail",
                "contact_type": "company",
            },
            self.label_to_person: {
                "group": self.group_imbox,
                "destination": self.group_imbox,
                "destination_mailbox": "Inbox",
                "contact_type": "person",
            },
        }

    @property
    def required_mailboxes(self) -> list[str]:
        """Return all mailbox names that must exist at startup.

        Includes Inbox, screener, error label, all triage labels, and all
        unique destination mailboxes. Conditionally includes the warning
        label when warnings are enabled.
        """
        # Collect unique destination mailboxes from the mapping
        destinations = list({
            entry["destination_mailbox"]
            for entry in self.label_to_group_mapping.values()
        })

        mailboxes = [
            "Inbox",
            self.screener_mailbox,
            self.label_mailroom_error,
            *self.triage_labels,
            *destinations,
        ]

        if self.warnings_enabled:
            mailboxes.append(self.label_mailroom_warning)

        return mailboxes

    @property
    def contact_groups(self) -> list[str]:
        """Return all contact group names for startup validation."""
        return [
            self.group_imbox,
            self.group_feed,
            self.group_paper_trail,
            self.group_jail,
        ]
