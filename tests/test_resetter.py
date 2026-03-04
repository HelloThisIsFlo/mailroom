"""Tests for the reset module: plan, apply, reporting."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, call, patch

import pytest

from mailroom.reset.resetter import (
    ContactCleanup,
    ResetPlan,
    ResetResult,
    _is_user_modified,
    apply_reset,
    plan_reset,
)
from mailroom.reset.reporting import print_reset_report


# --- Mock Helpers ---

MAILROOM_HEADER = "\u2014 Mailroom \u2014"


def _make_contact(
    uid: str,
    fn: str,
    emails: list[str],
    note: str,
    vcard_data: str = "",
) -> dict:
    """Build a contact dict as returned by list_all_contacts."""
    return {
        "href": f"/{uid}.vcf",
        "etag": f'"etag-{uid}"',
        "uid": uid,
        "fn": fn,
        "emails": emails,
        "note": note,
        "vcard_data": vcard_data or f"BEGIN:VCARD\nUID:{uid}\nFN:{fn}\nNOTE:{note}\nEND:VCARD",
    }


# --- TestPlanReset ---


class TestPlanReset:
    """Tests for plan_reset() plan building."""

    def test_identifies_annotated_contacts(self, mock_settings) -> None:
        """Contacts with Mailroom note header are included in plan."""
        contacts = [
            _make_contact("uid-1", "Acme Corp", ["acme@example.com"],
                          f"{MAILROOM_HEADER}\nTriaged to Feed on 2026-01-15"),
            _make_contact("uid-2", "No Notes", ["none@example.com"], ""),
            _make_contact("uid-3", "Pre-existing", ["pre@example.com"],
                          "Some old note"),
        ]

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "Imbox": "mb-imbox",
            "@ToFeed": "mb-tofeed", "@ToImbox": "mb-toimbox",
            "@MailroomError": "mb-error", "@MailroomWarning": "mb-warning",
            "Paper Trail": "mb-papertrl", "Jail": "mb-jail",
            "@ToPaperTrail": "mb-topapertrl", "@ToJail": "mb-tojail",
            "Person": "mb-person", "@ToPerson": "mb-toperson",
            "Billboard": "mb-billboard", "@ToBillboard": "mb-tobillboard",
            "Truck": "mb-truck", "@ToTruck": "mb-totruck",
        }
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        carddav._groups = {
            "Feed": {"href": "/feed.vcf", "etag": '"etag"', "uid": "uid-feed"},
            "Imbox": {"href": "/imbox.vcf", "etag": '"etag"', "uid": "uid-imbox"},
        }

        plan = plan_reset(mock_settings, jmap, carddav)

        assert len(plan.contacts_to_clean) == 1
        assert plan.contacts_to_clean[0].uid == "uid-1"

    def test_excludes_screener_and_inbox(self, mock_settings) -> None:
        """Screener and Inbox mailboxes are excluded from label cleanup."""
        jmap = MagicMock()
        # Return IDs for managed mailboxes only (excluding Inbox and Screener)
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "Imbox": "mb-imbox",
            "@ToFeed": "mb-tofeed", "@ToImbox": "mb-toimbox",
            "@MailroomError": "mb-error", "@MailroomWarning": "mb-warning",
            "Paper Trail": "mb-papertrl", "Jail": "mb-jail",
            "@ToPaperTrail": "mb-topapertrl", "@ToJail": "mb-tojail",
            "Person": "mb-person", "@ToPerson": "mb-toperson",
            "Billboard": "mb-billboard", "@ToBillboard": "mb-tobillboard",
            "Truck": "mb-truck", "@ToTruck": "mb-totruck",
        }
        jmap.query_emails.return_value = ["email-1"]

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = []
        carddav._groups = {}

        plan = plan_reset(mock_settings, jmap, carddav)

        # Screener and Inbox should not be in email_labels
        assert "Screener" not in plan.email_labels
        assert "Inbox" not in plan.email_labels

    def test_contacts_without_mailroom_note_excluded(self, mock_settings) -> None:
        """Contacts with no Mailroom note section are excluded."""
        contacts = [
            _make_contact("uid-1", "Plain", ["p@example.com"], "Just a plain note"),
            _make_contact("uid-2", "Empty", ["e@example.com"], ""),
        ]

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "Imbox": "mb-imbox",
            "@ToFeed": "mb-tofeed", "@ToImbox": "mb-toimbox",
            "@MailroomError": "mb-error", "@MailroomWarning": "mb-warning",
            "Paper Trail": "mb-papertrl", "Jail": "mb-jail",
            "@ToPaperTrail": "mb-topapertrl", "@ToJail": "mb-tojail",
            "Person": "mb-person", "@ToPerson": "mb-toperson",
            "Billboard": "mb-billboard", "@ToBillboard": "mb-tobillboard",
            "Truck": "mb-truck", "@ToTruck": "mb-totruck",
        }
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        carddav._groups = {}

        plan = plan_reset(mock_settings, jmap, carddav)

        assert len(plan.contacts_to_clean) == 0

    def test_likely_created_detection(self, mock_settings) -> None:
        """Contact with only managed group memberships and mailroom-only note is likely_created."""
        # Contact whose note is ONLY the mailroom section
        contacts = [
            _make_contact("uid-created", "New Corp", ["new@example.com"],
                          f"{MAILROOM_HEADER}\nTriaged to Feed on 2026-01-15"),
            _make_contact("uid-existing", "Old Corp", ["old@example.com"],
                          f"Pre-existing note\n\n{MAILROOM_HEADER}\nRe-triaged to Imbox on 2026-03-01"),
        ]

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "Imbox": "mb-imbox",
            "@ToFeed": "mb-tofeed", "@ToImbox": "mb-toimbox",
            "@MailroomError": "mb-error", "@MailroomWarning": "mb-warning",
            "Paper Trail": "mb-papertrl", "Jail": "mb-jail",
            "@ToPaperTrail": "mb-topapertrl", "@ToJail": "mb-tojail",
            "Person": "mb-person", "@ToPerson": "mb-toperson",
            "Billboard": "mb-billboard", "@ToBillboard": "mb-tobillboard",
            "Truck": "mb-truck", "@ToTruck": "mb-totruck",
        }
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        # Simulate managed groups with uid-created in Feed, uid-existing in Imbox
        carddav._groups = {
            "Feed": {"href": "/feed.vcf", "etag": '"etag"', "uid": "uid-feed"},
            "Imbox": {"href": "/imbox.vcf", "etag": '"etag"', "uid": "uid-imbox"},
        }

        # Mock get_group_members to return membership data
        def _get_group_members(group_name):
            if group_name == "Feed":
                return ["uid-created"]
            if group_name == "Imbox":
                return ["uid-existing"]
            return []

        carddav.get_group_members.side_effect = _get_group_members

        plan = plan_reset(mock_settings, jmap, carddav)

        created = next(c for c in plan.contacts_to_clean if c.uid == "uid-created")
        existing = next(c for c in plan.contacts_to_clean if c.uid == "uid-existing")

        assert created.likely_created is True
        assert existing.likely_created is False

    def test_plan_includes_correct_email_counts(self, mock_settings) -> None:
        """Plan correctly maps mailbox names to email IDs."""
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "Imbox": "mb-imbox",
            "@ToFeed": "mb-tofeed", "@ToImbox": "mb-toimbox",
            "@MailroomError": "mb-error", "@MailroomWarning": "mb-warning",
            "Paper Trail": "mb-papertrl", "Jail": "mb-jail",
            "@ToPaperTrail": "mb-topapertrl", "@ToJail": "mb-tojail",
            "Person": "mb-person", "@ToPerson": "mb-toperson",
            "Billboard": "mb-billboard", "@ToBillboard": "mb-tobillboard",
            "Truck": "mb-truck", "@ToTruck": "mb-totruck",
        }

        def _query_emails(mailbox_id, **kwargs):
            if mailbox_id == "mb-feed":
                return ["e1", "e2", "e3"]
            if mailbox_id == "mb-toimbox":
                return ["e4"]
            return []

        jmap.query_emails.side_effect = _query_emails

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = []
        carddav._groups = {}

        plan = plan_reset(mock_settings, jmap, carddav)

        assert plan.email_labels.get("Feed") == ["e1", "e2", "e3"]
        assert plan.email_labels.get("@ToImbox") == ["e4"]


# --- TestApplyReset ---


class TestApplyReset:
    """Tests for apply_reset() execution."""

    def _make_plan(self) -> ResetPlan:
        """Build a simple reset plan for testing."""
        return ResetPlan(
            email_labels={
                "Feed": ["e1", "e2"],
                "@ToImbox": ["e3"],
            },
            group_members={
                "Feed": ["uid-1", "uid-2"],
                "Imbox": ["uid-3"],
            },
            contacts_to_clean=[
                ContactCleanup(
                    href="/uid-1.vcf",
                    etag='"etag-1"',
                    fn="Acme Corp",
                    uid="uid-1",
                    note=f"{MAILROOM_HEADER}\nTriaged to Feed on 2026-01-15",
                    stripped_note="",
                    likely_created=True,
                    vcard_data=f"BEGIN:VCARD\nUID:uid-1\nFN:Acme Corp\nNOTE:{MAILROOM_HEADER}\\nTriaged to Feed on 2026-01-15\nEND:VCARD",
                ),
                ContactCleanup(
                    href="/uid-2.vcf",
                    etag='"etag-2"',
                    fn="Old Corp",
                    uid="uid-2",
                    note=f"Pre-existing note\n\n{MAILROOM_HEADER}\nRe-triaged to Imbox on 2026-03-01",
                    stripped_note="Pre-existing note",
                    likely_created=False,
                    vcard_data=f"BEGIN:VCARD\nUID:uid-2\nFN:Old Corp\nNOTE:Pre-existing note\\n\\n{MAILROOM_HEADER}\\nRe-triaged to Imbox on 2026-03-01\nEND:VCARD",
                ),
            ],
        )

    def test_label_removal_calls(self, mock_settings) -> None:
        """apply_reset calls batch_remove_labels for each managed label."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
        }
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        result = apply_reset(plan, jmap, carddav, mock_settings)

        # batch_remove_labels should be called for Feed and @ToImbox
        assert jmap.batch_remove_labels.call_count == 2

    def test_group_emptying_calls(self, mock_settings) -> None:
        """apply_reset calls remove_from_group for each member in each group."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
        }
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        result = apply_reset(plan, jmap, carddav, mock_settings)

        # remove_from_group: Feed(uid-1, uid-2) + Imbox(uid-3) = 3 calls
        assert carddav.remove_from_group.call_count == 3

    def test_note_stripping_mailroom_only(self, mock_settings) -> None:
        """Note that is ONLY mailroom section gets cleared to empty."""
        plan = ResetPlan(
            email_labels={},
            group_members={},
            contacts_to_clean=[
                ContactCleanup(
                    href="/uid-1.vcf",
                    etag='"etag-1"',
                    fn="Acme Corp",
                    uid="uid-1",
                    note=f"{MAILROOM_HEADER}\nTriaged to Feed on 2026-01-15",
                    stripped_note="",
                    likely_created=True,
                    vcard_data=f"BEGIN:VCARD\nVERSION:3.0\nUID:uid-1\nFN:Acme Corp\nNOTE:{MAILROOM_HEADER}\\nTriaged to Feed on 2026-01-15\nEND:VCARD",
                ),
            ],
        )
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {}
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        result = apply_reset(plan, jmap, carddav, mock_settings)

        # The vcard_bytes passed to update_contact_vcard should have empty/no NOTE
        assert carddav.update_contact_vcard.call_count == 1
        call_args = carddav.update_contact_vcard.call_args
        vcard_bytes = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("vcard_bytes", b"")
        vcard_str = vcard_bytes.decode("utf-8") if isinstance(vcard_bytes, bytes) else str(vcard_bytes)
        # NOTE should be empty or not contain the Mailroom header
        assert MAILROOM_HEADER not in vcard_str

    def test_note_stripping_preserves_preexisting(self, mock_settings) -> None:
        """Note with pre-existing content preserves the pre-existing text."""
        plan = ResetPlan(
            email_labels={},
            group_members={},
            contacts_to_clean=[
                ContactCleanup(
                    href="/uid-2.vcf",
                    etag='"etag-2"',
                    fn="Old Corp",
                    uid="uid-2",
                    note=f"Pre-existing note\n\n{MAILROOM_HEADER}\nRe-triaged to Imbox on 2026-03-01",
                    stripped_note="Pre-existing note",
                    likely_created=False,
                    vcard_data=f"BEGIN:VCARD\nVERSION:3.0\nUID:uid-2\nFN:Old Corp\nNOTE:Pre-existing note\\n\\n{MAILROOM_HEADER}\\nRe-triaged to Imbox on 2026-03-01\nEND:VCARD",
                ),
            ],
        )
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {}
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        result = apply_reset(plan, jmap, carddav, mock_settings)

        call_args = carddav.update_contact_vcard.call_args
        vcard_bytes = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("vcard_bytes", b"")
        vcard_str = vcard_bytes.decode("utf-8") if isinstance(vcard_bytes, bytes) else str(vcard_bytes)
        assert "Pre-existing note" in vcard_str
        assert MAILROOM_HEADER not in vcard_str

    def test_operation_order(self, mock_settings) -> None:
        """Operations execute in order: labels, groups, notes."""
        plan = self._make_plan()
        call_order = []

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
        }
        jmap.batch_remove_labels.side_effect = lambda *a, **kw: call_order.append("labels")

        carddav = MagicMock()
        carddav.remove_from_group.side_effect = lambda *a, **kw: call_order.append("groups")
        carddav.update_contact_vcard.side_effect = lambda *a, **kw: call_order.append("notes")

        apply_reset(plan, jmap, carddav, mock_settings)

        # All label ops before all group ops before all note ops
        label_indices = [i for i, x in enumerate(call_order) if x == "labels"]
        group_indices = [i for i, x in enumerate(call_order) if x == "groups"]
        note_indices = [i for i, x in enumerate(call_order) if x == "notes"]

        assert max(label_indices) < min(group_indices)
        assert max(group_indices) < min(note_indices)

    def test_result_counts(self, mock_settings) -> None:
        """ResetResult has correct counts."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
        }
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        result = apply_reset(plan, jmap, carddav, mock_settings)

        assert result.emails_unlabeled == 3  # e1, e2, e3
        assert result.groups_emptied == 2  # Feed, Imbox
        assert result.contacts_cleaned == 2
        assert result.errors == []


