"""TDD tests for ScreenerWorkflow poll cycle, conflict detection, error labeling, and per-sender processing."""

from unittest.mock import MagicMock, call

import pytest
import vobject

from mailroom.workflows.screener import ScreenerWorkflow


def _default_call_side_effect(method_calls):
    """Default jmap.call() handler: batched Email/query returns empty, Email/get returns empty."""
    first_method = method_calls[0][0]
    if first_method == "Email/query":
        return [
            ["Email/query", {"ids": [], "total": 0}, mc[2]]
            for mc in method_calls
        ]
    if first_method == "Email/get":
        ids = method_calls[0][1].get("ids", [])
        return [["Email/get", {"list": [
            {"id": eid, "mailboxIds": {}} for eid in ids
        ]}, "g0"]]
    if first_method == "Email/set":
        return [["Email/set", {"updated": {}}, method_calls[0][2]]]
    return []


@pytest.fixture
def jmap(mock_mailbox_ids):
    """Mock JMAPClient with sensible defaults."""
    client = MagicMock()
    client.account_id = "acc-001"

    # Default: no emails in any triage label (used by _process_sender sweep)
    client.query_emails.return_value = []
    client.get_email_senders.return_value = {}

    # Default: handles batched Email/query (empty), Email/get, Email/set
    client.call.side_effect = _default_call_side_effect

    return client


@pytest.fixture
def carddav():
    """Mock CardDAVClient."""
    return MagicMock()


@pytest.fixture
def workflow(jmap, carddav, mock_settings, mock_mailbox_ids):
    """Create a ScreenerWorkflow with mocked dependencies."""
    return ScreenerWorkflow(
        jmap=jmap,
        carddav=carddav,
        settings=mock_settings,
        mailbox_ids=mock_mailbox_ids,
    )


class TestPollNoEmails:
    """No triaged emails -> poll() returns 0, minimal client calls."""

    def test_returns_zero(self, workflow):
        result = workflow.poll()
        assert result == 0

    def test_queries_all_triage_labels(self, workflow, jmap):
        workflow.poll()
        # Batched: single jmap.call() with 7 Email/query method calls
        batch_call = jmap.call.call_args_list[0]
        method_calls = batch_call.args[0]
        assert len(method_calls) == 7
        queried_ids = {mc[1]["filter"]["inMailbox"] for mc in method_calls}
        assert "mb-toimbox" in queried_ids
        assert "mb-tofeed" in queried_ids
        assert "mb-topapertrl" in queried_ids
        assert "mb-tojail" in queried_ids
        assert "mb-toperson" in queried_ids
        assert "mb-tobillboard" in queried_ids
        assert "mb-totruck" in queried_ids

    def test_no_sender_lookup(self, workflow, jmap):
        workflow.poll()
        jmap.get_email_senders.assert_not_called()


class TestPollSingleSenderSingleLabel:
    """1 sender, 1 label, 1 email -> clean sender processed."""

    @pytest.fixture(autouse=True)
    def setup_one_email(self, jmap, mock_mailbox_ids):
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice Smith")}
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"]}, mock_mailbox_ids
        )

    def test_returns_zero_because_stub_raises(self, workflow):
        """_process_sender stub raises NotImplementedError, caught by poll -> returns 0."""
        result = workflow.poll()
        assert result == 0

    def test_error_label_not_applied(self, workflow, jmap):
        """No error label applied for non-conflicted sender."""
        workflow.poll()
        # The Email/set call for error labeling should NOT happen
        # Only call should be the Email/get for error filtering
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        assert len(email_set_calls) == 0


class TestPollConflictingSender:
    """1 sender, 2 different labels on 2 emails -> conflicted."""

    @pytest.fixture(autouse=True)
    def setup_conflicting(self, jmap, mock_mailbox_ids):
        def sender_side_effect(email_ids):
            return {eid: ("bob@example.com", "Bob Example") for eid in email_ids}

        jmap.get_email_senders.side_effect = sender_side_effect

        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"], "mb-tofeed": ["email-2"]}, mock_mailbox_ids
        )

    def test_returns_zero_processed(self, workflow):
        result = workflow.poll()
        assert result == 0

    def test_error_label_applied_to_both_emails(self, workflow, jmap):
        workflow.poll()
        # Check that Email/set was called to add error label
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1
        # Verify both email IDs got the error label
        patched_ids = set()
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid in mc[1].get("update", {}):
                        patched_ids.add(eid)
        assert "email-1" in patched_ids
        assert "email-2" in patched_ids


class TestPollTwoCleanSenders:
    """2 senders, each with 1 label -> both clean, both processed."""

    @pytest.fixture(autouse=True)
    def setup_two_senders(self, jmap, mock_mailbox_ids):
        jmap.get_email_senders.return_value = {
            "email-1": ("alice@example.com", "Alice"),
            "email-2": ("carol@example.com", "Carol"),
        }
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1", "email-2"]}, mock_mailbox_ids
        )

    def test_both_senders_attempted(self, workflow):
        """Both senders get _process_sender called (stub fails, both counted as failures)."""
        result = workflow.poll()
        # Both senders fail because _process_sender is a stub
        assert result == 0


class TestPollMixedCleanAndConflicted:
    """1 clean sender + 1 conflicted sender -> clean processed, conflicted gets error label."""

    @pytest.fixture(autouse=True)
    def setup_mixed(self, jmap, mock_mailbox_ids):
        def sender_side_effect(email_ids):
            mapping = {
                "email-1": ("alice@example.com", "Alice"),
                "email-2": ("bob@example.com", "Bob"),
                "email-3": ("bob@example.com", "Bob"),
            }
            return {eid: mapping[eid] for eid in email_ids if eid in mapping}

        jmap.get_email_senders.side_effect = sender_side_effect

        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1", "email-2"], "mb-tofeed": ["email-3"]},
            mock_mailbox_ids,
        )

    def test_clean_sender_attempted(self, workflow):
        """Alice (clean) gets _process_sender called (stub fails, returns 0)."""
        result = workflow.poll()
        assert result == 0

    def test_conflicted_sender_gets_error_label(self, workflow, jmap):
        """Bob (conflicted) gets @MailroomError but not _process_sender."""
        workflow.poll()
        # Bob's emails should get error label
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        patched_ids = set()
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid in mc[1].get("update", {}):
                        patched_ids.add(eid)
        assert "email-2" in patched_ids
        assert "email-3" in patched_ids
        # Alice's email should NOT get error label
        assert "email-1" not in patched_ids


class TestAlreadyErroredEmailFiltered:
    """Email already has @MailroomError -> filtered out, not re-processed."""

    @pytest.fixture(autouse=True)
    def setup_errored(self, jmap, mock_mailbox_ids):
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice")}

        def call_side_effect(method_calls):
            first_method = method_calls[0][0]
            if first_method == "Email/query":
                responses = []
                for mc in method_calls:
                    label_id = mc[1]["filter"]["inMailbox"]
                    call_id = mc[2]
                    if label_id == "mb-toimbox":
                        responses.append(["Email/query", {"ids": ["email-1"], "total": 1}, call_id])
                    else:
                        responses.append(["Email/query", {"ids": [], "total": 0}, call_id])
                return responses
            if first_method == "Email/get":
                # email-1 already has the error label
                return [["Email/get", {"list": [
                    {"id": "email-1", "mailboxIds": {"mb-toimbox": True, "mb-error": True}},
                ]}, "g0"]]
            return [["Email/set", {"updated": {}}, method_calls[0][2]]]

        jmap.call.side_effect = call_side_effect

    def test_returns_zero(self, workflow):
        result = workflow.poll()
        assert result == 0

    def test_no_processing(self, workflow, jmap):
        workflow.poll()
        # No Email/set calls (no error label application, no processing)
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        assert len(email_set_calls) == 0


class TestSenderMissingFromHeader:
    """Email without From header -> skipped with warning, others still processed."""

    @pytest.fixture(autouse=True)
    def setup_missing_sender(self, jmap, mock_mailbox_ids):
        # email-1 has no sender, email-2 has a sender
        jmap.get_email_senders.return_value = {"email-2": ("alice@example.com", "Alice")}
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1", "email-2"]}, mock_mailbox_ids
        )

    def test_sender_with_email_still_processed(self, workflow):
        """alice@example.com is still collected even though email-1 has no sender."""
        result = workflow.poll()
        # Stub _process_sender raises, so returns 0, but alice was attempted
        assert result == 0


class TestApplyErrorLabelTransientFailure:
    """_apply_error_label fails (transient) -> logged, poll continues."""

    @pytest.fixture(autouse=True)
    def setup_error_label_failure(self, jmap, mock_mailbox_ids):
        def sender_side_effect(email_ids):
            return {eid: ("bob@example.com", "Bob") for eid in email_ids}

        jmap.get_email_senders.side_effect = sender_side_effect

        def call_side_effect(method_calls):
            first_method = method_calls[0][0]
            if first_method == "Email/query":
                responses = []
                for mc in method_calls:
                    label_id = mc[1]["filter"]["inMailbox"]
                    call_id = mc[2]
                    if label_id == "mb-toimbox":
                        responses.append(["Email/query", {"ids": ["email-1"], "total": 1}, call_id])
                    elif label_id == "mb-tofeed":
                        responses.append(["Email/query", {"ids": ["email-2"], "total": 1}, call_id])
                    else:
                        responses.append(["Email/query", {"ids": [], "total": 0}, call_id])
                return responses
            if first_method == "Email/get":
                ids = method_calls[0][1].get("ids", [])
                return [["Email/get", {"list": [
                    {"id": eid, "mailboxIds": {"mb-toimbox": True}} for eid in ids
                ]}, "g0"]]
            # Email/set for error labeling -> transient failure
            raise ConnectionError("Network timeout")

        jmap.call.side_effect = call_side_effect

    def test_poll_does_not_crash(self, workflow):
        """Poll continues even when _apply_error_label fails."""
        result = workflow.poll()
        assert result == 0


