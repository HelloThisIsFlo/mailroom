"""Tests for the setup provisioner: plan, apply, reporting, and CLI wiring."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest

from mailroom.setup.provisioner import apply_resources, plan_resources
from mailroom.setup.reporting import ResourceAction, print_plan


# --- Mock Helpers ---


def _make_mailbox_list(names: list[str]) -> list[dict]:
    """Build a JMAP Mailbox/get response list from names."""
    result = []
    for i, name in enumerate(names):
        mb: dict = {"id": f"mb-{i}", "name": name, "parentId": None}
        if name == "Inbox":
            mb["role"] = "inbox"
        else:
            mb["role"] = None
        result.append(mb)
    return result


def _mock_jmap(existing_mailboxes: list[str]) -> MagicMock:
    """Create a mock JMAPClient with Mailbox/get returning given names."""
    jmap = MagicMock()
    jmap.account_id = "u1234"
    mailbox_list = _make_mailbox_list(existing_mailboxes)
    jmap.call.return_value = [["Mailbox/get", {"list": mailbox_list}, "m0"]]
    return jmap


def _mock_carddav(existing_groups: list[str]) -> MagicMock:
    """Create a mock CardDAVClient with list_groups returning given names."""
    carddav = MagicMock()
    carddav.list_groups.return_value = {
        name: {"href": f"/{name}.vcf", "etag": '"etag"', "uid": f"uid-{name}"}
        for name in existing_groups
    }
    return carddav


# --- Plan Tests ---


class TestPlanResources:
    """Tests for plan_resources() resource discovery."""

    def test_all_exist(self, mock_settings) -> None:
        """When all resources exist, every action has status 'exists'."""
        all_mailboxes = list(mock_settings.required_mailboxes)
        all_groups = list(mock_settings.contact_groups)

        jmap = _mock_jmap(all_mailboxes)
        carddav = _mock_carddav(all_groups)

        actions = plan_resources(mock_settings, jmap, carddav)

        assert all(a.status == "exists" for a in actions)
        assert len(actions) > 0

    def test_some_missing(self, mock_settings) -> None:
        """Missing mailboxes and groups get status 'create'."""
        # Provide all except Feed mailbox and Feed group
        mailboxes = [
            n for n in mock_settings.required_mailboxes if n != "Feed"
        ]
        groups = [g for g in mock_settings.contact_groups if g != "Feed"]

        jmap = _mock_jmap(mailboxes)
        carddav = _mock_carddav(groups)

        actions = plan_resources(mock_settings, jmap, carddav)

        feed_mailbox = next(
            a for a in actions if a.name == "Feed" and a.kind == "mailbox"
        )
        assert feed_mailbox.status == "create"

        feed_group = next(
            a for a in actions if a.name == "Feed" and a.kind == "contact_group"
        )
        assert feed_group.status == "create"

        # Others should exist
        inbox = next(a for a in actions if a.name == "Inbox")
        assert inbox.status == "exists"

    def test_categorizes_correctly(self, mock_settings) -> None:
        """Resources are categorized into mailbox, label, contact_group, mailroom."""
        all_mailboxes = list(mock_settings.required_mailboxes)
        all_groups = list(mock_settings.contact_groups)

        jmap = _mock_jmap(all_mailboxes)
        carddav = _mock_carddav(all_groups)

        actions = plan_resources(mock_settings, jmap, carddav)

        # Action Labels should contain triage labels
        label_names = {a.name for a in actions if a.kind == "label"}
        assert "@ToImbox" in label_names
        assert "@ToFeed" in label_names
        assert "@ToPaperTrail" in label_names
        assert "@ToJail" in label_names
        assert "@ToPerson" in label_names

        # Mailboxes should contain system + destination (NOT triage labels or mailroom)
        mailbox_names = {a.name for a in actions if a.kind == "mailbox"}
        assert "Inbox" in mailbox_names
        assert "Screener" in mailbox_names
        assert "Feed" in mailbox_names
        # Triage labels should NOT be in mailbox kind
        assert "@ToImbox" not in mailbox_names
        assert "@ToFeed" not in mailbox_names
        # Mailroom-specific should NOT be in mailbox kind
        assert "@MailroomError" not in mailbox_names
        assert "@MailroomWarning" not in mailbox_names

        # Mailroom-specific
        mailroom_names = {a.name for a in actions if a.kind == "mailroom"}
        assert "@MailroomError" in mailroom_names
        assert "@MailroomWarning" in mailroom_names

        # Contact Groups
        group_names = {a.name for a in actions if a.kind == "contact_group"}
        assert "Imbox" in group_names
        assert "Feed" in group_names
        assert "Paper Trail" in group_names
        assert "Jail" in group_names


# --- Apply Tests ---


class TestApplyResources:
    """Tests for apply_resources() resource creation."""

    def test_creates_missing(self) -> None:
        """Resources with 'create' status become 'created' on success."""
        plan = [
            ResourceAction(kind="mailbox", name="Inbox", status="exists"),
            ResourceAction(kind="mailbox", name="Feed", status="create"),
            ResourceAction(kind="contact_group", name="Feed", status="create"),
        ]

        jmap = MagicMock()
        jmap.create_mailbox.return_value = "new-mb-id"
        carddav = MagicMock()
        carddav.create_group.return_value = {
            "href": "/feed.vcf",
            "etag": '"etag"',
            "uid": "uid-feed",
        }

        result = apply_resources(plan, jmap, carddav)

        assert result[0].status == "exists"  # Inbox unchanged
        assert result[1].status == "created"  # Feed mailbox created
        assert result[2].status == "created"  # Feed group created
        jmap.create_mailbox.assert_called_once_with("Feed")
        carddav.create_group.assert_called_once_with("Feed")

    def test_handles_failure(self) -> None:
        """Failed mailbox creation sets status to 'failed' with error."""
        plan = [
            ResourceAction(kind="mailbox", name="Feed", status="create"),
        ]

        jmap = MagicMock()
        jmap.create_mailbox.side_effect = RuntimeError("403 Forbidden")
        carddav = MagicMock()

        result = apply_resources(plan, jmap, carddav)

        assert result[0].status == "failed"
        assert "403 Forbidden" in result[0].error

    def test_skips_children_on_parent_failure(self) -> None:
        """Child resources get 'skipped' when their parent failed."""
        plan = [
            ResourceAction(
                kind="mailbox", name="Parent", status="create"
            ),
            ResourceAction(
                kind="mailbox", name="Child", status="create", parent="Parent"
            ),
        ]

        jmap = MagicMock()
        jmap.create_mailbox.side_effect = RuntimeError("creation failed")
        carddav = MagicMock()

        result = apply_resources(plan, jmap, carddav)

        assert result[0].status == "failed"
        assert result[1].status == "skipped"
        assert result[1].error == "parent failed"
        # create_mailbox only called once (for Parent, not Child)
        jmap.create_mailbox.assert_called_once_with("Parent")

    def test_existing_resources_unchanged(self) -> None:
        """Resources with 'exists' status pass through without API calls."""
        plan = [
            ResourceAction(kind="mailbox", name="Inbox", status="exists"),
            ResourceAction(kind="label", name="@ToFeed", status="exists"),
            ResourceAction(
                kind="contact_group", name="Feed", status="exists"
            ),
        ]

        jmap = MagicMock()
        carddav = MagicMock()

        result = apply_resources(plan, jmap, carddav)

        assert all(a.status == "exists" for a in result)
        jmap.create_mailbox.assert_not_called()
        carddav.create_group.assert_not_called()


# --- Reporting Tests ---


class TestReporting:
    """Tests for print_plan() output formatting."""

    def test_dry_run_output(self, capsys) -> None:
        """Dry-run output shows section headers, symbols, and summary."""
        actions = [
            ResourceAction(kind="mailbox", name="Inbox", status="exists"),
            ResourceAction(kind="mailbox", name="Feed", status="create"),
            ResourceAction(kind="label", name="@ToFeed", status="create"),
            ResourceAction(kind="label", name="@ToImbox", status="exists"),
            ResourceAction(
                kind="contact_group", name="Imbox", status="exists"
            ),
            ResourceAction(
                kind="contact_group", name="Feed", status="create"
            ),
            ResourceAction(
                kind="mailroom", name="@MailroomError", status="exists"
            ),
        ]

        print_plan(actions, apply=False)
        output = capsys.readouterr().out

        # Section headers (4 categories)
        assert "Mailboxes" in output
        assert "Action Labels" in output
        assert "Contact Groups" in output
        assert "\nMailroom\n" in output

        # Status symbols
        assert "\u2713" in output  # checkmark for exists
        assert "+" in output  # plus for create

        # Summary line
        assert "3 to create" in output
        assert "4 existing" in output

    def test_apply_output_with_failures(self, capsys) -> None:
        """Apply output shows created/failed counts in summary."""
        actions = [
            ResourceAction(kind="mailbox", name="Inbox", status="exists"),
            ResourceAction(kind="mailbox", name="Feed", status="created"),
            ResourceAction(
                kind="mailbox",
                name="Jail",
                status="failed",
                error="403 Forbidden",
            ),
            ResourceAction(
                kind="contact_group", name="Feed", status="created"
            ),
        ]

        print_plan(actions, apply=True)
        output = capsys.readouterr().out

        assert "2 created" in output
        assert "1 existing" in output
        assert "1 failed" in output
        assert "FAILED: 403 Forbidden" in output

    def test_no_color_when_not_tty(self, capsys) -> None:
        """Output has no ANSI escape codes when stdout is not a TTY."""
        actions = [
            ResourceAction(kind="mailbox", name="Inbox", status="exists"),
            ResourceAction(kind="mailbox", name="Feed", status="create"),
            ResourceAction(
                kind="mailbox",
                name="Jail",
                status="failed",
                error="403 Forbidden",
            ),
            ResourceAction(
                kind="mailroom", name="@MailroomError", status="exists"
            ),
        ]

        print_plan(actions, apply=False)
        output = capsys.readouterr().out

        # capsys is not a TTY, so no ANSI escape codes
        assert "\033[" not in output

    def test_skipped_output(self, capsys) -> None:
        """Skipped resources show circle-slash symbol and reason."""
        actions = [
            ResourceAction(
                kind="mailbox",
                name="Child",
                status="skipped",
                parent="Parent",
                error="parent failed",
            ),
        ]

        print_plan(actions, apply=True)
        output = capsys.readouterr().out

        assert "\u2298" in output  # circle-slash
        assert "skipped (parent failed)" in output
        assert "1 skipped" in output
