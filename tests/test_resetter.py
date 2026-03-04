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
        "vcard_data": vcard_data or f"BEGIN:VCARD\nVERSION:3.0\nUID:{uid}\nFN:{fn}\nEMAIL:{emails[0] if emails else ''}\nNOTE:{note}\nEND:VCARD",
    }


def _make_provenance_vcard(uid: str, fn: str, email: str, extra_fields: str = "") -> str:
    """Build a vCard string with only Mailroom-managed fields (unmodified)."""
    return (
        f"BEGIN:VCARD\r\n"
        f"VERSION:3.0\r\n"
        f"UID:{uid}\r\n"
        f"FN:{fn}\r\n"
        f"N:;;;\r\n"
        f"EMAIL;TYPE=INTERNET:{email}\r\n"
        f"NOTE:{MAILROOM_HEADER}\\nCreated by Mailroom\\nTriaged to Feed on 2026-01-15\r\n"
        f"ORG:{fn}\r\n"
        f"{extra_fields}"
        f"END:VCARD\r\n"
    )


def _make_modified_vcard(uid: str, fn: str, email: str) -> str:
    """Build a vCard string with user-added TEL field (modified)."""
    return _make_provenance_vcard(uid, fn, email, "TEL;TYPE=CELL:+1234567890\r\n")