class TestProcessSenderException:
    """_process_sender raises exception -> logged, triage labels left in place."""

    @pytest.fixture(autouse=True)
    def setup_process_failure(self, jmap, mock_mailbox_ids):
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice")}
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"]}, mock_mailbox_ids
        )

    def test_exception_caught_and_returns_zero(self, workflow):
        """_process_sender is a stub raising NotImplementedError, poll catches it."""
        result = workflow.poll()
        assert result == 0

    def test_triage_labels_not_removed(self, workflow, jmap):
        """Triage labels left in place when _process_sender fails."""
        workflow.poll()
        jmap.remove_label.assert_not_called()


class TestDetectConflicts:
    """Unit tests for _detect_conflicts method."""

    def test_single_label_is_clean(self, workflow):
        triaged = {"alice@example.com": [("email-1", "@ToImbox")]}
        clean, conflicted = workflow._detect_conflicts(triaged)
        assert "alice@example.com" in clean
        assert len(conflicted) == 0

    def test_multiple_labels_is_conflicted(self, workflow):
        triaged = {
            "bob@example.com": [
                ("email-1", "@ToImbox"),
                ("email-2", "@ToFeed"),
            ]
        }
        clean, conflicted = workflow._detect_conflicts(triaged)
        assert len(clean) == 0
        assert "bob@example.com" in conflicted

    def test_same_label_multiple_emails_is_clean(self, workflow):
        triaged = {
            "alice@example.com": [
                ("email-1", "@ToImbox"),
                ("email-2", "@ToImbox"),
            ]
        }
        clean, conflicted = workflow._detect_conflicts(triaged)
        assert "alice@example.com" in clean
        assert len(conflicted) == 0

    def test_mixed_senders(self, workflow):
        triaged = {
            "alice@example.com": [("email-1", "@ToImbox")],
            "bob@example.com": [
                ("email-2", "@ToImbox"),
                ("email-3", "@ToFeed"),
            ],
        }
        clean, conflicted = workflow._detect_conflicts(triaged)
        assert "alice@example.com" in clean
        assert "bob@example.com" in conflicted


class TestCollectTriagedFilterErrorLabel:
    """_collect_triaged filters out emails already marked with @MailroomError."""

    @pytest.fixture(autouse=True)
    def setup_mixed_errored(self, jmap, mock_mailbox_ids):
        jmap.get_email_senders.return_value = {
            "email-1": ("alice@example.com", "Alice"),
            "email-2": ("bob@example.com", "Bob"),
        }

        def call_side_effect(method_calls):
            first_method = method_calls[0][0]
            if first_method == "Email/query":
                responses = []
                for mc in method_calls:
                    label_id = mc[1]["filter"]["inMailbox"]
                    call_id = mc[2]
                    if label_id == "mb-toimbox":
                        responses.append(["Email/query", {"ids": ["email-1", "email-2"], "total": 2}, call_id])
                    else:
                        responses.append(["Email/query", {"ids": [], "total": 0}, call_id])
                return responses
            if first_method == "Email/get":
                # email-1 has error label, email-2 does not
                return [["Email/get", {"list": [
                    {"id": "email-1", "mailboxIds": {"mb-toimbox": True, "mb-error": True}},
                    {"id": "email-2", "mailboxIds": {"mb-toimbox": True}},
                ]}, "g0"]]
            return [["Email/set", {"updated": {}}, method_calls[0][2]]]

        jmap.call.side_effect = call_side_effect

    def test_only_non_errored_collected(self, workflow):
        triaged, sender_names = workflow._collect_triaged()
        # alice's email-1 should be filtered out (has error label)
        # bob's email-2 should remain
        assert "bob@example.com" in triaged
        assert "alice@example.com" not in triaged


# =============================================================================
# Plan 02: Per-sender triage processing tests
# =============================================================================


class TestGetDestinationMailboxIds:
    """_get_destination_mailbox_ids maps triage labels to correct mailbox IDs (additive chain)."""

    def test_imbox_maps_to_imbox_plus_inbox(self, workflow):
        """@ToImbox -> [mb-imbox, mb-inbox]: Imbox mailbox + Inbox (add_to_inbox=True)."""
        result = workflow._get_destination_mailbox_ids("@ToImbox")
        assert result == ["mb-imbox", "mb-inbox"]

    def test_feed_maps_to_feed(self, workflow):
        """@ToFeed -> [feed_id]: root, no parent, no add_to_inbox."""
        result = workflow._get_destination_mailbox_ids("@ToFeed")
        assert result == ["mb-feed"]

    def test_paper_trail_maps_to_paper_trail(self, workflow):
        """@ToPaperTrail -> [paper_trail_id]: root, no parent, no add_to_inbox."""
        result = workflow._get_destination_mailbox_ids("@ToPaperTrail")
        assert result == ["mb-papertrl"]

    def test_jail_maps_to_jail(self, workflow):
        """@ToJail -> [jail_id]: root, no parent, no add_to_inbox."""
        result = workflow._get_destination_mailbox_ids("@ToJail")
        assert result == ["mb-jail"]

    def test_person_maps_to_person_plus_imbox(self, workflow):
        """@ToPerson -> [mb-person, mb-imbox]: child + parent (additive chain)."""
        result = workflow._get_destination_mailbox_ids("@ToPerson")
        assert result == ["mb-person", "mb-imbox"]

    def test_billboard_maps_to_billboard_plus_paper_trail(self, workflow):
        """@ToBillboard -> [mb-billboard, mb-papertrl]: child + parent (additive chain)."""
        result = workflow._get_destination_mailbox_ids("@ToBillboard")
        assert result == ["mb-billboard", "mb-papertrl"]

    def test_truck_maps_to_truck_plus_paper_trail(self, workflow):
        """@ToTruck -> [mb-truck, mb-papertrl]: child + parent (additive chain)."""
        result = workflow._get_destination_mailbox_ids("@ToTruck")
        assert result == ["mb-truck", "mb-papertrl"]

    def test_person_does_not_include_inbox(self, workflow):
        """@ToPerson does NOT include Inbox -- add_to_inbox does NOT propagate from Imbox."""
        result = workflow._get_destination_mailbox_ids("@ToPerson")
        assert "mb-inbox" not in result


class TestProcessSenderNewContact:
    """New sender triaged to @ToImbox: full pipeline with contact creation."""

    @pytest.fixture(autouse=True)
    def setup_new_sender(self, jmap, carddav):
        # CardDAV: no existing contact, upsert creates one
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "new-uid-123",
            "group": "Imbox",
            "name_mismatch": False,
        }
        # CardDAV: search returns empty (new sender)
        carddav.search_by_email.return_value = []

        # JMAP: reconcile finds 3 emails from this sender (all in Screener)
        jmap.query_emails_by_sender.return_value = ["email-1", "email-2", "email-3"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
            "email-2": {"mb-screener"},
            "email-3": {"mb-screener"},
        }

    def test_upsert_contact_called(self, workflow, carddav):
        """upsert_contact called with sender, display name from sender_names, group name."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice Smith"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice Smith", "Imbox", contact_type="company",
            provenance_group="Mailroom",
        )

    def test_sweep_queries_all_mailboxes(self, workflow, jmap):
        """Sweep queries all mailboxes for sender emails (not just Screener).

        query_emails_by_sender is called twice: once for warning cleanup, once for reconciliation.
        """
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        assert jmap.query_emails_by_sender.call_count == 2
        jmap.query_emails_by_sender.assert_any_call("alice@example.com")

    def test_reconcile_applies_imbox_plus_inbox(self, workflow, jmap):
        """Reconciliation adds Imbox + Inbox labels (add_to_inbox=True), removes Screener."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    update = mc[1].get("update", {})
                    if "email-1" in update:
                        patch = update["email-1"]
                        assert patch.get("mailboxIds/mb-imbox") is True
                        assert patch.get("mailboxIds/mb-inbox") is True
                        assert patch.get("mailboxIds/mb-screener") is None

    def test_triage_label_removed_last(self, workflow, jmap):
        """remove_label called for triage label on triggering emails only."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.remove_label.assert_called_once_with("email-1", "mb-toimbox")

    def test_returns_normally(self, workflow):
        """_process_sender does not raise on success."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )


class TestProcessSenderExistingContact:
    """Existing sender with @ToFeed: upsert returns 'existing', sweep moves to Feed."""

    @pytest.fixture(autouse=True)
    def setup_existing_sender(self, jmap, carddav):
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "existing-uid-456",
            "group": "Feed",
            "name_mismatch": False,
        }
        carddav.search_by_email.return_value = []

        # Reconcile finds 2 emails from sender (both in Screener)
        jmap.query_emails_by_sender.return_value = ["email-5", "email-6"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-5": {"mb-screener"},
            "email-6": {"mb-screener"},
        }

    def test_reconcile_to_feed(self, workflow, jmap):
        """Reconciliation adds Feed label, removes Screener for @ToFeed destination."""
        workflow._process_sender(
            "bob@example.com", [("email-5", "@ToFeed")]
        )
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    update = mc[1].get("update", {})
                    if "email-5" in update:
                        patch = update["email-5"]
                        assert patch.get("mailboxIds/mb-feed") is True
                        assert patch.get("mailboxIds/mb-screener") is None

    def test_triage_label_removed(self, workflow, jmap):
        """Triage label removed from triggering email after sweep."""
        workflow._process_sender(
            "bob@example.com", [("email-5", "@ToFeed")]
        )
        jmap.remove_label.assert_called_once_with("email-5", "mb-tofeed")


