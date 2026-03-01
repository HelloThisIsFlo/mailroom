"""Tests for the YAML-based configuration module."""

import pytest
from pydantic import ValidationError

from mailroom.core.config import MailroomSettings, ResolvedCategory


# ---------------------------------------------------------------------------
# Phase 9.1: YAML-based config with nested sub-models
# ---------------------------------------------------------------------------


class TestYAMLConfigDefaults:
    """MailroomSettings loads defaults when config.yaml has no overrides."""

    def test_defaults_with_empty_yaml(self, monkeypatch, tmp_path):
        """Empty config.yaml gives sensible defaults for all nested fields."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "test-token-abc")

        settings = MailroomSettings()

        assert settings.jmap_token == "test-token-abc"
        assert settings.carddav_password == ""
        # Nested access paths
        assert settings.polling.interval == 60
        assert settings.polling.debounce_seconds == 3
        assert settings.logging.level == "info"
        assert settings.labels.mailroom_error == "@MailroomError"
        assert settings.labels.mailroom_warning == "@MailroomWarning"
        assert settings.labels.warnings_enabled is True
        assert settings.triage.screener_mailbox == "Screener"

    def test_default_triage_categories(self, monkeypatch, tmp_path):
        """Default triage categories: 5 entries with correct names."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert len(settings.triage.categories) == 5
        names = [c.name for c in settings.triage.categories]
        assert names == ["Imbox", "Feed", "Paper Trail", "Jail", "Person"]

    def test_default_triage_labels(self, monkeypatch, tmp_path):
        """Triage labels match v1.0 defaults via computed property on root."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert settings.triage_labels == [
            "@ToImbox", "@ToFeed", "@ToPaperTrail", "@ToJail", "@ToPerson"
        ]


class TestYAMLConfigOverrides:
    """Config values from YAML override defaults."""

    def test_polling_override(self, monkeypatch, tmp_path):
        """polling.interval from YAML overrides default."""
        config = tmp_path / "config.yaml"
        config.write_text("polling:\n  interval: 120\n  debounce_seconds: 5\n")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert settings.polling.interval == 120
        assert settings.polling.debounce_seconds == 5

    def test_logging_override(self, monkeypatch, tmp_path):
        """logging.level from YAML overrides default."""
        config = tmp_path / "config.yaml"
        config.write_text("logging:\n  level: debug\n")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert settings.logging.level == "debug"

    def test_labels_override(self, monkeypatch, tmp_path):
        """labels section from YAML overrides defaults."""
        config = tmp_path / "config.yaml"
        config.write_text(
            "labels:\n"
            "  mailroom_error: '@CustomError'\n"
            "  warnings_enabled: false\n"
        )
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert settings.labels.mailroom_error == "@CustomError"
        assert settings.labels.warnings_enabled is False

    def test_screener_mailbox_override(self, monkeypatch, tmp_path):
        """triage.screener_mailbox from YAML overrides default."""
        config = tmp_path / "config.yaml"
        config.write_text("triage:\n  screener_mailbox: MyScreener\n")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert settings.triage.screener_mailbox == "MyScreener"

    def test_custom_categories_via_yaml(self, monkeypatch, tmp_path):
        """Custom categories via YAML triage.categories replaces all defaults."""
        config = tmp_path / "config.yaml"
        config.write_text(
            "triage:\n"
            "  categories:\n"
            "    - name: Receipts\n"
            "    - name: VIP\n"
            "      destination_mailbox: Inbox\n"
        )
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert len(settings.triage.categories) == 2
        assert settings.triage_labels == ["@ToReceipts", "@ToVIP"]
        mapping = settings.label_to_category_mapping
        assert mapping["@ToReceipts"].destination_mailbox == "Receipts"
        assert mapping["@ToVIP"].destination_mailbox == "Inbox"


class TestNameOnlyShorthand:
    """Name-only shorthand ('- Feed') works in YAML triage categories."""

    def test_string_shorthand(self, monkeypatch, tmp_path):
        """Plain string '- Feed' in YAML is equivalent to '- name: Feed'."""
        config = tmp_path / "config.yaml"
        config.write_text(
            "triage:\n"
            "  categories:\n"
            "    - Feed\n"
            "    - Paper Trail\n"
        )
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert len(settings.triage.categories) == 2
        assert settings.triage.categories[0].name == "Feed"
        assert settings.triage.categories[1].name == "Paper Trail"
        assert settings.triage_labels == ["@ToFeed", "@ToPaperTrail"]

    def test_mixed_shorthand_and_dict(self, monkeypatch, tmp_path):
        """Mix of string shorthand and dict form works."""
        config = tmp_path / "config.yaml"
        config.write_text(
            "triage:\n"
            "  categories:\n"
            "    - name: Imbox\n"
            "      destination_mailbox: Inbox\n"
            "    - Feed\n"
            "    - name: Person\n"
            "      parent: Imbox\n"
            "      contact_type: person\n"
        )
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert len(settings.triage.categories) == 3
        names = [c.name for c in settings.triage.categories]
        assert names == ["Imbox", "Feed", "Person"]


class TestMissingConfigYAML:
    """Missing config.yaml fails fast with clear error."""

    def test_missing_config_exits(self, monkeypatch, tmp_path, capsys):
        """Missing config.yaml raises SystemExit(1) with helpful stderr message."""
        monkeypatch.setenv("MAILROOM_CONFIG", str(tmp_path / "nonexistent.yaml"))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        with pytest.raises(SystemExit) as exc_info:
            MailroomSettings()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "config.yaml.example" in captured.err


class TestMAILROOM_CONFIG_Override:
    """MAILROOM_CONFIG env var overrides default config.yaml path."""

    def test_config_path_override(self, monkeypatch, tmp_path):
        """MAILROOM_CONFIG points to a custom path."""
        custom_config = tmp_path / "custom" / "my-config.yaml"
        custom_config.parent.mkdir(parents=True)
        custom_config.write_text("polling:\n  interval: 999\n")
        monkeypatch.setenv("MAILROOM_CONFIG", str(custom_config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert settings.polling.interval == 999


class TestAuthEnvVarsStayFlat:
    """Auth credentials remain as flat env vars on root MailroomSettings."""

    def test_auth_fields_flat(self, monkeypatch, tmp_path):
        """Auth fields are directly on settings root, not nested."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "my-token")
        monkeypatch.setenv("MAILROOM_CARDDAV_USERNAME", "user@fastmail.com")
        monkeypatch.setenv("MAILROOM_CARDDAV_PASSWORD", "secret")

        settings = MailroomSettings()

        assert settings.jmap_token == "my-token"
        assert settings.carddav_username == "user@fastmail.com"
        assert settings.carddav_password == "secret"

    def test_required_jmap_token(self, monkeypatch, tmp_path):
        """Missing MAILROOM_JMAP_TOKEN causes a validation error."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))

        with pytest.raises(ValidationError) as exc_info:
            MailroomSettings()

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("jmap_token",) for e in errors)


class TestComputedProperties:
    """Computed properties stay on root and access nested sub-models."""

    def test_label_category_mapping(self, monkeypatch, tmp_path):
        """label_to_category_mapping returns correct associations."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()
        mapping = settings.label_to_category_mapping

        imbox = mapping["@ToImbox"]
        assert isinstance(imbox, ResolvedCategory)
        assert imbox.contact_group == "Imbox"
        assert imbox.destination_mailbox == "Inbox"
        assert imbox.contact_type == "company"

        person = mapping["@ToPerson"]
        assert person.contact_type == "person"
        assert person.contact_group == "Imbox"
        assert person.destination_mailbox == "Inbox"

        assert len(mapping) == 5

    def test_required_mailboxes_includes_all(self, monkeypatch, tmp_path):
        """required_mailboxes includes triage labels, destinations, screener, and error."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()
        required = settings.required_mailboxes

        for label in settings.triage_labels:
            assert label in required
        assert "@MailroomWarning" in required
        assert "@MailroomError" in required
        assert "Inbox" in required
        assert "Screener" in required

    def test_required_mailboxes_without_warnings(self, monkeypatch, tmp_path):
        """required_mailboxes excludes @MailroomWarning when warnings disabled."""
        config = tmp_path / "config.yaml"
        config.write_text("labels:\n  warnings_enabled: false\n")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()

        assert settings.labels.warnings_enabled is False
        assert "@MailroomWarning" not in settings.required_mailboxes

    def test_contact_groups_unique(self, monkeypatch, tmp_path):
        """contact_groups returns unique groups (Person shares Imbox)."""
        config = tmp_path / "config.yaml"
        config.write_text("")
        monkeypatch.setenv("MAILROOM_CONFIG", str(config))
        monkeypatch.setenv("MAILROOM_JMAP_TOKEN", "tok")

        settings = MailroomSettings()
        groups = settings.contact_groups

        assert len(groups) == 4
        assert "Imbox" in groups
        assert "Feed" in groups
        assert "Paper Trail" in groups
        assert "Jail" in groups


# ---------------------------------------------------------------------------
# Phase 6: TriageCategory, ResolvedCategory, Derivation, Defaults, Validation
# (these tests are unchanged — they test models/functions directly, not settings)
# ---------------------------------------------------------------------------

from dataclasses import FrozenInstanceError

from mailroom.core.config import (
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
        """Person (parent='Imbox') inherits contact_group and destination_mailbox."""
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
            TriageCategory(name="VIP", parent="Imbox", contact_group="VIPGroup"),
        ]
        resolved = resolve_categories(cats)
        vip = next(r for r in resolved if r.name == "VIP")
        assert vip.contact_group == "VIPGroup"
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


# --- Validation Logic ---


class TestValidationEmptyList:
    def test_empty_list_rejected(self):
        with pytest.raises(ValueError, match="(?i)at least one triage category"):
            resolve_categories([])


class TestValidationDuplicateNames:
    def test_duplicate_names_rejected(self):
        cats = [TriageCategory(name="Feed"), TriageCategory(name="Feed")]
        with pytest.raises(ValueError, match="Duplicate category name.*Feed"):
            resolve_categories(cats)


class TestValidationInvalidContactType:
    def test_invalid_contact_type_rejected(self):
        with pytest.raises(ValidationError):
            TriageCategory(name="X", contact_type="invalid")


class TestValidationParentReferences:
    def test_nonexistent_parent_rejected(self):
        cats = [TriageCategory(name="Child", parent="Ghost")]
        with pytest.raises(ValueError, match="non-existent parent 'Ghost'"):
            resolve_categories(cats)


class TestValidationCircularParents:
    def test_circular_parent_chain(self):
        cats = [
            TriageCategory(name="A", parent="B"),
            TriageCategory(name="B", parent="A"),
        ]
        with pytest.raises(ValueError, match="Circular parent chain"):
            resolve_categories(cats)

    def test_self_referencing_parent(self):
        cats = [TriageCategory(name="A", parent="A")]
        with pytest.raises(ValueError, match="Circular parent chain"):
            resolve_categories(cats)


class TestValidationSharedContactGroups:
    def test_shared_groups_without_parent_rejected(self):
        cats = [
            TriageCategory(name="Alpha", contact_group="SharedGroup"),
            TriageCategory(name="Beta", contact_group="SharedGroup"),
        ]
        with pytest.raises(ValueError, match="share contact group"):
            resolve_categories(cats)

    def test_shared_groups_with_parent_allowed(self):
        cats = [
            TriageCategory(name="Imbox", destination_mailbox="Inbox"),
            TriageCategory(name="Person", parent="Imbox", contact_type="person"),
        ]
        resolved = resolve_categories(cats)
        assert len(resolved) == 2


class TestValidationDuplicateLabels:
    def test_duplicate_labels_rejected(self):
        cats = [
            TriageCategory(name="PaperTrail"),
            TriageCategory(name="Custom", label="@ToPaperTrail"),
        ]
        with pytest.raises(ValueError, match="Duplicate.*label.*@ToPaperTrail"):
            resolve_categories(cats)


class TestValidationAllErrorsAtOnce:
    def test_multiple_errors_reported_together(self):
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
    def test_error_includes_default_config(self):
        with pytest.raises(ValueError) as exc_info:
            resolve_categories([])
        msg = str(exc_info.value)
        assert "Default configuration for reference" in msg
        assert '"name": "Imbox"' in msg


class TestValidationValidCustomCategory:
    def test_single_custom_category(self):
        cats = [TriageCategory(name="Receipts")]
        resolved = resolve_categories(cats)
        assert len(resolved) == 1
        assert resolved[0].name == "Receipts"
        assert resolved[0].label == "@ToReceipts"