# Standard mailbox resolution for tests
_STANDARD_MAILBOXES = {
    "Feed": "mb-feed", "Imbox": "mb-imbox",
    "@ToFeed": "mb-tofeed", "@ToImbox": "mb-toimbox",
    "@MailroomError": "mb-error", "@MailroomWarning": "mb-warning",
    "Paper Trail": "mb-papertrl", "Jail": "mb-jail",
    "@ToPaperTrail": "mb-topapertrl", "@ToJail": "mb-tojail",
    "Person": "mb-person", "@ToPerson": "mb-toperson",
    "Billboard": "mb-billboard", "@ToBillboard": "mb-tobillboard",
    "Truck": "mb-truck", "@ToTruck": "mb-totruck",
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
        jmap.resolve_mailboxes.return_value = _STANDARD_MAILBOXES
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        carddav._groups = {
            "Feed": {"href": "/feed.vcf", "etag": '"etag"', "uid": "uid-feed"},
            "Imbox": {"href": "/imbox.vcf", "etag": '"etag"', "uid": "uid-imbox"},
        }
        carddav.get_group_members.return_value = []

        plan = plan_reset(mock_settings, jmap, carddav)

        # Annotated contact should be in one of the three lists
        all_contacts = plan.contacts_to_delete + plan.contacts_to_warn + plan.contacts_to_strip
        assert len(all_contacts) == 1
        assert all_contacts[0].uid == "uid-1"

    def test_excludes_screener_and_inbox(self, mock_settings) -> None:
        """Screener and Inbox mailboxes are excluded from label cleanup."""
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = _STANDARD_MAILBOXES
        jmap.query_emails.return_value = ["email-1"]

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = []
        carddav._groups = {}
        carddav.get_group_members.return_value = []

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
        jmap.resolve_mailboxes.return_value = _STANDARD_MAILBOXES
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        carddav._groups = {}
        carddav.get_group_members.return_value = []

        plan = plan_reset(mock_settings, jmap, carddav)

        all_contacts = plan.contacts_to_delete + plan.contacts_to_warn + plan.contacts_to_strip
        assert len(all_contacts) == 0

    def test_provenance_unmodified_goes_to_delete(self, mock_settings) -> None:
        """Unmodified provenance contact (in provenance group, no extra fields) goes to contacts_to_delete."""
        vcard = _make_provenance_vcard("uid-prov", "Acme Corp", "acme@example.com")
        contacts = [
            _make_contact("uid-prov", "Acme Corp", ["acme@example.com"],
                          f"{MAILROOM_HEADER}\nCreated by Mailroom\nTriaged to Feed on 2026-01-15",
                          vcard_data=vcard),
        ]

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = _STANDARD_MAILBOXES
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        carddav._groups = {
            "Feed": {"href": "/feed.vcf", "etag": '"etag"', "uid": "uid-feed"},
            "Imbox": {"href": "/imbox.vcf", "etag": '"etag"', "uid": "uid-imbox"},
        }
        carddav.get_group_members.side_effect = lambda g: (
            ["uid-prov"] if g == "Mailroom" else []
        )

        plan = plan_reset(mock_settings, jmap, carddav)

        assert len(plan.contacts_to_delete) == 1
        assert plan.contacts_to_delete[0].uid == "uid-prov"
        assert plan.contacts_to_delete[0].provenance == "created_unmodified"

    def test_provenance_modified_goes_to_warn(self, mock_settings) -> None:
        """Modified provenance contact (in provenance group, has extra fields) goes to contacts_to_warn."""
        vcard = _make_modified_vcard("uid-mod", "Acme Corp", "acme@example.com")
        contacts = [
            _make_contact("uid-mod", "Acme Corp", ["acme@example.com"],
                          f"{MAILROOM_HEADER}\nCreated by Mailroom\nTriaged to Feed on 2026-01-15",
                          vcard_data=vcard),
        ]

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = _STANDARD_MAILBOXES
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        carddav._groups = {
            "Feed": {"href": "/feed.vcf", "etag": '"etag"', "uid": "uid-feed"},
            "Imbox": {"href": "/imbox.vcf", "etag": '"etag"', "uid": "uid-imbox"},
        }
        carddav.get_group_members.side_effect = lambda g: (
            ["uid-mod"] if g == "Mailroom" else []
        )

        plan = plan_reset(mock_settings, jmap, carddav)

        assert len(plan.contacts_to_warn) == 1
        assert plan.contacts_to_warn[0].uid == "uid-mod"
        assert plan.contacts_to_warn[0].provenance == "created_modified"
        assert plan.contacts_to_warn[0].email == "acme@example.com"

    def test_adopted_contact_goes_to_strip(self, mock_settings) -> None:
        """Adopted contact (not in provenance group, has Mailroom note) goes to contacts_to_strip."""
        contacts = [
            _make_contact("uid-adopted", "Old Corp", ["old@example.com"],
                          f"Pre-existing note\n\n{MAILROOM_HEADER}\nAdopted by Mailroom\nRe-triaged to Imbox on 2026-03-01"),
        ]

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = _STANDARD_MAILBOXES
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        carddav._groups = {
            "Feed": {"href": "/feed.vcf", "etag": '"etag"', "uid": "uid-feed"},
            "Imbox": {"href": "/imbox.vcf", "etag": '"etag"', "uid": "uid-imbox"},
        }
        carddav.get_group_members.return_value = []

        plan = plan_reset(mock_settings, jmap, carddav)

        assert len(plan.contacts_to_strip) == 1
        assert plan.contacts_to_strip[0].uid == "uid-adopted"
        assert plan.contacts_to_strip[0].provenance == "adopted"

    def test_plan_includes_correct_email_counts(self, mock_settings) -> None:
        """Plan correctly maps mailbox names to email IDs."""
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = _STANDARD_MAILBOXES

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
        carddav.get_group_members.return_value = []

        plan = plan_reset(mock_settings, jmap, carddav)

        assert plan.email_labels.get("Feed") == ["e1", "e2", "e3"]
        assert plan.email_labels.get("@ToImbox") == ["e4"]


# --- TestApplyReset ---


class TestApplyReset:
    """Tests for apply_reset() execution with provenance-aware 7-step order."""

    def _make_plan(self) -> ResetPlan:
        """Build a provenance-aware reset plan for testing."""
        return ResetPlan(
            email_labels={
                "Feed": ["e1", "e2"],
                "@ToImbox": ["e3"],
            },
            group_members={
                "Feed": ["uid-del", "uid-warn"],
                "Imbox": ["uid-strip"],
            },
            contacts_to_delete=[
                ContactCleanup(
                    href="/uid-del.vcf",
                    etag='"etag-del"',
                    fn="Delete Corp",
                    uid="uid-del",
                    note=f"{MAILROOM_HEADER}\nCreated by Mailroom\nTriaged to Feed on 2026-01-15",
                    stripped_note="",
                    provenance="created_unmodified",
                    email="delete@example.com",
                    vcard_data=f"BEGIN:VCARD\nVERSION:3.0\nUID:uid-del\nFN:Delete Corp\nEMAIL:delete@example.com\nNOTE:{MAILROOM_HEADER}\\nTriaged to Feed on 2026-01-15\nEND:VCARD",
                ),
            ],
            contacts_to_warn=[
                ContactCleanup(
                    href="/uid-warn.vcf",
                    etag='"etag-warn"',
                    fn="Warn Corp",
                    uid="uid-warn",
                    note=f"{MAILROOM_HEADER}\nCreated by Mailroom\nTriaged to Feed on 2026-01-15",
                    stripped_note="",
                    provenance="created_modified",
                    email="warn@example.com",
                    vcard_data=f"BEGIN:VCARD\nVERSION:3.0\nUID:uid-warn\nFN:Warn Corp\nEMAIL:warn@example.com\nTEL:+123\nNOTE:{MAILROOM_HEADER}\\nTriaged to Feed on 2026-01-15\nEND:VCARD",
                ),
            ],
            contacts_to_strip=[
                ContactCleanup(
                    href="/uid-strip.vcf",
                    etag='"etag-strip"',
                    fn="Strip Corp",
                    uid="uid-strip",
                    note=f"Old note\n\n{MAILROOM_HEADER}\nAdopted by Mailroom\nRe-triaged to Imbox on 2026-03-01",
                    stripped_note="Old note",
                    provenance="adopted",
                    email="strip@example.com",
                    vcard_data=f"BEGIN:VCARD\nVERSION:3.0\nUID:uid-strip\nFN:Strip Corp\nEMAIL:strip@example.com\nNOTE:Old note\\n\\n{MAILROOM_HEADER}\\nAdopted by Mailroom\nEND:VCARD",
                ),
            ],
        )

    def test_step1_removes_managed_labels(self, mock_settings) -> None:
        """Step 1: Remove managed labels from emails."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'
        jmap.query_emails_by_sender.return_value = []

        result = apply_reset(plan, jmap, carddav, mock_settings)

        # batch_remove_labels called for Feed and @ToImbox
        remove_calls = jmap.batch_remove_labels.call_args_list
        assert len(remove_calls) >= 2  # at least managed labels + possible warning/error cleanup

    def test_step2_removes_warning_and_error_labels(self, mock_settings) -> None:
        """Step 2: Remove @MailroomWarning and @MailroomError from ALL emails."""
        plan = ResetPlan(
            email_labels={}, group_members={},
            contacts_to_delete=[], contacts_to_warn=[], contacts_to_strip=[],
        )
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        # Warning mailbox has 2 emails, error has 1
        def _query_emails(mailbox_id, **kwargs):
            if mailbox_id == "mb-warning":
                return ["ew1", "ew2"]
            if mailbox_id == "mb-error":
                return ["ee1"]
            return []
        jmap.query_emails.side_effect = _query_emails
        carddav = MagicMock()

        apply_reset(plan, jmap, carddav, mock_settings)

        # batch_remove_labels should be called for warning and error cleanup
        remove_calls = jmap.batch_remove_labels.call_args_list
        # Find calls that remove warning/error labels
        warning_calls = [c for c in remove_calls if "mb-warning" in str(c)]
        error_calls = [c for c in remove_calls if "mb-error" in str(c)]
        assert len(warning_calls) >= 1
        assert len(error_calls) >= 1

    def test_step3_removes_contacts_from_groups(self, mock_settings) -> None:
        """Step 3: Remove contacts from category groups."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        jmap.query_emails_by_sender.return_value = []
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        apply_reset(plan, jmap, carddav, mock_settings)

        # remove_from_group: Feed(uid-del, uid-warn) + Imbox(uid-strip) = 3 category calls
        # + 1 provenance group removal (step 5) = 4 total
        category_removals = [
            c for c in carddav.remove_from_group.call_args_list
            if c[0][0] != "Mailroom"
        ]
        assert len(category_removals) == 3

    def test_step4_applies_warning_to_modified_contacts(self, mock_settings) -> None:
        """Step 4: Apply @MailroomWarning to user-modified provenance contacts' emails."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        # Sender has 3 emails
        jmap.query_emails_by_sender.return_value = ["we1", "we2", "we3"]
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        apply_reset(plan, jmap, carddav, mock_settings)

        # query_emails_by_sender called for warn contact's email
        jmap.query_emails_by_sender.assert_called_with("warn@example.com")
        # batch_add_labels called with warning mailbox
        jmap.batch_add_labels.assert_called_once_with(
            ["we1", "we2", "we3"], ["mb-warning"]
        )

    def test_step5_removes_warned_from_provenance_group(self, mock_settings) -> None:
        """Step 5: Remove warned contacts from provenance group."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        jmap.query_emails_by_sender.return_value = []
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        apply_reset(plan, jmap, carddav, mock_settings)

        # remove_from_group should include provenance group removal for warned contact
        provenance_removals = [
            c for c in carddav.remove_from_group.call_args_list
            if c[0][0] == "Mailroom"  # group_name = provenance group
        ]
        assert len(provenance_removals) == 1
        assert provenance_removals[0][0][1] == "uid-warn"

    def test_step6_strips_notes_from_all_contacts(self, mock_settings) -> None:
        """Step 6: Strip Mailroom notes from ALL annotated contacts."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        jmap.query_emails_by_sender.return_value = []
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        apply_reset(plan, jmap, carddav, mock_settings)

        # update_contact_vcard called for all 3 contacts (delete + warn + strip)
        assert carddav.update_contact_vcard.call_count == 3

    def test_step7_deletes_unmodified_provenance_contacts(self, mock_settings) -> None:
        """Step 7: DELETE unmodified provenance contacts."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        jmap.query_emails_by_sender.return_value = []
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        apply_reset(plan, jmap, carddav, mock_settings)

        # delete_contact called for uid-del
        carddav.delete_contact.assert_called_once_with("/uid-del.vcf", '"etag-del"')

    def test_7step_operation_order(self, mock_settings) -> None:
        """Operations execute in exact 7-step order from CONTEXT.md."""
        plan = self._make_plan()
        call_order = []

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        jmap.batch_remove_labels.side_effect = lambda *a, **kw: call_order.append("step1_or_2_remove_labels")
        jmap.query_emails_by_sender.return_value = ["we1"]
        jmap.batch_add_labels.side_effect = lambda *a, **kw: call_order.append("step4_add_warning")

        carddav = MagicMock()
        carddav.remove_from_group.side_effect = lambda *a, **kw: call_order.append(
            "step5_provenance_remove" if a[0] == "Mailroom" else "step3_group_remove"
        )
        carddav.update_contact_vcard.side_effect = lambda *a, **kw: call_order.append("step6_strip_notes")
        carddav.delete_contact.side_effect = lambda *a, **kw: call_order.append("step7_delete")

        apply_reset(plan, jmap, carddav, mock_settings)

        # Verify ordering: step1/2 < step3 < step4 < step5 < step6 < step7
        def first_index(prefix):
            for i, x in enumerate(call_order):
                if x.startswith(prefix):
                    return i
            return -1

        def last_index(prefix):
            for i in range(len(call_order) - 1, -1, -1):
                if call_order[i].startswith(prefix):
                    return i
            return -1

        assert last_index("step1_or_2") < first_index("step3")
        assert last_index("step3") < first_index("step4")
        assert last_index("step4") < first_index("step5")
        assert last_index("step5") < first_index("step6")
        assert last_index("step6") < first_index("step7")

    def test_result_counts(self, mock_settings) -> None:
        """ResetResult has correct counts for all categories."""
        plan = self._make_plan()
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "Feed": "mb-feed", "@ToImbox": "mb-toimbox",
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        jmap.query_emails_by_sender.return_value = ["we1"]
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        result = apply_reset(plan, jmap, carddav, mock_settings)

        assert result.emails_unlabeled == 3  # e1, e2, e3
        assert result.groups_emptied == 2  # Feed, Imbox
        assert result.contacts_deleted == 1  # uid-del
        assert result.contacts_warned == 1  # uid-warn
        assert result.contacts_cleaned == 1  # uid-strip (adopted)
        assert result.errors == []

    def test_note_stripping_mailroom_only(self, mock_settings) -> None:
        """Note that is ONLY mailroom section gets cleared to empty."""
        plan = ResetPlan(
            email_labels={}, group_members={},
            contacts_to_delete=[], contacts_to_warn=[],
            contacts_to_strip=[
                ContactCleanup(
                    href="/uid-1.vcf",
                    etag='"etag-1"',
                    fn="Acme Corp",
                    uid="uid-1",
                    note=f"{MAILROOM_HEADER}\nTriaged to Feed on 2026-01-15",
                    stripped_note="",
                    provenance="adopted",
                    email="acme@example.com",
                    vcard_data=f"BEGIN:VCARD\nVERSION:3.0\nUID:uid-1\nFN:Acme Corp\nNOTE:{MAILROOM_HEADER}\\nTriaged to Feed on 2026-01-15\nEND:VCARD",
                ),
            ],
        )
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        result = apply_reset(plan, jmap, carddav, mock_settings)

        assert carddav.update_contact_vcard.call_count == 1
        call_args = carddav.update_contact_vcard.call_args
        vcard_bytes = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("vcard_bytes", b"")
        vcard_str = vcard_bytes.decode("utf-8") if isinstance(vcard_bytes, bytes) else str(vcard_bytes)
        assert MAILROOM_HEADER not in vcard_str

    def test_note_stripping_preserves_preexisting(self, mock_settings) -> None:
        """Note with pre-existing content preserves the pre-existing text."""
        plan = ResetPlan(
            email_labels={}, group_members={},
            contacts_to_delete=[], contacts_to_warn=[],
            contacts_to_strip=[
                ContactCleanup(
                    href="/uid-2.vcf",
                    etag='"etag-2"',
                    fn="Old Corp",
                    uid="uid-2",
                    note=f"Pre-existing note\n\n{MAILROOM_HEADER}\nRe-triaged to Imbox on 2026-03-01",
                    stripped_note="Pre-existing note",
                    provenance="adopted",
                    email="old@example.com",
                    vcard_data=f"BEGIN:VCARD\nVERSION:3.0\nUID:uid-2\nFN:Old Corp\nNOTE:Pre-existing note\\n\\n{MAILROOM_HEADER}\\nRe-triaged to Imbox on 2026-03-01\nEND:VCARD",
                ),
            ],
        )
        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = {
            "@MailroomWarning": "mb-warning", "@MailroomError": "mb-error",
        }
        jmap.query_emails.return_value = []
        carddav = MagicMock()
        carddav.update_contact_vcard.return_value = '"new-etag"'

        result = apply_reset(plan, jmap, carddav, mock_settings)

        call_args = carddav.update_contact_vcard.call_args
        vcard_bytes = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("vcard_bytes", b"")
        vcard_str = vcard_bytes.decode("utf-8") if isinstance(vcard_bytes, bytes) else str(vcard_bytes)
        assert "Pre-existing note" in vcard_str
        assert MAILROOM_HEADER not in vcard_str

    def test_second_reset_warned_contacts_invisible(self, mock_settings) -> None:
        """After first reset warns a contact, second reset does not see it."""
        # Simulate a contact that was warned: no provenance group, no Mailroom note
        contacts = [
            _make_contact("uid-warned", "Warned Corp", ["warned@example.com"],
                          ""),  # note was stripped in first reset
        ]

        jmap = MagicMock()
        jmap.resolve_mailboxes.return_value = _STANDARD_MAILBOXES
        jmap.query_emails.return_value = []

        carddav = MagicMock()
        carddav.list_all_contacts.return_value = contacts
        carddav._groups = {
            "Feed": {"href": "/feed.vcf", "etag": '"etag"', "uid": "uid-feed"},
        }
        carddav.get_group_members.return_value = []

        plan = plan_reset(mock_settings, jmap, carddav)

        all_contacts = plan.contacts_to_delete + plan.contacts_to_warn + plan.contacts_to_strip
        assert len(all_contacts) == 0


# --- TestResetReporting ---


class TestResetReporting:
    """Tests for print_reset_report() output formatting."""

    def test_dry_run_report_shows_sections(self, capsys) -> None:
        """Dry-run report shows DELETE, WARN, and strip sections."""
        plan = ResetPlan(
            email_labels={
                "Feed": ["e1", "e2"],
                "@ToImbox": ["e3"],
            },
            group_members={
                "Feed": ["uid-1", "uid-2"],
            },
            contacts_to_delete=[
                ContactCleanup(
                    href="/uid-del.vcf", etag='"etag"', fn="Delete Corp",
                    uid="uid-del", note="note", stripped_note="",
                    provenance="created_unmodified", email="del@example.com",
                    vcard_data="",
                ),
            ],
            contacts_to_warn=[
                ContactCleanup(
                    href="/uid-warn.vcf", etag='"etag"', fn="Warn Corp",
                    uid="uid-warn", note="note", stripped_note="",
                    provenance="created_modified", email="warn@example.com",
                    vcard_data="",
                ),
            ],
            contacts_to_strip=[
                ContactCleanup(
                    href="/uid-strip.vcf", etag='"etag"', fn="Strip Corp",
                    uid="uid-strip", note="note", stripped_note="pre",
                    provenance="adopted", email="strip@example.com",
                    vcard_data="",
                ),
            ],
        )

        print_reset_report(plan, apply=False)
        output = capsys.readouterr().out

        assert "Email Labels" in output
        assert "Feed" in output
        assert "DELETE" in output
        assert "Delete Corp" in output
        assert "WARN" in output
        assert "Warn Corp" in output
        assert "strip" in output.lower()
        assert "Strip Corp" in output

    def test_apply_report_shows_all_counts(self, capsys) -> None:
        """Apply report shows deleted, warned, and cleaned counts."""
        result = ResetResult(
            emails_unlabeled=5,
            groups_emptied=3,
            contacts_deleted=2,
            contacts_warned=1,
            contacts_cleaned=4,
            errors=[],
        )

        print_reset_report(result, apply=True)
        output = capsys.readouterr().out

        assert "5" in output
        assert "3" in output
        assert "2" in output  # deleted
        assert "1" in output  # warned
        assert "4" in output  # cleaned


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
            "NOTE:\u2014 Mailroom \u2014\\nCreated by Mailroom\r\n"
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