class TestProcessSenderPaperTrail:
    """Sender triaged to @ToPaperTrail: emails go to Paper Trail mailbox."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "pt-uid",
            "group": "Paper Trail",
            "name_mismatch": False,
        }
        carddav.search_by_email.return_value = []

        jmap.query_emails_by_sender.return_value = ["email-10"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-10": {"mb-screener"},
        }

    def test_reconcile_to_paper_trail(self, workflow, jmap):
        workflow._process_sender(
            "carol@example.com", [("email-10", "@ToPaperTrail")]
        )
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    update = mc[1].get("update", {})
                    if "email-10" in update:
                        patch = update["email-10"]
                        assert patch.get("mailboxIds/mb-papertrl") is True
                        assert patch.get("mailboxIds/mb-screener") is None


class TestProcessSenderJail:
    """Sender triaged to @ToJail: emails go to Jail mailbox."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "jail-uid",
            "group": "Jail",
            "name_mismatch": False,
        }
        carddav.search_by_email.return_value = []

        jmap.query_emails_by_sender.return_value = ["email-20"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-20": {"mb-screener"},
        }

    def test_reconcile_to_jail(self, workflow, jmap):
        workflow._process_sender(
            "spam@example.com", [("email-20", "@ToJail")]
        )
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    update = mc[1].get("update", {})
                    if "email-20" in update:
                        patch = update["email-20"]
                        assert patch.get("mailboxIds/mb-jail") is True
                        assert patch.get("mailboxIds/mb-screener") is None


class TestProcessSenderMultipleTriggering:
    """Sender with 5 triggering emails and 5 more in Screener: all reconciled, only triggering get remove_label."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "multi-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }
        carddav.search_by_email.return_value = []

        # Reconcile finds all 10 emails from sender (all in Screener)
        jmap.query_emails_by_sender.return_value = [
            f"email-{i}" for i in range(1, 11)
        ]
        jmap.get_email_mailbox_ids.return_value = {
            f"email-{i}": {"mb-screener"} for i in range(1, 11)
        }

    def test_all_reconciled(self, workflow, jmap):
        """All 10 emails from sender are reconciled with new labels."""
        triggering = [(f"email-{i}", "@ToImbox") for i in range(1, 6)]
        workflow._process_sender("alice@example.com", triggering)
        jmap.query_emails_by_sender.assert_any_call("alice@example.com")
        # Verify Email/set was called for reconciliation
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1
        # Check that all 10 emails got patches
        patched_ids = set()
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    patched_ids.update(mc[1].get("update", {}).keys())
        assert patched_ids == {f"email-{i}" for i in range(1, 11)}

    def test_only_triggering_get_remove_label(self, workflow, jmap):
        """Only the 5 triggering emails get triage label removed."""
        triggering = [(f"email-{i}", "@ToImbox") for i in range(1, 6)]
        workflow._process_sender("alice@example.com", triggering)
        assert jmap.remove_label.call_count == 5
        removed_ids = [c.args[0] for c in jmap.remove_label.call_args_list]
        assert removed_ids == [f"email-{i}" for i in range(1, 6)]


class TestProcessSenderStepOrder:
    """Verify strict step ordering for initial triage: detect retriage -> upsert -> reconcile -> remove label."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "order-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_upsert_before_reconcile(self, workflow, jmap, carddav):
        """upsert_contact is called after warning cleanup but before reconciliation."""
        call_order = []
        carddav.upsert_contact.side_effect = lambda *a, **kw: (
            call_order.append("upsert"),
            {"action": "created", "uid": "order-uid", "group": "Imbox", "name_mismatch": False},
        )[1]

        orig_query = jmap.query_emails_by_sender.return_value
        query_call_count = [0]

        def tracking_query(sender):
            query_call_count[0] += 1
            if query_call_count[0] == 1:
                call_order.append("warning_cleanup_query")
            else:
                call_order.append("reconcile_query")
            return orig_query

        jmap.query_emails_by_sender.side_effect = tracking_query
        jmap.remove_label.side_effect = lambda *a, **kw: call_order.append(
            "remove_label"
        )

        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )

        assert call_order == ["warning_cleanup_query", "upsert", "reconcile_query", "remove_label"]

    def test_remove_label_is_last(self, workflow, jmap, carddav):
        """remove_label is the very last operation."""
        call_order = []
        carddav.upsert_contact.side_effect = lambda *a, **kw: (
            call_order.append("upsert"),
            {"action": "created", "uid": "order-uid", "group": "Imbox", "name_mismatch": False},
        )[1]
        jmap.remove_label.side_effect = lambda *a, **kw: call_order.append(
            "remove_label"
        )

        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        assert call_order[-1] == "remove_label"


class TestRetriageDifferentGroup:
    """Sender already in 'Feed' group, triaged to @ToImbox: re-triage moves to new group."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        # search_by_email finds an existing contact
        carddav.search_by_email.return_value = [
            {
                "href": "/contact-456.vcf",
                "etag": '"etag-456"',
                "vcard_data": _make_vcard("bob@example.com", "contact-uid-456"),
            }
        ]
        # check_membership returns "Feed" (the group the contact is already in)
        carddav.check_membership.return_value = "Feed"
        # upsert_contact succeeds
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "contact-uid-456",
            "group": "Imbox",
            "name_mismatch": False,
        }
        # query_emails_by_sender returns some emails for reconciliation
        jmap.query_emails_by_sender.return_value = ["email-10", "email-11"]
        # get_email_mailbox_ids for checking Screener presence
        jmap.get_email_mailbox_ids.return_value = {
            "email-10": {"mb-feed"},
            "email-11": {"mb-feed"},
        }

    def test_no_error_label_applied(self, workflow, jmap):
        """@MailroomError is NOT applied for re-triage (re-triage replaces error behavior)."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox"), ("email-2", "@ToImbox")],
        )
        # No Email/set calls for error labeling
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" and "mb-error" in str(mc[1].get("update", {}))
                   for mc in c.args[0])
        ]
        assert len(email_set_calls) == 0

    def test_upsert_called(self, workflow, carddav):
        """upsert_contact IS called during re-triage."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox")],
        )
        carddav.upsert_contact.assert_called_once()

    def test_group_reassignment_happens(self, workflow, carddav):
        """add_to_group and remove_from_group called for group reassignment."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox")],
        )
        # Feed->Imbox: add to Imbox, remove from Feed
        carddav.add_to_group.assert_called()
        carddav.remove_from_group.assert_called()

    def test_email_reconciliation_happens(self, workflow, jmap):
        """query_emails_by_sender and Email/set called for email reconciliation."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox")],
        )
        jmap.query_emails_by_sender.assert_any_call("bob@example.com")

    def test_triage_label_removed(self, workflow, jmap):
        """Triage label IS removed after re-triage (not left for manual resolution)."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox")],
        )
        jmap.remove_label.assert_called_once_with("email-1", "mb-toimbox")


class TestRetriageSameGroup:
    """Sender already in 'Imbox' group, triaged to @ToImbox again: re-triage with self-healing."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = [
            {
                "href": "/contact-789.vcf",
                "etag": '"etag-789"',
                "vcard_data": _make_vcard("alice@example.com", "contact-uid-789"),
            }
        ]
        # check_membership returns "Imbox" (same group as target)
        carddav.check_membership.return_value = "Imbox"
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "contact-uid-789",
            "group": "Imbox",
            "name_mismatch": False,
        }
        # query_emails_by_sender for reconciliation
        jmap.query_emails_by_sender.return_value = ["email-1", "email-2"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-imbox"},
            "email-2": {"mb-imbox"},
        }

    def test_upsert_called(self, workflow, carddav):
        """upsert_contact called during same-group re-triage."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        carddav.upsert_contact.assert_called_once()

    def test_no_group_add_or_remove(self, workflow, carddav):
        """Same-group re-triage: chain diff is empty, NO add/remove calls."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        carddav.add_to_group.assert_not_called()
        carddav.remove_from_group.assert_not_called()

    def test_email_reconciliation_called(self, workflow, jmap):
        """Email reconciliation runs for self-healing even in same-group re-triage."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.query_emails_by_sender.assert_any_call("alice@example.com")

    def test_triage_label_removed(self, workflow, jmap):
        """Triage label removed normally."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.remove_label.assert_called_once()


class TestRetriageNewSender:
    """New sender (not in contacts): _detect_retriage returns (None, None), initial triage flow."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "brand-new-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_no_membership_check(self, workflow, carddav):
        """check_membership NOT called when no contact found (new sender)."""
        workflow._process_sender(
            "newbie@example.com", [("email-1", "@ToImbox")]
        )
        carddav.check_membership.assert_not_called()

    def test_upsert_called(self, workflow, carddav):
        """New sender proceeds to upsert."""
        workflow._process_sender(
            "newbie@example.com", [("email-1", "@ToImbox")]
        )
        carddav.upsert_contact.assert_called_once()

    def test_uses_full_reconciliation(self, workflow, jmap):
        """New sender also uses full email reconciliation (same as retriage)."""
        workflow._process_sender(
            "newbie@example.com", [("email-1", "@ToImbox")]
        )
        jmap.query_emails_by_sender.assert_any_call("newbie@example.com")


class TestCardDAVFailureDuringUpsert:
    """CardDAV failure during upsert: exception propagates, triage label NOT removed."""

    @pytest.fixture(autouse=True)
    def setup(self, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.side_effect = ConnectionError("CardDAV down")

    def test_exception_propagates(self, workflow):
        """Exception from upsert_contact propagates up."""
        with pytest.raises(ConnectionError, match="CardDAV down"):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )

    def test_triage_label_not_removed(self, workflow, jmap):
        """Triage label NOT removed when CardDAV fails."""
        with pytest.raises(ConnectionError):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )
        jmap.remove_label.assert_not_called()

    def test_sweep_not_called(self, workflow, jmap):
        """No sweep when CardDAV fails during upsert."""
        with pytest.raises(ConnectionError):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )
        jmap.batch_move_emails.assert_not_called()


