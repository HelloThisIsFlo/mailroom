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


# --- Phase 6: TriageCategory Model, ResolvedCategory, Derivation, Defaults ---

from dataclasses import FrozenInstanceError

from mailroom.core.config import (
    ResolvedCategory,
    TriageCategory,
    _default_categories,
    resolve_categories,
)


class TestTriageCategoryModel:
    """Tests for the TriageCategory Pydantic model."""

    def test_name_only_input(self):
        """TriageCategory(name='Receipts') succeeds with defaults."""
        cat = TriageCategory(name="Receipts")
        assert cat.name == "Receipts"
        assert cat.label is None
        assert cat.contact_group is None
        assert cat.destination_mailbox is None
        assert cat.contact_type == "company"
        assert cat.parent is None

    def test_empty_name_rejected(self):
        """TriageCategory(name='') raises ValidationError."""
        with pytest.raises(ValidationError):
            TriageCategory(name="")

    def test_whitespace_only_name_rejected(self):
        """TriageCategory(name='  ') raises ValidationError."""
        with pytest.raises(ValidationError):
            TriageCategory(name="  ")

    def test_name_stripped(self):
        """TriageCategory(name='  Receipts  ') strips to 'Receipts'."""
        cat = TriageCategory(name="  Receipts  ")
        assert cat.name == "Receipts"


class TestDerivationRules:
    """Tests for name-to-label/group/mailbox derivation via resolve_categories."""

    def test_simple_name_derivation(self):
        """Name 'Receipts' derives label '@ToReceipts', group 'Receipts', mailbox 'Receipts'."""
        cats = [TriageCategory(name="Receipts")]
        resolved = resolve_categories(cats)
        assert len(resolved) == 1
        r = resolved[0]
        assert r.label == "@ToReceipts"
        assert r.contact_group == "Receipts"
        assert r.destination_mailbox == "Receipts"

    def test_multi_word_name_derivation(self):
        """Name 'Paper Trail' derives label '@ToPaperTrail' (spaces removed)."""
        cats = [TriageCategory(name="Paper Trail")]
        resolved = resolve_categories(cats)
        r = resolved[0]
        assert r.label == "@ToPaperTrail"
        assert r.contact_group == "Paper Trail"
        assert r.destination_mailbox == "Paper Trail"

    def test_explicit_override_preserved(self):
        """Explicit destination_mailbox='Inbox' overrides derived value."""
        cats = [TriageCategory(name="Imbox", destination_mailbox="Inbox")]
        resolved = resolve_categories(cats)
        r = resolved[0]
        assert r.destination_mailbox == "Inbox"
        # Label and group still derived from name
        assert r.label == "@ToImbox"
        assert r.contact_group == "Imbox"


class TestDefaultFactory:
    """Tests for _default_categories() factory function."""

    def test_returns_five_categories(self):
        """_default_categories() returns 5 TriageCategory instances."""
        defaults = _default_categories()
        assert len(defaults) == 5
        assert all(isinstance(c, TriageCategory) for c in defaults)

    def test_default_names(self):
        """Default category names are Imbox, Feed, Paper Trail, Jail, Person."""
        defaults = _default_categories()
        names = [c.name for c in defaults]
        assert names == ["Imbox", "Feed", "Paper Trail", "Jail", "Person"]

    def test_imbox_destination_override(self):
        """Imbox has destination_mailbox='Inbox' override."""
        defaults = _default_categories()
        imbox = next(c for c in defaults if c.name == "Imbox")
        assert imbox.destination_mailbox == "Inbox"

    def test_person_parent_and_contact_type(self):
        """Person has parent='Imbox' and contact_type='person'."""
        defaults = _default_categories()
        person = next(c for c in defaults if c.name == "Person")
        assert person.parent == "Imbox"
        assert person.contact_type == "person"


class TestResolvedCategory:
    """Tests for the ResolvedCategory frozen dataclass."""

    def test_all_fields_concrete(self):
        """ResolvedCategory has all concrete fields (no None except parent)."""
        r = ResolvedCategory(
            name="Feed",
            label="@ToFeed",
            contact_group="Feed",
            destination_mailbox="Feed",
            contact_type="company",
            parent=None,
        )
        assert r.name == "Feed"
        assert r.label == "@ToFeed"
        assert r.contact_group == "Feed"
        assert r.destination_mailbox == "Feed"
        assert r.contact_type == "company"
        assert r.parent is None

    def test_frozen_immutability(self):
        """Attempting to mutate a ResolvedCategory raises FrozenInstanceError."""
        r = ResolvedCategory(
            name="Feed",
            label="@ToFeed",
            contact_group="Feed",
            destination_mailbox="Feed",
            contact_type="company",
            parent=None,
        )
        with pytest.raises(FrozenInstanceError):
            r.name = "Changed"


class TestParentInheritance:
    """Tests for parent-child inheritance in resolve_categories."""

    def test_child_inherits_parent_group_and_mailbox(self):
        """Person (parent='Imbox') inherits contact_group and destination_mailbox from Imbox."""
        cats = [
            TriageCategory(name="Imbox", destination_mailbox="Inbox"),
            TriageCategory(name="Person", parent="Imbox", contact_type="person"),
        ]
        resolved = resolve_categories(cats)
        person = next(r for r in resolved if r.name == "Person")
        assert person.contact_group == "Imbox"
        assert person.destination_mailbox == "Inbox"
        assert person.contact_type == "person"

    def test_child_explicit_override_not_inherited(self):
        """Child with explicit contact_group does NOT inherit parent's group."""
        cats = [
            TriageCategory(name="Imbox", destination_mailbox="Inbox"),
            TriageCategory(
                name="VIP",
                parent="Imbox",
                contact_group="VIPGroup",
            ),
        ]
        resolved = resolve_categories(cats)
        vip = next(r for r in resolved if r.name == "VIP")
        assert vip.contact_group == "VIPGroup"
        # But destination_mailbox IS inherited (not explicitly set)
        assert vip.destination_mailbox == "Inbox"

    def test_parent_after_child_still_resolves(self):
        """Parent appearing after child in list still resolves correctly (two-pass)."""
        cats = [
            TriageCategory(name="Person", parent="Imbox", contact_type="person"),
            TriageCategory(name="Imbox", destination_mailbox="Inbox"),
        ]
        resolved = resolve_categories(cats)
        person = next(r for r in resolved if r.name == "Person")
        assert person.contact_group == "Imbox"
        assert person.destination_mailbox == "Inbox"