# --- TestResetReporting ---


class TestResetReporting:
    """Tests for print_reset_report() output formatting."""

    def test_dry_run_report(self, capsys) -> None:
        """Dry-run report shows counts per section."""
        plan = ResetPlan(
            email_labels={
                "Feed": ["e1", "e2"],
                "@ToImbox": ["e3"],
            },
            group_members={
                "Feed": ["uid-1", "uid-2"],
            },
            contacts_to_clean=[
                ContactCleanup(
                    href="/uid-1.vcf", etag='"etag"', fn="Acme Corp",
                    uid="uid-1", note="note", stripped_note="",
                    likely_created=False, vcard_data="",
                ),
            ],
        )

        print_reset_report(plan, apply=False)
        output = capsys.readouterr().out

        assert "Email Labels" in output
        assert "Feed" in output
        assert "2" in output  # 2 emails in Feed
        assert "Contact Groups" in output
        assert "Contacts" in output
        assert "Acme Corp" in output

    def test_likely_created_section(self, capsys) -> None:
        """Likely-created contacts appear in separate section."""
        plan = ResetPlan(
            email_labels={},
            group_members={},
            contacts_to_clean=[
                ContactCleanup(
                    href="/uid-1.vcf", etag='"etag"', fn="Likely Corp",
                    uid="uid-1", note="note", stripped_note="",
                    likely_created=True, vcard_data="",
                ),
                ContactCleanup(
                    href="/uid-2.vcf", etag='"etag"', fn="Old Corp",
                    uid="uid-2", note="note", stripped_note="pre",
                    likely_created=False, vcard_data="",
                ),
            ],
        )

        print_reset_report(plan, apply=False)
        output = capsys.readouterr().out

        assert "Likely Mailroom-Created" in output
        assert "Likely Corp" in output
        assert "manual deletion" in output.lower() or "manual" in output.lower()

    def test_apply_report(self, capsys) -> None:
        """Apply report shows result counts."""
        result = ResetResult(
            emails_unlabeled=5,
            groups_emptied=3,
            contacts_cleaned=2,
            errors=[],
        )

        print_reset_report(result, apply=True)
        output = capsys.readouterr().out

        assert "5" in output
        assert "3" in output
        assert "2" in output