class TestJMAPFailureDuringReconciliation:
    """JMAP failure during email reconciliation: exception propagates, triage label NOT removed."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "sweep-fail-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

        # Reconciliation uses jmap.call for Email/set -- make it fail
        def call_side_effect(method_calls):
            first_method = method_calls[0][0]
            if first_method == "Email/set":
                raise RuntimeError("JMAP reconciliation failed")
            return _default_call_side_effect(method_calls)

        jmap.call.side_effect = call_side_effect

    def test_exception_propagates(self, workflow):
        with pytest.raises(RuntimeError, match="JMAP reconciliation failed"):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )

    def test_triage_label_not_removed(self, workflow, jmap):
        with pytest.raises(RuntimeError):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )
        jmap.remove_label.assert_not_called()


class TestJMAPFailureDuringRemoveLabel:
    """JMAP failure during remove_label: exception propagates (partially processed, retry safe per TRIAGE-05)."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "remove-fail-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }
        jmap.remove_label.side_effect = RuntimeError("Failed to remove label")

    def test_exception_propagates(self, workflow):
        with pytest.raises(RuntimeError, match="Failed to remove label"):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )

    def test_contact_was_upserted(self, workflow, carddav):
        """Contact upsert succeeded before remove_label failed."""
        with pytest.raises(RuntimeError):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )
        carddav.upsert_contact.assert_called_once()

    def test_emails_were_reconciled(self, workflow, jmap):
        """Email reconciliation succeeded before remove_label failed."""
        with pytest.raises(RuntimeError):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )
        jmap.query_emails_by_sender.assert_called()


class TestProcessSenderEmptyReconciliation:
    """Reconciliation finds no emails from sender: no Email/set patches applied."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "empty-sweep-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        # No emails found from sender across all mailboxes
        jmap.query_emails_by_sender.return_value = []

    def test_no_email_set_called(self, workflow, jmap):
        """No Email/set patches when reconciliation finds nothing."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        # No Email/set calls should be made for reconciliation
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        assert len(email_set_calls) == 0

    def test_triage_label_still_removed(self, workflow, jmap):
        """Triage label removal still happens even if reconciliation is empty."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.remove_label.assert_called_once_with("email-1", "mb-toimbox")


class TestProcessSenderIntegrationWithPoll:
    """End-to-end: poll() calls _process_sender which now works (not a stub)."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav, mock_mailbox_ids):
        # Discovery: batched Email/query returns email-1 in @ToImbox
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"]}, mock_mailbox_ids
        )
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice Smith")}

        # Reconciliation: finds email-1 from sender
        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "poll-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

    def test_poll_returns_one_processed(self, workflow):
        """poll() now returns 1 (sender processed successfully)."""
        result = workflow.poll()
        assert result == 1

    def test_poll_calls_upsert(self, workflow, carddav):
        workflow.poll()
        carddav.upsert_contact.assert_called_once()

    def test_poll_calls_reconciliation(self, workflow, jmap):
        workflow.poll()
        jmap.query_emails_by_sender.assert_any_call("alice@example.com")

    def test_poll_passes_display_name_to_upsert(self, workflow, carddav):
        """poll() propagates sender display name from JMAP to upsert_contact."""
        workflow.poll()
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice Smith", "Imbox", contact_type="company",
            provenance_group="Mailroom",
        )


class TestDisplayNamePropagation:
    """Display name flows from JMAP From header through _collect_triaged to upsert_contact."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "dn-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_display_name_passed_to_upsert(self, workflow, carddav):
        """_process_sender passes the sender's display name from sender_names to upsert_contact."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice Smith"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice Smith", "Imbox", contact_type="company",
            provenance_group="Mailroom",
        )

    def test_display_name_none_when_missing(self, workflow, carddav):
        """None is passed when no name available in sender_names."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": None},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", None, "Imbox", contact_type="company",
            provenance_group="Mailroom",
        )

    def test_display_name_none_when_sender_not_in_names(self, workflow, carddav):
        """None passed when sender_names is empty dict (backward compatible)."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", None, "Imbox", contact_type="company",
            provenance_group="Mailroom",
        )


class TestCollectTriagedReturnsSenderNames:
    """_collect_triaged returns sender_names dict alongside triaged emails."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, mock_mailbox_ids):
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice Smith")}
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"]}, mock_mailbox_ids
        )

    def test_returns_tuple(self, workflow):
        """_collect_triaged returns a tuple of (triaged, sender_names)."""
        result = workflow._collect_triaged()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_sender_names_populated(self, workflow):
        """sender_names contains the display name for each sender."""
        triaged, sender_names = workflow._collect_triaged()
        assert sender_names["alice@example.com"] == "Alice Smith"

    def test_triaged_dict_still_correct(self, workflow):
        """Triaged dict still maps sender email to list of (email_id, label) tuples."""
        triaged, sender_names = workflow._collect_triaged()
        assert "alice@example.com" in triaged
        assert triaged["alice@example.com"] == [("email-1", "@ToImbox")]

    def test_empty_returns_empty_tuple(self, workflow, jmap, mock_mailbox_ids):
        """When no emails found, returns ({}, {})."""
        jmap.call.side_effect = _make_batched_call_side_effect({}, mock_mailbox_ids)
        result = workflow._collect_triaged()
        assert result == ({}, {})


# =============================================================================
# Plan 03.1-02: Contact type passthrough, @ToPerson routing, @MailroomWarning
# =============================================================================


class TestContactTypePassthroughToImbox:
    """_process_sender with @ToImbox passes contact_type='company' to upsert_contact."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "ct-imbox-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_contact_type_company(self, workflow, carddav):
        """upsert_contact called with contact_type='company' for @ToImbox."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice", "Imbox", contact_type="company",
            provenance_group="Mailroom",
        )


class TestContactTypePassthroughToPerson:
    """_process_sender with @ToPerson passes contact_type='person' to upsert_contact."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "ct-person-uid",
            "group": "Person",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_contact_type_person(self, workflow, carddav):
        """upsert_contact called with contact_type='person' for @ToPerson."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToPerson")],
            {"alice@example.com": "Alice Person"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice Person", "Person", contact_type="person",
            provenance_group="Mailroom",
        )


class TestContactTypePassthroughToFeed:
    """_process_sender with @ToFeed passes contact_type='company' to upsert_contact."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "ct-feed-uid",
            "group": "Feed",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_contact_type_company(self, workflow, carddav):
        """upsert_contact called with contact_type='company' for @ToFeed."""
        workflow._process_sender(
            "feed@example.com",
            [("email-1", "@ToFeed")],
            {"feed@example.com": "Feed Sender"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "feed@example.com", "Feed Sender", "Feed", contact_type="company",
            provenance_group="Mailroom",
        )


class TestContactTypePassthroughToJail:
    """_process_sender with @ToJail passes contact_type='company' to upsert_contact."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "ct-jail-uid",
            "group": "Jail",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_contact_type_company(self, workflow, carddav):
        """upsert_contact called with contact_type='company' for @ToJail."""
        workflow._process_sender(
            "spam@example.com",
            [("email-1", "@ToJail")],
            {"spam@example.com": "Spammer"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "spam@example.com", "Spammer", "Jail", contact_type="company",
            provenance_group="Mailroom",
        )


class TestToPersonRoutingPoll:
    """poll() with @ToPerson label processes sender, reconciles labels, removes triage label."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav, mock_mailbox_ids):
        # Discovery: batched Email/query returns email-1 in @ToPerson
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toperson": ["email-1"]}, mock_mailbox_ids
        )
        jmap.get_email_senders.return_value = {
            "email-1": ("person@example.com", "Jane Doe")
        }

        # Reconciliation: finds email-1 from sender in Screener
        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "person-poll-uid",
            "group": "Person",
            "name_mismatch": False,
        }

    def test_poll_returns_one_processed(self, workflow):
        """poll() returns 1 for @ToPerson sender."""
        result = workflow.poll()
        assert result == 1

    def test_upsert_called_with_person_type(self, workflow, carddav):
        """upsert_contact called with contact_type='person' for @ToPerson."""
        workflow.poll()
        carddav.upsert_contact.assert_called_once_with(
            "person@example.com", "Jane Doe", "Person", contact_type="person",
            provenance_group="Mailroom",
        )

    def test_reconcile_to_person_plus_imbox(self, workflow, jmap):
        """Reconciliation applies Person + Imbox labels (additive chain)."""
        workflow.poll()
        jmap.query_emails_by_sender.assert_any_call("person@example.com")

    def test_triage_label_removed(self, workflow, jmap):
        """@ToPerson label removed from triggering email."""
        workflow.poll()
        jmap.remove_label.assert_called_once_with("email-1", "mb-toperson")


class TestToPersonRoutesPersonGroup:
    """@ToPerson routes to Person contact group (v1.2: independent child)."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "person-group-uid",
            "group": "Person",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_routes_to_person_group(self, workflow, carddav):
        """@ToPerson upsert_contact uses 'Person' group (v1.2: independent)."""
        workflow._process_sender(
            "person@example.com",
            [("email-1", "@ToPerson")],
            {"person@example.com": "Jane Doe"},
        )
        # The group argument (3rd positional) is "Person"
        args, kwargs = carddav.upsert_contact.call_args
        assert args[2] == "Person"


class TestToPersonConflictWithToImbox:
    """@ToPerson + @ToImbox on same sender produces conflict."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, mock_mailbox_ids):
        def sender_side_effect(email_ids):
            return {eid: ("both@example.com", "Both Labels") for eid in email_ids}

        jmap.get_email_senders.side_effect = sender_side_effect

        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toperson": ["email-1"], "mb-toimbox": ["email-2"]}, mock_mailbox_ids
        )

    def test_conflict_detected(self, workflow):
        """@ToPerson + @ToImbox = conflict, returns 0 processed."""
        result = workflow.poll()
        assert result == 0

    def test_error_label_applied(self, workflow, jmap):
        """Both emails get @MailroomError."""
        workflow.poll()
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        patched_ids = set()
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid in mc[1].get("update", {}):
                        patched_ids.add(eid)
        assert "email-1" in patched_ids
        assert "email-2" in patched_ids


