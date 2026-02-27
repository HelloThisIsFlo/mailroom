"""Mailroom configuration loaded from MAILROOM_-prefixed environment variables."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator
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


def _validate_categories(categories: list[TriageCategory]) -> list[str]:
    """Validate a list of triage categories and return all errors found.

    Checks performed (all errors collected, not fail-fast):
      - At least one category required
      - No duplicate names
      - All parent references point to existing categories
      - No circular parent chains (including self-reference)
      - No duplicate labels after derivation
      - No shared contact groups unless related via parent
    """
    errors: list[str] = []

    # 1. Empty list
    if not categories:
        errors.append("At least one triage category is required.")
        return errors  # remaining checks meaningless on empty list

    # 2. Duplicate names
    seen_names: set[str] = set()
    for cat in categories:
        if cat.name in seen_names:
            errors.append(f"Duplicate category name: '{cat.name}'")
        seen_names.add(cat.name)

    # 3. Parent references exist
    name_set = {c.name for c in categories}
    for cat in categories:
        if cat.parent and cat.parent not in name_set:
            errors.append(
                f"Category '{cat.name}' references non-existent parent '{cat.parent}'"
            )

    # 4. Circular parent chains
    parent_map = {c.name: c.parent for c in categories}
    checked: set[str] = set()
    for cat in categories:
        if cat.parent and cat.name not in checked:
            visited: set[str] = {cat.name}
            current = cat.parent
            while current:
                if current in visited:
                    errors.append(
                        f"Circular parent chain involving '{cat.name}'"
                    )
                    break
                if current not in name_set:
                    break  # already reported as non-existent parent
                visited.add(current)
                current = parent_map.get(current)
            checked.update(visited)

    # 5. Duplicate labels after derivation
    label_owners: dict[str, str] = {}
    for cat in categories:
        label = cat.label if cat.label is not None else derive_label(cat.name)
        if label in label_owners:
            errors.append(
                f"Duplicate triage label '{label}' "
                f"(from '{label_owners[label]}' and '{cat.name}')"
            )
        else:
            label_owners[label] = cat.name

    # 6. Shared contact groups without parent relationship
    # Build resolved groups for checking
    group_owners: dict[str, list[str]] = {}
    for cat in categories:
        group = (
            cat.contact_group
            if cat.contact_group is not None
            else derive_contact_group(cat.name)
        )
        group_owners.setdefault(group, []).append(cat.name)

    for group, owners in group_owners.items():
        if len(owners) > 1:
            # Check if all sharing is via parent relationships
            for i, a in enumerate(owners):
                for b in owners[i + 1 :]:
                    cat_a = next(c for c in categories if c.name == a)
                    cat_b = next(c for c in categories if c.name == b)
                    # Allowed if one is parent of the other
                    if cat_a.parent != b and cat_b.parent != a:
                        errors.append(
                            f"Categories '{a}' and '{b}' share contact group "
                            f"'{group}' without a parent relationship"
                        )

    return errors


def resolve_categories(
    categories: list[TriageCategory],
) -> list[ResolvedCategory]:
    """Resolve a list of user-provided categories into fully concrete objects.

    Validates all constraints first (collecting all errors), then performs
    two-pass resolution:
      1. Derive missing fields from the category name.
      2. Apply parent inheritance (children inherit parent's contact_group
         and destination_mailbox unless explicitly overridden).

    Raises ``ValueError`` with all validation errors if any are found.
    """
    # Validate first -- collect all errors
    errors = _validate_categories(categories)
    if errors:
        default_json = json.dumps(
            [c.model_dump(exclude_none=True) for c in _default_categories()],
            indent=2,
        )
        raise ValueError(
            "Invalid triage category configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
            + f"\n\nDefault configuration for reference:\n{default_json}"
        )

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
        arbitrary_types_allowed=True,
    )

    # Required credentials -- no defaults, fails if missing
    jmap_token: str

    # CardDAV credentials -- not required in Phase 1 (empty defaults for forward compat)
    carddav_username: str = ""
    carddav_password: str = ""

    # Polling
    poll_interval: int = 60  # seconds (tighter safety net with SSE push as primary)
    debounce_seconds: int = 3  # SSE event debounce window

    # Logging
    log_level: str = "info"

    # Error label (verified at startup alongside other labels)
    label_mailroom_error: str = "@MailroomError"

    # Warning label (non-blocking alerts, e.g. name mismatch)
    label_mailroom_warning: str = "@MailroomWarning"
    warnings_enabled: bool = True

    # Screener mailbox name (configurable for flexibility)
    screener_mailbox: str = "Screener"

    # Triage categories -- single source of truth for all category configuration
    triage_categories: list[TriageCategory] = Field(
        default_factory=_default_categories,
    )

    @model_validator(mode="after")
    def resolve_and_validate_categories(self) -> Self:
        """Resolve triage categories and build label-to-category lookup."""
        resolved = resolve_categories(self.triage_categories)
        object.__setattr__(self, "_resolved_categories", resolved)
        object.__setattr__(
            self, "_label_to_category", {r.label: r for r in resolved}
        )
        return self

    @property
    def triage_labels(self) -> list[str]:
        """Return all triage label names for mailbox validation at startup."""
        return [c.label for c in self._resolved_categories]

    @property
    def label_to_category_mapping(self) -> dict[str, ResolvedCategory]:
        """Return a mapping from triage label to its resolved category.

        Used by the triage workflow to determine where to move emails
        based on which label the user applied. Each ResolvedCategory
        includes contact_group, destination_mailbox, and contact_type.
        """
        return dict(self._label_to_category)

    @property
    def required_mailboxes(self) -> list[str]:
        """Return all mailbox names that must exist at startup.

        Includes Inbox, screener, error label, all triage labels, and all
        unique destination mailboxes. Conditionally includes the warning
        label when warnings are enabled.
        """
        mailboxes: set[str] = {"Inbox", self.screener_mailbox, self.label_mailroom_error}
        for c in self._resolved_categories:
            mailboxes.add(c.label)
            mailboxes.add(c.destination_mailbox)
        if self.warnings_enabled:
            mailboxes.add(self.label_mailroom_warning)
        return sorted(mailboxes)

    @property
    def contact_groups(self) -> list[str]:
        """Return all contact group names for startup validation."""
        return sorted({c.contact_group for c in self._resolved_categories})