# --- TestIsUserModified ---


class TestIsUserModified:
    """Tests for _is_user_modified() vCard field detection."""

    def _make_vcard(self, extra_fields: str = "") -> str:
        """Build a minimal vCard string with optional extra fields."""
        return (
            "BEGIN:VCARD\r\n"
            "VERSION:3.0\r\n"
            "UID:test-uid\r\n"
            "FN:Test Corp\r\n"
            "N:;;;\r\n"
            "EMAIL;TYPE=INTERNET:test@example.com\r\n"
            "NOTE:— Mailroom —\\nCreated by Mailroom\r\n"
            "ORG:Test Corp\r\n"
            "PRODID:-//Apple Inc.//Fastmail//EN\r\n"
            f"{extra_fields}"
            "END:VCARD\r\n"
        )

    def test_unmodified_returns_false(self) -> None:
        """Contact with only Mailroom-managed fields is NOT user-modified."""
        vcard = self._make_vcard()
        assert _is_user_modified(vcard) is False

    def test_tel_field_returns_true(self) -> None:
        """Contact with TEL field IS user-modified."""
        vcard = self._make_vcard("TEL;TYPE=CELL:+1234567890\r\n")
        assert _is_user_modified(vcard) is True

    def test_additional_email_returns_true(self) -> None:
        """Contact with multiple EMAIL entries IS user-modified."""
        vcard = self._make_vcard("EMAIL;TYPE=INTERNET:second@example.com\r\n")
        assert _is_user_modified(vcard) is True

    def test_adr_returns_true(self) -> None:
        """Contact with ADR field IS user-modified."""
        vcard = self._make_vcard("ADR:;;123 Main St;City;CA;90210;US\r\n")
        assert _is_user_modified(vcard) is True

    def test_url_returns_true(self) -> None:
        """Contact with URL field IS user-modified."""
        vcard = self._make_vcard("URL:https://example.com\r\n")
        assert _is_user_modified(vcard) is True

    def test_bday_returns_true(self) -> None:
        """Contact with BDAY field IS user-modified."""
        vcard = self._make_vcard("BDAY:1990-01-15\r\n")
        assert _is_user_modified(vcard) is True

    def test_title_returns_true(self) -> None:
        """Contact with TITLE field IS user-modified."""
        vcard = self._make_vcard("TITLE:CEO\r\n")
        assert _is_user_modified(vcard) is True

    def test_nickname_returns_true(self) -> None:
        """Contact with NICKNAME field IS user-modified."""
        vcard = self._make_vcard("NICKNAME:TestNick\r\n")
        assert _is_user_modified(vcard) is True

    def test_photo_returns_true(self) -> None:
        """Contact with PHOTO field IS user-modified."""
        vcard = self._make_vcard("PHOTO;VALUE=uri:https://example.com/photo.jpg\r\n")
        assert _is_user_modified(vcard) is True

    def test_apple_system_fields_not_treated_as_user(self) -> None:
        """x-addressbookserver-* fields are system fields, not user data."""
        vcard = self._make_vcard(
            "X-ADDRESSBOOKSERVER-KIND:individual\r\n"
            "X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:abc\r\n"
        )
        assert _is_user_modified(vcard) is False