class TestToPersonConflictWithToFeed:
    """@ToPerson + @ToFeed on same sender produces conflict."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, mock_mailbox_ids):
        def sender_side_effect(email_ids):
            return {eid: ("both@example.com", "Both Labels") for eid in email_ids}

        jmap.get_email_senders.side_effect = sender_side_effect

        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toperson": ["email-1"], "mb-tofeed": ["email-2"]}, mock_mailbox_ids
        )

    def test_conflict_detected(self, workflow):
        """@ToPerson + @ToFeed = conflict, returns 0 processed."""
        result = workflow.poll()
        assert result == 0

    def test_error_label_applied_to_both(self, workflow, jmap):
        """Both emails get @MailroomError."""
        workflow.poll()
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        patched_ids = set()
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid in mc[1].get("update", {}):
                        patched_ids.add(eid)
        assert "email-1" in patched_ids
        assert "email-2" in patched_ids


class TestWarningLabelOnNameMismatchEnabled:
    """upsert returns name_mismatch=True, warnings_enabled=True: _apply_warning_label called."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "mismatch-uid",
            "group": "Imbox",
            "name_mismatch": True,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_warning_label_applied(self, workflow, jmap):
        """_apply_warning_label is called when name_mismatch=True and warnings_enabled=True."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToPerson")],
            {"alice@example.com": "Alice New Name"},
        )
        # Warning label should be applied via JMAP Email/set with warning mailbox ID
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1
        # Check that the warning mailbox ID is used
        found_warning = False
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid, update in mc[1].get("update", {}).items():
                        if "mailboxIds/mb-warning" in update:
                            found_warning = True
        assert found_warning, "Warning label (mb-warning) not applied to email"


class TestWarningLabelOnNameMismatchDisabled:
    """upsert returns name_mismatch=True, warnings_enabled=False: NO warning label."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav, mock_settings):
        mock_settings.mailroom.warnings_enabled = False

        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "mismatch-uid-disabled",
            "group": "Imbox",
            "name_mismatch": True,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_no_warning_label(self, workflow, jmap):
        """No warning label applied when warnings_enabled=False."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToPerson")],
            {"alice@example.com": "Alice New Name"},
        )
        # Only calls should NOT include any Email/set with warning mailbox
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid, update in mc[1].get("update", {}).items():
                        assert "mailboxIds/mb-warning" not in update


class TestNoWarningWhenNoNameMismatch:
    """upsert returns name_mismatch=False: NO warning regardless of warnings_enabled."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "nomismatch-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_no_warning_label(self, workflow, jmap):
        """No warning label applied when name_mismatch=False."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToPerson")],
            {"alice@example.com": "Alice"},
        )
        # Email/set calls should be reconciliation only, not warning.
        # Check none of the patches contain the warning mailbox ID.
        for c in jmap.call.call_args_list:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid, update in mc[1].get("update", {}).items():
                        assert "mailboxIds/mb-warning" not in update


class TestWarningLabelFailureNonBlocking:
    """_apply_warning_label failure is caught -- processing continues, only logs."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "warn-fail-uid",
            "group": "Imbox",
            "name_mismatch": True,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

        # Track Email/set calls to distinguish warning from reconciliation.
        # Step 3a (warning) runs BEFORE step 4 (reconciliation) in _process_sender.
        self._email_set_count = 0

        def call_side_effect(method_calls):
            method = method_calls[0][0]
            if method == "Email/set":
                self._email_set_count += 1
                if self._email_set_count == 1:
                    # First Email/set is warning label -- fail
                    raise ConnectionError("JMAP warning label failed")
                else:
                    # Second Email/set is reconciliation -- let it succeed
                    return [["Email/set", {"updated": {}}, method_calls[0][2]]]
            return _default_call_side_effect(method_calls)

        jmap.call.side_effect = call_side_effect

    def test_processing_continues_after_warning_failure(self, workflow, jmap):
        """Reconciliation and label removal still happen even when warning label fails."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToPerson")],
            {"alice@example.com": "Alice New"},
        )
        # Triage label should still be removed (processing continued)
        jmap.remove_label.assert_called_once_with("email-1", "mb-toperson")


class TestWarningAppliedToTriggeringEmailsOnly:
    """@MailroomWarning is applied to the triggering email(s), not all emails."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "warn-target-uid",
            "group": "Imbox",
            "name_mismatch": True,
        }

        jmap.query_emails_by_sender.return_value = [
            f"email-{i}" for i in range(1, 6)
        ]
        jmap.get_email_mailbox_ids.return_value = {
            f"email-{i}": {"mb-screener"} for i in range(1, 6)
        }

    def test_warning_applied_to_triggering_only(self, workflow, jmap):
        """Warning label applied only to triggering emails (email-1, email-2), not swept ones."""
        triggering = [("email-1", "@ToPerson"), ("email-2", "@ToPerson")]
        workflow._process_sender(
            "alice@example.com",
            triggering,
            {"alice@example.com": "Alice Mismatch"},
        )
        # Collect all emails that received warning label
        warned_ids = set()
        for c in jmap.call.call_args_list:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid, update in mc[1].get("update", {}).items():
                        if "mailboxIds/mb-warning" in update:
                            warned_ids.add(eid)
        # Only triggering emails should get warning
        assert warned_ids == {"email-1", "email-2"}


class TestToPersonDestinationMailbox:
    """@ToPerson maps to Person + Imbox mailboxes (additive chain)."""

    def test_toperson_maps_to_person_plus_imbox(self, workflow):
        """@ToPerson -> [mb-person, mb-imbox]: child + parent (additive chain)."""
        result = workflow._get_destination_mailbox_ids("@ToPerson")
        assert result == ["mb-person", "mb-imbox"]


# =============================================================================
# Plan 11-02: Additive parent chain tests
# =============================================================================


class TestAdditiveContactGroups:
    """_process_sender adds contact to all ancestor groups via add_to_group."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_person_adds_to_imbox_group(self, workflow, carddav):
        """Person triage: upsert_contact with 'Person', then add_to_group with 'Imbox'."""
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "person-uid-1",
            "group": "Person",
            "name_mismatch": False,
        }
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToPerson")],
            {"alice@example.com": "Alice"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice", "Person", contact_type="person",
            provenance_group="Mailroom",
        )
        carddav.add_to_group.assert_called_once_with("Imbox", "person-uid-1")

    def test_billboard_adds_to_paper_trail_group(self, workflow, carddav):
        """Billboard triage: upsert with 'Billboard', then add_to_group with 'Paper Trail'."""
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "bb-uid-1",
            "group": "Billboard",
            "name_mismatch": False,
        }
        workflow._process_sender(
            "promo@example.com",
            [("email-1", "@ToBillboard")],
            {"promo@example.com": "Promo Sender"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "promo@example.com", "Promo Sender", "Billboard", contact_type="company",
            provenance_group="Mailroom",
        )
        carddav.add_to_group.assert_called_once_with("Paper Trail", "bb-uid-1")

    def test_truck_adds_to_paper_trail_group(self, workflow, carddav):
        """Truck triage: upsert with 'Truck', then add_to_group with 'Paper Trail'."""
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "truck-uid-1",
            "group": "Truck",
            "name_mismatch": False,
        }
        workflow._process_sender(
            "shipping@example.com",
            [("email-1", "@ToTruck")],
            {"shipping@example.com": "Shipping Co"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "shipping@example.com", "Shipping Co", "Truck", contact_type="company",
            provenance_group="Mailroom",
        )
        carddav.add_to_group.assert_called_once_with("Paper Trail", "truck-uid-1")

    def test_root_feed_no_add_to_group(self, workflow, carddav):
        """Feed (root) triage: upsert called, NO add_to_group (no ancestors)."""
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "feed-uid-1",
            "group": "Feed",
            "name_mismatch": False,
        }
        workflow._process_sender(
            "feed@example.com",
            [("email-1", "@ToFeed")],
            {"feed@example.com": "Feed Sender"},
        )
        carddav.upsert_contact.assert_called_once()
        carddav.add_to_group.assert_not_called()

    def test_root_imbox_no_add_to_group(self, workflow, carddav):
        """Imbox (root) triage: upsert called, NO add_to_group (no ancestors)."""
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "imbox-uid-1",
            "group": "Imbox",
            "name_mismatch": False,
        }
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice"},
        )
        carddav.upsert_contact.assert_called_once()
        carddav.add_to_group.assert_not_called()


class TestAddToInboxNotInherited:
    """Person triage does NOT add Inbox even though Imbox has add_to_inbox=True."""

    def test_person_no_inbox(self, workflow):
        """Person destination list does NOT include Inbox (add_to_inbox not inherited)."""
        result = workflow._get_destination_mailbox_ids("@ToPerson")
        assert "mb-inbox" not in result
        assert result == ["mb-person", "mb-imbox"]

    def test_billboard_no_inbox(self, workflow):
        """Billboard destination list does NOT include Inbox (Paper Trail has no add_to_inbox)."""
        result = workflow._get_destination_mailbox_ids("@ToBillboard")
        assert "mb-inbox" not in result
        assert result == ["mb-billboard", "mb-papertrl"]

    def test_truck_no_inbox(self, workflow):
        """Truck destination list does NOT include Inbox (Paper Trail has no add_to_inbox)."""
        result = workflow._get_destination_mailbox_ids("@ToTruck")
        assert "mb-inbox" not in result
        assert result == ["mb-truck", "mb-papertrl"]


class TestRootCategoryAddToInbox:
    """Imbox triage adds Inbox via add_to_inbox flag."""

    def test_imbox_adds_inbox(self, workflow):
        """Imbox destination includes Inbox because add_to_inbox=True."""
        result = workflow._get_destination_mailbox_ids("@ToImbox")
        assert "mb-inbox" in result
        assert result == ["mb-imbox", "mb-inbox"]

    def test_feed_no_inbox(self, workflow):
        """Feed destination does NOT include Inbox (add_to_inbox=False)."""
        result = workflow._get_destination_mailbox_ids("@ToFeed")
        assert "mb-inbox" not in result
        assert result == ["mb-feed"]

    def test_paper_trail_no_inbox(self, workflow):
        """Paper Trail destination does NOT include Inbox (add_to_inbox=False)."""
        result = workflow._get_destination_mailbox_ids("@ToPaperTrail")
        assert "mb-inbox" not in result
        assert result == ["mb-papertrl"]

    def test_jail_no_inbox(self, workflow):
        """Jail destination does NOT include Inbox (add_to_inbox=False)."""
        result = workflow._get_destination_mailbox_ids("@ToJail")
        assert "mb-inbox" not in result
        assert result == ["mb-jail"]


# =============================================================================
# Plan 13-02: Re-triage tests
# =============================================================================


class TestRetriageGroupChainDiff:
    """Verify shared groups are untouched, only diff groups are added/removed."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        # Sender currently in Billboard (parent: Paper Trail)
        # Re-triaging to Truck (parent: Paper Trail)
        # Shared: Paper Trail, Diff: remove Billboard, add Truck
        carddav.search_by_email.return_value = [
            {
                "href": "/contact-chain.vcf",
                "etag": '"etag-chain"',
                "vcard_data": _make_vcard("chain@example.com", "chain-uid"),
            }
        ]
        carddav.check_membership.return_value = "Billboard"
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "chain-uid",
            "group": "Truck",
            "name_mismatch": False,
        }
        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-billboard", "mb-papertrl"},
        }

    def test_shared_group_not_touched(self, workflow, carddav):
        """Paper Trail is in both old and new chain -- not added or removed."""
        workflow._process_sender(
            "chain@example.com",
            [("email-1", "@ToTruck")],
        )
        # Paper Trail should NOT appear in add_to_group or remove_from_group calls
        add_groups = [c.args[0] for c in carddav.add_to_group.call_args_list]
        remove_groups = [c.args[0] for c in carddav.remove_from_group.call_args_list]
        assert "Paper Trail" not in add_groups
        assert "Paper Trail" not in remove_groups

    def test_new_group_added(self, workflow, carddav):
        """Truck (new-only) is added."""
        workflow._process_sender(
            "chain@example.com",
            [("email-1", "@ToTruck")],
        )
        add_groups = [c.args[0] for c in carddav.add_to_group.call_args_list]
        assert "Truck" in add_groups

    def test_old_group_removed(self, workflow, carddav):
        """Billboard (old-only) is removed."""
        workflow._process_sender(
            "chain@example.com",
            [("email-1", "@ToTruck")],
        )
        remove_groups = [c.args[0] for c in carddav.remove_from_group.call_args_list]
        assert "Billboard" in remove_groups