# --- Phase 6: Validation Logic ---


class TestValidationEmptyList:
    """Validation rejects empty category lists."""

    def test_empty_list_rejected(self):
        """resolve_categories([]) raises ValueError with 'at least one triage category'."""
        with pytest.raises(ValueError, match="at least one triage category"):
            resolve_categories([])


class TestValidationDuplicateNames:
    """Validation detects duplicate category names."""

    def test_duplicate_names_rejected(self):
        """Two categories named 'Feed' raises ValueError mentioning 'Feed'."""
        cats = [TriageCategory(name="Feed"), TriageCategory(name="Feed")]
        with pytest.raises(ValueError, match="Duplicate category name.*Feed"):
            resolve_categories(cats)


class TestValidationInvalidContactType:
    """Pydantic Literal rejects invalid contact_type values."""

    def test_invalid_contact_type_rejected(self):
        """TriageCategory(name='X', contact_type='invalid') raises ValidationError."""
        with pytest.raises(ValidationError):
            TriageCategory(name="X", contact_type="invalid")


class TestValidationParentReferences:
    """Validation catches non-existent parent references."""

    def test_nonexistent_parent_rejected(self):
        """Parent referencing non-existent category raises ValueError."""
        cats = [TriageCategory(name="Child", parent="Ghost")]
        with pytest.raises(ValueError, match="non-existent parent 'Ghost'"):
            resolve_categories(cats)


class TestValidationCircularParents:
    """Validation detects circular parent chains."""

    def test_circular_parent_chain(self):
        """A -> B -> A raises ValueError with 'Circular parent chain'."""
        cats = [
            TriageCategory(name="A", parent="B"),
            TriageCategory(name="B", parent="A"),
        ]
        with pytest.raises(ValueError, match="Circular parent chain"):
            resolve_categories(cats)

    def test_self_referencing_parent(self):
        """A has parent='A' raises ValueError with 'Circular parent chain'."""
        cats = [TriageCategory(name="A", parent="A")]
        with pytest.raises(ValueError, match="Circular parent chain"):
            resolve_categories(cats)


class TestValidationSharedContactGroups:
    """Validation flags shared contact groups without parent relationship."""

    def test_shared_groups_without_parent_rejected(self):
        """Two unrelated categories with same contact_group raises ValueError."""
        cats = [
            TriageCategory(name="Alpha", contact_group="SharedGroup"),
            TriageCategory(name="Beta", contact_group="SharedGroup"),
        ]
        with pytest.raises(ValueError, match="shared.*contact.*group"):
            resolve_categories(cats)

    def test_shared_groups_with_parent_allowed(self):
        """Parent and child sharing contact_group is allowed."""
        cats = [
            TriageCategory(name="Imbox", destination_mailbox="Inbox"),
            TriageCategory(name="Person", parent="Imbox", contact_type="person"),
        ]
        # Should NOT raise -- parent-child sharing is fine
        resolved = resolve_categories(cats)
        assert len(resolved) == 2


class TestValidationDuplicateLabels:
    """Validation detects duplicate labels after derivation."""

    def test_duplicate_labels_rejected(self):
        """Two categories deriving to the same label raises ValueError."""
        cats = [
            TriageCategory(name="PaperTrail"),
            TriageCategory(name="Custom", label="@ToPaperTrail"),
        ]
        with pytest.raises(ValueError, match="Duplicate.*label.*@ToPaperTrail"):
            resolve_categories(cats)


class TestValidationAllErrorsAtOnce:
    """Validation collects ALL errors and reports them together."""

    def test_multiple_errors_reported_together(self):
        """Categories with BOTH duplicate names AND bad parent -> both errors in message."""
        cats = [
            TriageCategory(name="Feed"),
            TriageCategory(name="Feed"),
            TriageCategory(name="Orphan", parent="Ghost"),
        ]
        with pytest.raises(ValueError) as exc_info:
            resolve_categories(cats)
        msg = str(exc_info.value)
        assert "Duplicate category name" in msg
        assert "non-existent parent" in msg


class TestValidationDefaultConfigInError:
    """Error messages include default configuration for reference."""

    def test_error_includes_default_config(self):
        """When validation fails, error message includes default config JSON."""
        with pytest.raises(ValueError) as exc_info:
            resolve_categories([])
        msg = str(exc_info.value)
        assert "Default configuration for reference" in msg
        assert '"name": "Imbox"' in msg


class TestValidationValidCustomCategory:
    """Valid custom categories resolve successfully."""

    def test_single_custom_category(self):
        """[TriageCategory(name='Receipts')] resolves successfully."""
        cats = [TriageCategory(name="Receipts")]
        resolved = resolve_categories(cats)
        assert len(resolved) == 1
        assert resolved[0].name == "Receipts"
        assert resolved[0].label == "@ToReceipts"