class TestRetriageAddBeforeRemove:
    """Verify add_to_group called before remove_from_group (safe order)."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        # Feed -> Imbox: add Imbox, remove Feed
        carddav.search_by_email.return_value = [
            {
                "href": "/contact-order.vcf",
                "etag": '"etag-order"',
                "vcard_data": _make_vcard("order@example.com", "order-uid"),
            }
        ]
        carddav.check_membership.return_value = "Feed"
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "order-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }
        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-feed"},
        }

    def test_add_before_remove(self, workflow, carddav):
        """add_to_group is called before remove_from_group."""
        call_order = []
        carddav.add_to_group.side_effect = lambda *a, **kw: call_order.append("add")
        carddav.remove_from_group.side_effect = lambda *a, **kw: call_order.append("remove")

        workflow._process_sender(
            "order@example.com",
            [("email-1", "@ToImbox")],
        )
        assert "add" in call_order
        assert "remove" in call_order
        assert call_order.index("add") < call_order.index("remove")


class TestRetriageLabelReconciliation:
    """Verify all managed labels stripped, new labels applied, Inbox not removed."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        # Sender in Feed, re-triaging to Imbox
        carddav.search_by_email.return_value = [
            {
                "href": "/contact-recon.vcf",
                "etag": '"etag-recon"',
                "vcard_data": _make_vcard("recon@example.com", "recon-uid"),
            }
        ]
        carddav.check_membership.return_value = "Feed"
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "recon-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }
        # Two emails: one in Feed, one in Feed+Inbox
        jmap.query_emails_by_sender.return_value = ["email-1", "email-2"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-feed"},
            "email-2": {"mb-feed", "mb-inbox"},
        }

    def test_managed_labels_stripped_new_labels_applied(self, workflow, jmap):
        """Email/set patches remove all managed labels + Screener, add new destination."""
        workflow._process_sender(
            "recon@example.com",
            [("email-1", "@ToImbox")],
        )
        # Find the Email/set call for reconciliation
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1
        # Check patches for email-1
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    update = mc[1].get("update", {})
                    if "email-1" in update:
                        patch = update["email-1"]
                        # Managed labels should be set to None (removed)
                        assert patch.get("mailboxIds/mb-feed") is None
                        # New destination should be True (added)
                        assert patch.get("mailboxIds/mb-imbox") is True

    def test_inbox_never_removed(self, workflow, jmap):
        """Inbox is NEVER set to None in reconciliation patches."""
        workflow._process_sender(
            "recon@example.com",
            [("email-1", "@ToImbox")],
        )
        for c in jmap.call.call_args_list:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    update = mc[1].get("update", {})
                    for eid, patch in update.items():
                        assert patch.get("mailboxIds/mb-inbox") is not None or "mailboxIds/mb-inbox" not in patch


class TestRetriageInboxScreenerOnly:
    """Verify Inbox added only to emails in Screener when add_to_inbox=true."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        # Sender in Feed, re-triaging to Imbox (add_to_inbox=True)
        carddav.search_by_email.return_value = [
            {
                "href": "/contact-inbox.vcf",
                "etag": '"etag-inbox"',
                "vcard_data": _make_vcard("inbox@example.com", "inbox-uid"),
            }
        ]
        carddav.check_membership.return_value = "Feed"
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "inbox-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }
        # email-1 is in Screener, email-2 is not
        jmap.query_emails_by_sender.return_value = ["email-1", "email-2"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-feed", "mb-screener"},
            "email-2": {"mb-feed"},
        }

    def test_inbox_added_to_screener_email_only(self, workflow, jmap):
        """Inbox added to email-1 (in Screener) but NOT email-2 (not in Screener)."""
        workflow._process_sender(
            "inbox@example.com",
            [("email-1", "@ToImbox")],
        )
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    update = mc[1].get("update", {})
                    if "email-1" in update:
                        assert update["email-1"].get("mailboxIds/mb-inbox") is True
                    if "email-2" in update:
                        assert "mailboxIds/mb-inbox" not in update["email-2"] or update["email-2"].get("mailboxIds/mb-inbox") is not True


class TestRetriageStructuredLogging:
    """Verify group_reassigned log event fields."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = [
            {
                "href": "/contact-log.vcf",
                "etag": '"etag-log"',
                "vcard_data": _make_vcard("log@example.com", "log-uid"),
            }
        ]
        carddav.check_membership.return_value = "Feed"
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "log-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }
        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-feed"},
        }

    def test_group_reassigned_log_event(self, workflow):
        """group_reassigned event logged with old_group, new_group, same_group fields."""
        import structlog.testing

        with structlog.testing.capture_logs() as logs:
            workflow._process_sender(
                "log@example.com",
                [("email-1", "@ToImbox")],
            )
        reassigned = [l for l in logs if l.get("event") == "group_reassigned"]
        assert len(reassigned) == 1
        assert reassigned[0]["old_group"] == "Feed"
        assert reassigned[0]["new_group"] == "Imbox"
        assert reassigned[0]["same_group"] is False

    def test_same_group_log_event(self, workflow, carddav, jmap):
        """same_group=True when old and new group are the same."""
        import structlog.testing

        carddav.check_membership.return_value = "Imbox"
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-imbox"},
        }
        with structlog.testing.capture_logs() as logs:
            workflow._process_sender(
                "log@example.com",
                [("email-1", "@ToImbox")],
            )
        reassigned = [l for l in logs if l.get("event") == "group_reassigned"]
        assert len(reassigned) == 1
        assert reassigned[0]["same_group"] is True


class TestInitialTriageUsesReconciliation:
    """Verify new sender uses full email reconciliation (same path as retriage)."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "initial-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_initial_triage_uses_full_reconciliation(self, workflow, jmap):
        """New sender uses query_emails_by_sender for full reconciliation."""
        workflow._process_sender(
            "new@example.com",
            [("email-1", "@ToImbox")],
        )
        jmap.query_emails_by_sender.assert_any_call("new@example.com")

    def test_initial_triage_reconciles_via_email_set(self, workflow, jmap):
        """New sender reconciles via Email/set patches (not batch_move_emails)."""
        workflow._process_sender(
            "new@example.com",
            [("email-1", "@ToImbox")],
        )
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1

    def test_initial_triage_logs_triage_complete(self, workflow):
        """New sender logs triage_complete (not group_reassigned)."""
        import structlog.testing

        with structlog.testing.capture_logs() as logs:
            workflow._process_sender(
                "new@example.com",
                [("email-1", "@ToImbox")],
            )
        triage_events = [l for l in logs if l.get("event") == "triage_complete"]
        reassigned_events = [l for l in logs if l.get("event") == "group_reassigned"]
        assert len(triage_events) == 1
        assert len(reassigned_events) == 0


class TestInitialTriageSweepsAllMailboxes:
    """Regression test: initial triage sweeps emails across ALL mailboxes, not just Screener.

    This was the root cause of a bug where triaging from Screener only processed
    Screener emails. A second triage (retriage) fixed it because it used
    query_emails_by_sender which searches all mailboxes.
    """

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "sweep-all-uid",
            "group": "Feed",
            "name_mismatch": False,
        }

        # Sender has emails in BOTH Screener and other mailboxes
        jmap.query_emails_by_sender.return_value = [
            "email-screener-1",
            "email-screener-2",
            "email-inbox-1",
        ]
        jmap.get_email_mailbox_ids.return_value = {
            "email-screener-1": {"mb-screener"},
            "email-screener-2": {"mb-screener"},
            "email-inbox-1": {"mb-inbox"},
        }

    def test_queries_all_mailboxes(self, workflow, jmap):
        """Initial triage uses query_emails_by_sender (all mailboxes), not query_emails (Screener only)."""
        workflow._process_sender(
            "alice@example.com", [("email-screener-1", "@ToFeed")]
        )
        jmap.query_emails_by_sender.assert_any_call("alice@example.com")
        jmap.query_emails.assert_not_called()

    def test_all_emails_get_new_labels(self, workflow, jmap):
        """All emails from sender get new destination labels, including those outside Screener."""
        workflow._process_sender(
            "alice@example.com", [("email-screener-1", "@ToFeed")]
        )
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        patched_ids = set()
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    patched_ids.update(mc[1].get("update", {}).keys())
        # All 3 emails should be patched (including the one in Inbox)
        assert patched_ids == {"email-screener-1", "email-screener-2", "email-inbox-1"}

    def test_inbox_email_gets_feed_label(self, workflow, jmap):
        """Email already in Inbox gets Feed label applied too."""
        workflow._process_sender(
            "alice@example.com", [("email-screener-1", "@ToFeed")]
        )
        for c in jmap.call.call_args_list:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    update = mc[1].get("update", {})
                    if "email-inbox-1" in update:
                        patch = update["email-inbox-1"]
                        assert patch.get("mailboxIds/mb-feed") is True


# =============================================================================
# Plan 12-01: Batched label scanning with per-method error handling
# =============================================================================


def _make_batched_call_side_effect(
    label_emails: dict[str, list[str]],
    mailbox_ids: dict[str, str],
    error_labels: dict[str, dict] | None = None,
):
    """Build a jmap.call side_effect that handles batched Email/query, Email/get, and Email/set.

    Args:
        label_emails: Mapping of label mailbox ID -> list of email IDs returned.
        mailbox_ids: The mock_mailbox_ids dict (name -> id).
        error_labels: If given, mapping of label mailbox ID -> error dict
            (e.g., {"type": "serverFail", "description": "..."}).
            These labels return ["error", {...}, call_id] instead of Email/query.
    """
    error_labels = error_labels or {}

    def side_effect(method_calls):
        first_method = method_calls[0][0]

        # Batched Email/query for discovery
        if first_method == "Email/query":
            responses = []
            for mc in method_calls:
                label_id = mc[1]["filter"]["inMailbox"]
                call_id = mc[2]
                if label_id in error_labels:
                    responses.append(["error", error_labels[label_id], call_id])
                else:
                    ids = label_emails.get(label_id, [])
                    responses.append(
                        ["Email/query", {"ids": ids, "total": len(ids)}, call_id]
                    )
            return responses

        # Email/get for error filtering or sender fetching
        if first_method == "Email/get":
            ids = method_calls[0][1].get("ids", [])
            props = method_calls[0][1].get("properties", [])
            # Sender fetch: properties include "from"
            if "from" in props:
                raise AssertionError("Sender fetch should use get_email_senders, not call()")
            # Error filtering: return emails with their mailbox IDs
            email_list = []
            for eid in ids:
                # Find which label mailbox this email belongs to
                mbox_ids = {}
                for label_mbid, eids in label_emails.items():
                    if eid in eids:
                        mbox_ids[label_mbid] = True
                email_list.append({"id": eid, "mailboxIds": mbox_ids})
            return [["Email/get", {"list": email_list}, "g0"]]

        # Email/set for error/warning labeling
        if first_method == "Email/set":
            return [["Email/set", {"updated": {}}, method_calls[0][2]]]

        return []

    return side_effect


class TestBatchedCollectTriaged:
    """_collect_triaged() uses batched jmap.call() with Email/query per label (SCAN-01, SCAN-02)."""

    def test_calls_jmap_call_once_for_discovery(self, workflow, jmap, mock_mailbox_ids):
        """_collect_triaged() calls jmap.call() exactly once for Email/query discovery."""
        jmap.call.side_effect = _make_batched_call_side_effect({}, mock_mailbox_ids)
        workflow._collect_triaged()
        # First call should be the batched Email/query
        query_calls = [
            c for c in jmap.call.call_args_list
            if c.args[0][0][0] == "Email/query"
        ]
        assert len(query_calls) == 1

    def test_does_not_call_query_emails_for_discovery(self, workflow, jmap, mock_mailbox_ids):
        """_collect_triaged() does NOT use jmap.query_emails() for discovery."""
        jmap.call.side_effect = _make_batched_call_side_effect({}, mock_mailbox_ids)
        workflow._collect_triaged()
        jmap.query_emails.assert_not_called()

    def test_batch_has_one_query_per_label(self, workflow, jmap, mock_mailbox_ids):
        """Batch contains exactly N Email/query calls (one per triage label)."""
        jmap.call.side_effect = _make_batched_call_side_effect({}, mock_mailbox_ids)
        workflow._collect_triaged()
        batch_call = jmap.call.call_args_list[0]
        method_calls = batch_call.args[0]
        assert len(method_calls) == 7  # 7 triage labels in v1.2 defaults
        for mc in method_calls:
            assert mc[0] == "Email/query"

    def test_each_query_uses_inmailbox_filter(self, workflow, jmap, mock_mailbox_ids):
        """Each Email/query uses inMailbox filter with the label's mailbox ID."""
        jmap.call.side_effect = _make_batched_call_side_effect({}, mock_mailbox_ids)
        workflow._collect_triaged()
        batch_call = jmap.call.call_args_list[0]
        method_calls = batch_call.args[0]
        queried_mailbox_ids = {mc[1]["filter"]["inMailbox"] for mc in method_calls}
        assert "mb-toimbox" in queried_mailbox_ids
        assert "mb-tofeed" in queried_mailbox_ids
        assert "mb-topapertrl" in queried_mailbox_ids
        assert "mb-tojail" in queried_mailbox_ids
        assert "mb-toperson" in queried_mailbox_ids
        assert "mb-tobillboard" in queried_mailbox_ids
        assert "mb-totruck" in queried_mailbox_ids

    def test_each_query_has_limit_100(self, workflow, jmap, mock_mailbox_ids):
        """Each Email/query has limit: 100."""
        jmap.call.side_effect = _make_batched_call_side_effect({}, mock_mailbox_ids)
        workflow._collect_triaged()
        batch_call = jmap.call.call_args_list[0]
        method_calls = batch_call.args[0]
        for mc in method_calls:
            assert mc[1]["limit"] == 100

    def test_each_query_has_unique_call_id(self, workflow, jmap, mock_mailbox_ids):
        """Each Email/query has a unique call-id (q0, q1, ...)."""
        jmap.call.side_effect = _make_batched_call_side_effect({}, mock_mailbox_ids)
        workflow._collect_triaged()
        batch_call = jmap.call.call_args_list[0]
        method_calls = batch_call.args[0]
        call_ids = [mc[2] for mc in method_calls]
        assert len(call_ids) == len(set(call_ids))  # all unique
        for i, cid in enumerate(call_ids):
            assert cid == f"q{i}"

    def test_successful_batch_returns_emails_grouped_by_sender(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """Successful batch returns emails grouped by sender (same structure as before)."""
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"], "mb-tofeed": ["email-2"]},
            mock_mailbox_ids,
        )
        jmap.get_email_senders.return_value = {
            "email-1": ("alice@example.com", "Alice"),
            "email-2": ("bob@example.com", "Bob"),
        }
        triaged, sender_names = workflow._collect_triaged()
        assert "alice@example.com" in triaged
        assert "bob@example.com" in triaged
        assert triaged["alice@example.com"] == [("email-1", "@ToImbox")]
        assert triaged["bob@example.com"] == [("email-2", "@ToFeed")]

    def test_single_sender_fetch_for_all_labels(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """Single get_email_senders call with ALL email IDs from ALL labels."""
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"], "mb-tofeed": ["email-2"]},
            mock_mailbox_ids,
        )
        jmap.get_email_senders.return_value = {
            "email-1": ("alice@example.com", "Alice"),
            "email-2": ("bob@example.com", "Bob"),
        }
        workflow._collect_triaged()
        jmap.get_email_senders.assert_called_once()
        called_ids = jmap.get_email_senders.call_args.args[0]
        assert set(called_ids) == {"email-1", "email-2"}

    def test_all_empty_returns_empty_without_sender_fetch(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """When all labels return empty, returns ({}, {}) without calling get_email_senders."""
        jmap.call.side_effect = _make_batched_call_side_effect({}, mock_mailbox_ids)
        triaged, sender_names = workflow._collect_triaged()
        assert triaged == {}
        assert sender_names == {}
        jmap.get_email_senders.assert_not_called()

    def test_error_filtering_is_separate_call(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """Error filtering (@MailroomError check) is a separate jmap.call() after batch."""
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"]},
            mock_mailbox_ids,
        )
        jmap.get_email_senders.return_value = {
            "email-1": ("alice@example.com", "Alice"),
        }
        workflow._collect_triaged()
        # Should have 2 jmap.call() invocations: 1 batch + 1 error filter
        assert jmap.call.call_count == 2
        # First call: batched Email/query
        assert jmap.call.call_args_list[0].args[0][0][0] == "Email/query"
        # Second call: Email/get for error filtering
        assert jmap.call.call_args_list[1].args[0][0][0] == "Email/get"


class TestBatchedPerMethodError:
    """Per-method error detection in batched responses (SCAN-03)."""

    def test_one_label_fails_others_still_process(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """When one label returns error, that label is skipped but others process normally."""
        jmap.call.side_effect = _make_batched_call_side_effect(
            {"mb-toimbox": ["email-1"]},
            mock_mailbox_ids,
            error_labels={"mb-tofeed": {"type": "serverFail", "description": "Temporary"}},
        )
        jmap.get_email_senders.return_value = {
            "email-1": ("alice@example.com", "Alice"),
        }
        triaged, sender_names = workflow._collect_triaged()
        assert "alice@example.com" in triaged
        assert triaged["alice@example.com"] == [("email-1", "@ToImbox")]

    def test_failed_label_logged_at_warning_on_first_failure(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """First failure for a label is logged at WARNING level."""
        import structlog.testing

        jmap.call.side_effect = _make_batched_call_side_effect(
            {},
            mock_mailbox_ids,
            error_labels={"mb-tofeed": {"type": "serverFail", "description": "Temp"}},
        )
        with structlog.testing.capture_logs() as logs:
            workflow._collect_triaged()
        warning_logs = [l for l in logs if l.get("event") == "label_query_failed"]
        assert len(warning_logs) >= 1
        assert warning_logs[0]["log_level"] == "warning"
        assert warning_logs[0]["consecutive_failures"] == 1

    def test_three_consecutive_failures_logged_at_error(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """After 3 consecutive failures for the same label, logged at ERROR level."""
        import structlog.testing

        side_effect = _make_batched_call_side_effect(
            {},
            mock_mailbox_ids,
            error_labels={"mb-tofeed": {"type": "serverFail", "description": "Persistent"}},
        )
        jmap.call.side_effect = side_effect

        # First 2 polls: WARNING
        workflow._collect_triaged()
        workflow._collect_triaged()

        # Third poll: should escalate to ERROR
        with structlog.testing.capture_logs() as logs:
            workflow._collect_triaged()
        error_logs = [l for l in logs if l.get("event") == "label_query_persistent_failure"]
        assert len(error_logs) >= 1
        assert error_logs[0]["log_level"] == "error"
        assert error_logs[0]["consecutive_failures"] == 3

    def test_counter_resets_on_success(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """Counter resets to 0 when a previously-failing label succeeds."""
        import structlog.testing

        # First 2 polls: Feed fails
        fail_side_effect = _make_batched_call_side_effect(
            {},
            mock_mailbox_ids,
            error_labels={"mb-tofeed": {"type": "serverFail", "description": "Temp"}},
        )
        jmap.call.side_effect = fail_side_effect
        workflow._collect_triaged()
        workflow._collect_triaged()

        # Third poll: Feed succeeds
        success_side_effect = _make_batched_call_side_effect(
            {},
            mock_mailbox_ids,
        )
        jmap.call.side_effect = success_side_effect
        workflow._collect_triaged()

        # Fourth poll: Feed fails again -- should be WARNING (count=1), not ERROR
        jmap.call.side_effect = fail_side_effect
        with structlog.testing.capture_logs() as logs:
            workflow._collect_triaged()
        # Should have WARNING for label_query_failed, NOT ERROR
        warning_logs = [l for l in logs if l.get("event") == "label_query_failed"]
        error_logs = [l for l in logs if l.get("event") == "label_query_persistent_failure"]
        assert len(warning_logs) >= 1
        assert warning_logs[0]["consecutive_failures"] == 1  # Reset to 1
        assert len(error_logs) == 0

    def test_all_labels_fail_returns_empty(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """When ALL labels fail, _collect_triaged() returns ({}, {})."""
        error_labels = {
            "mb-toimbox": {"type": "serverFail", "description": "Fail"},
            "mb-tofeed": {"type": "serverFail", "description": "Fail"},
            "mb-topapertrl": {"type": "serverFail", "description": "Fail"},
            "mb-tojail": {"type": "serverFail", "description": "Fail"},
            "mb-toperson": {"type": "serverFail", "description": "Fail"},
            "mb-tobillboard": {"type": "serverFail", "description": "Fail"},
            "mb-totruck": {"type": "serverFail", "description": "Fail"},
        }
        jmap.call.side_effect = _make_batched_call_side_effect(
            {},
            mock_mailbox_ids,
            error_labels=error_labels,
        )
        triaged, sender_names = workflow._collect_triaged()
        assert triaged == {}
        assert sender_names == {}
        jmap.get_email_senders.assert_not_called()


class TestBatchedPagination:
    """Pagination edge case: total > len(ids) triggers follow-up query."""

    def test_pagination_follow_up_for_large_label(
        self, workflow, jmap, mock_mailbox_ids
    ):
        """When a label's total > len(ids), follow-up paginated query made for that label."""

        call_count = {"n": 0}

        def side_effect(method_calls):
            call_count["n"] += 1
            first_method = method_calls[0][0]

            if first_method == "Email/query":
                if call_count["n"] == 1:
                    # Batched query: mb-toimbox returns 2 ids but total=5
                    responses = []
                    for mc in method_calls:
                        label_id = mc[1]["filter"]["inMailbox"]
                        call_id = mc[2]
                        if label_id == "mb-toimbox":
                            responses.append(
                                ["Email/query", {"ids": ["e1", "e2"], "total": 5}, call_id]
                            )
                        else:
                            responses.append(
                                ["Email/query", {"ids": [], "total": 0}, call_id]
                            )
                    return responses

            if first_method == "Email/get":
                ids = method_calls[0][1].get("ids", [])
                return [["Email/get", {"list": [
                    {"id": eid, "mailboxIds": {"mb-toimbox": True}} for eid in ids
                ]}, "g0"]]

            return []

        jmap.call.side_effect = side_effect
        # Follow-up query for pagination
        jmap.query_emails.return_value = ["e1", "e2", "e3", "e4", "e5"]
        jmap.get_email_senders.return_value = {
            f"e{i}": (f"alice@example.com", "Alice") for i in range(1, 6)
        }
        triaged, _ = workflow._collect_triaged()
        # Should have called query_emails for the pagination follow-up
        jmap.query_emails.assert_called_once()
        # All 5 emails should be in the result
        assert len(triaged.get("alice@example.com", [])) == 5


class TestBatchedExistingBehaviorPreserved:
    """Existing behavior preserved after batching refactor."""

    def test_process_sender_uses_query_emails_by_sender_for_reconciliation(
        self, workflow, jmap, carddav
    ):
        """_process_sender reconciliation uses jmap.query_emails_by_sender() for full sweep."""
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "sweep-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.query_emails_by_sender.assert_any_call("alice@example.com")


# =============================================================================
# Plan 14-02: @MailroomWarning cleanup + provenance_group plumbing
# =============================================================================


class TestWarningCleanupBeforeProcessing:
    """_process_sender removes @MailroomWarning from ALL sender emails before processing."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "cleanup-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        # Sender has 3 emails, some with @MailroomWarning
        jmap.query_emails_by_sender.return_value = ["email-1", "email-2", "email-3"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
            "email-2": {"mb-screener"},
            "email-3": {"mb-screener"},
        }

    def test_warning_cleanup_calls_batch_remove(self, workflow, jmap):
        """batch_remove_labels called with warning label ID for all sender emails."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice"},
        )
        jmap.batch_remove_labels.assert_called_once_with(
            ["email-1", "email-2", "email-3"],
            ["mb-warning"],
        )

    def test_warning_cleanup_before_upsert(self, workflow, jmap, carddav):
        """Warning cleanup happens BEFORE upsert_contact."""
        call_order = []
        jmap.batch_remove_labels.side_effect = lambda *a, **kw: call_order.append("cleanup")
        carddav.upsert_contact.side_effect = lambda *a, **kw: (
            call_order.append("upsert"),
            {"action": "created", "uid": "cleanup-uid", "group": "Imbox", "name_mismatch": False},
        )[1]

        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice"},
        )
        assert call_order.index("cleanup") < call_order.index("upsert")


class TestWarningCleanupThenReapply:
    """Warning is cleaned up then reapplied if name mismatch persists."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "reapply-uid",
            "group": "Imbox",
            "name_mismatch": True,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_cleanup_then_warning_reapplied(self, workflow, jmap):
        """Cleanup removes warning, then _apply_warning_label reapplies it."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice New Name"},
        )
        # Cleanup was called
        jmap.batch_remove_labels.assert_called_once()
        # Warning was reapplied via Email/set
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        found_warning = False
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid, update in mc[1].get("update", {}).items():
                        if "mailboxIds/mb-warning" in update:
                            found_warning = True
        assert found_warning


class TestWarningCleanupNoReapply:
    """Warning is cleaned up and NOT reapplied when no name mismatch."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "no-reapply-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_cleanup_no_warning_reapplied(self, workflow, jmap):
        """Cleanup removes warning, no reapply since no mismatch."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice"},
        )
        jmap.batch_remove_labels.assert_called_once()
        # No Email/set calls with warning mailbox
        email_set_calls = [
            c for c in jmap.call.call_args_list
            if any(mc[0] == "Email/set" for mc in c.args[0])
        ]
        for c in email_set_calls:
            for mc in c.args[0]:
                if mc[0] == "Email/set":
                    for eid, update in mc[1].get("update", {}).items():
                        assert "mailboxIds/mb-warning" not in update


class TestProvenanceGroupPlumbing:
    """_process_sender passes settings.mailroom.provenance_group to upsert_contact."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "prov-uid",
            "group": "Imbox",
            "name_mismatch": False,
        }

        jmap.query_emails_by_sender.return_value = ["email-1"]
        jmap.get_email_mailbox_ids.return_value = {
            "email-1": {"mb-screener"},
        }

    def test_provenance_group_passed_to_upsert(self, workflow, carddav):
        """upsert_contact is called with provenance_group='Mailroom'."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice", "Imbox",
            contact_type="company",
            provenance_group="Mailroom",
        )


# =============================================================================
# Helper functions
# =============================================================================


def _make_vcard(email: str, uid: str) -> str:
    """Build a minimal vCard string for testing."""
    card = vobject.vCard()
    card.add("uid").value = uid
    card.add("fn").value = email.split("@")[0]
    card.add("n").value = vobject.vcard.Name(given=email.split("@")[0])
    email_prop = card.add("email")
    email_prop.value = email
    email_prop.type_param = "INTERNET"
    return card.serialize()
