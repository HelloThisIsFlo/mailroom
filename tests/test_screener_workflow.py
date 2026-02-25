"""TDD tests for ScreenerWorkflow poll cycle, conflict detection, error labeling, and per-sender processing."""

from unittest.mock import MagicMock, call

import pytest
import vobject

from mailroom.workflows.screener import ScreenerWorkflow


@pytest.fixture
def jmap(mock_mailbox_ids):
    """Mock JMAPClient with sensible defaults."""
    client = MagicMock()
    client.account_id = "acc-001"

    # Default: no emails in any triage label
    client.query_emails.return_value = []
    client.get_email_senders.return_value = {}

    # Default: Email/get returns empty list (no emails to check for error label)
    client.call.return_value = [["Email/get", {"list": []}, "g0"]]

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
        # Should query each of the 5 triage labels (including @ToPerson)
        assert jmap.query_emails.call_count == 5
        queried_ids = [c.args[0] for c in jmap.query_emails.call_args_list]
        assert "mb-toimbox" in queried_ids
        assert "mb-tofeed" in queried_ids
        assert "mb-topapertrl" in queried_ids
        assert "mb-tojail" in queried_ids
        assert "mb-toperson" in queried_ids

    def test_no_sender_lookup(self, workflow, jmap):
        workflow.poll()
        jmap.get_email_senders.assert_not_called()


class TestPollSingleSenderSingleLabel:
    """1 sender, 1 label, 1 email -> clean sender processed."""

    @pytest.fixture(autouse=True)
    def setup_one_email(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice Smith")}
        # Email/get: email-1 does NOT have error label
        jmap.call.return_value = [
            ["Email/get", {"list": [{"id": "email-1", "mailboxIds": {"mb-toimbox": True}}]}, "g0"]
        ]

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
    def setup_conflicting(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1"]
            if mailbox_id == "mb-tofeed":
                return ["email-2"]
            return []

        jmap.query_emails.side_effect = query_side_effect

        def sender_side_effect(email_ids):
            result = {}
            for eid in email_ids:
                result[eid] = ("bob@example.com", "Bob Example")
            return result

        jmap.get_email_senders.side_effect = sender_side_effect

        # Email/get: neither email has error label
        def call_side_effect(method_calls):
            method = method_calls[0][0]
            if method == "Email/get":
                ids = method_calls[0][1].get("ids", [])
                return [
                    [
                        "Email/get",
                        {
                            "list": [
                                {"id": eid, "mailboxIds": {"mb-toimbox": True}}
                                for eid in ids
                            ]
                        },
                        "g0",
                    ]
                ]
            # Email/set for error labeling -> success
            return [["Email/set", {"updated": {"email-1": None}}, "err0"]]

        jmap.call.side_effect = call_side_effect

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
    def setup_two_senders(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1", "email-2"]
            return []

        jmap.query_emails.side_effect = query_side_effect
        jmap.get_email_senders.return_value = {
            "email-1": ("alice@example.com", "Alice"),
            "email-2": ("carol@example.com", "Carol"),
        }
        # Neither has error label
        jmap.call.return_value = [
            [
                "Email/get",
                {
                    "list": [
                        {"id": "email-1", "mailboxIds": {"mb-toimbox": True}},
                        {"id": "email-2", "mailboxIds": {"mb-toimbox": True}},
                    ]
                },
                "g0",
            ]
        ]

    def test_both_senders_attempted(self, workflow):
        """Both senders get _process_sender called (stub fails, both counted as failures)."""
        result = workflow.poll()
        # Both senders fail because _process_sender is a stub
        assert result == 0


class TestPollMixedCleanAndConflicted:
    """1 clean sender + 1 conflicted sender -> clean processed, conflicted gets error label."""

    @pytest.fixture(autouse=True)
    def setup_mixed(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1", "email-2"]  # alice clean, bob conflict
            if mailbox_id == "mb-tofeed":
                return ["email-3"]  # bob conflict
            return []

        jmap.query_emails.side_effect = query_side_effect

        def sender_side_effect(email_ids):
            mapping = {
                "email-1": ("alice@example.com", "Alice"),
                "email-2": ("bob@example.com", "Bob"),
                "email-3": ("bob@example.com", "Bob"),
            }
            return {eid: mapping[eid] for eid in email_ids if eid in mapping}

        jmap.get_email_senders.side_effect = sender_side_effect

        def call_side_effect(method_calls):
            method = method_calls[0][0]
            if method == "Email/get":
                ids = method_calls[0][1].get("ids", [])
                return [
                    [
                        "Email/get",
                        {
                            "list": [
                                {"id": eid, "mailboxIds": {"mb-toimbox": True}}
                                for eid in ids
                            ]
                        },
                        "g0",
                    ]
                ]
            return [["Email/set", {"updated": {}}, "err0"]]

        jmap.call.side_effect = call_side_effect

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
    def setup_errored(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice")}
        # email-1 already has the error label
        jmap.call.return_value = [
            [
                "Email/get",
                {
                    "list": [
                        {
                            "id": "email-1",
                            "mailboxIds": {"mb-toimbox": True, "mb-error": True},
                        }
                    ]
                },
                "g0",
            ]
        ]

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
    def setup_missing_sender(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1", "email-2"]
            return []

        jmap.query_emails.side_effect = query_side_effect
        # email-1 has no sender, email-2 has a sender
        jmap.get_email_senders.return_value = {"email-2": ("alice@example.com", "Alice")}
        # Neither has error label
        jmap.call.return_value = [
            [
                "Email/get",
                {
                    "list": [
                        {"id": "email-2", "mailboxIds": {"mb-toimbox": True}},
                    ]
                },
                "g0",
            ]
        ]

    def test_sender_with_email_still_processed(self, workflow):
        """alice@example.com is still collected even though email-1 has no sender."""
        result = workflow.poll()
        # Stub _process_sender raises, so returns 0, but alice was attempted
        assert result == 0


class TestApplyErrorLabelTransientFailure:
    """_apply_error_label fails (transient) -> logged, poll continues."""

    @pytest.fixture(autouse=True)
    def setup_error_label_failure(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1"]
            if mailbox_id == "mb-tofeed":
                return ["email-2"]
            return []

        jmap.query_emails.side_effect = query_side_effect

        def sender_side_effect(email_ids):
            return {eid: ("bob@example.com", "Bob") for eid in email_ids}

        jmap.get_email_senders.side_effect = sender_side_effect

        call_count = {"n": 0}

        def call_side_effect(method_calls):
            method = method_calls[0][0]
            if method == "Email/get":
                ids = method_calls[0][1].get("ids", [])
                return [
                    [
                        "Email/get",
                        {
                            "list": [
                                {"id": eid, "mailboxIds": {"mb-toimbox": True}}
                                for eid in ids
                            ]
                        },
                        "g0",
                    ]
                ]
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
    def setup_process_failure(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice")}
        jmap.call.return_value = [
            [
                "Email/get",
                {"list": [{"id": "email-1", "mailboxIds": {"mb-toimbox": True}}]},
                "g0",
            ]
        ]

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
    def setup_mixed_errored(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1", "email-2"]
            return []

        jmap.query_emails.side_effect = query_side_effect
        jmap.get_email_senders.return_value = {
            "email-1": ("alice@example.com", "Alice"),
            "email-2": ("bob@example.com", "Bob"),
        }
        # email-1 has error label, email-2 does not
        jmap.call.return_value = [
            [
                "Email/get",
                {
                    "list": [
                        {
                            "id": "email-1",
                            "mailboxIds": {"mb-toimbox": True, "mb-error": True},
                        },
                        {
                            "id": "email-2",
                            "mailboxIds": {"mb-toimbox": True},
                        },
                    ]
                },
                "g0",
            ]
        ]

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
    """_get_destination_mailbox_ids maps triage labels to correct mailbox IDs."""

    def test_imbox_maps_to_inbox(self, workflow):
        """@ToImbox -> [inbox_id]: emails appear in Inbox."""
        result = workflow._get_destination_mailbox_ids("@ToImbox")
        assert result == ["mb-inbox"]

    def test_feed_maps_to_feed(self, workflow):
        """@ToFeed -> [feed_id]: emails go to Feed mailbox."""
        result = workflow._get_destination_mailbox_ids("@ToFeed")
        assert result == ["mb-feed"]

    def test_paper_trail_maps_to_paper_trail(self, workflow):
        """@ToPaperTrail -> [paper_trail_id]: emails go to Paper Trail mailbox."""
        result = workflow._get_destination_mailbox_ids("@ToPaperTrail")
        assert result == ["mb-papertrl"]

    def test_jail_maps_to_jail(self, workflow):
        """@ToJail -> [jail_id]: emails go to Jail mailbox."""
        result = workflow._get_destination_mailbox_ids("@ToJail")
        assert result == ["mb-jail"]


class TestProcessSenderNewContact:
    """New sender triaged to @ToImbox: full pipeline with contact creation."""

    @pytest.fixture(autouse=True)
    def setup_new_sender(self, jmap, carddav):
        # CardDAV: no existing contact, upsert creates one
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "new-uid-123",
            "group": "Imbox",
        }
        # CardDAV: search returns empty (new sender)
        carddav.search_by_email.return_value = []

        # JMAP: sweep finds 3 emails in Screener from this sender
        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "alice@example.com":
                return ["email-1", "email-2", "email-3"]
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_upsert_contact_called(self, workflow, carddav):
        """upsert_contact called with sender, display name from sender_names, group name."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice Smith"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice Smith", "Imbox"
        )

    def test_sweep_queries_screener(self, workflow, jmap):
        """Sweep query searches Screener for all emails from sender."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        # Should call query_emails with screener_id and sender
        jmap.query_emails.assert_called_once_with(
            "mb-screener", sender="alice@example.com"
        )

    def test_batch_move_called_with_inbox(self, workflow, jmap):
        """batch_move_emails called: remove Screener, add Inbox for Imbox destination."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.batch_move_emails.assert_called_once_with(
            ["email-1", "email-2", "email-3"],
            "mb-screener",
            ["mb-inbox"],
        )

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
        }
        carddav.search_by_email.return_value = []

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "bob@example.com":
                return ["email-5", "email-6"]
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_batch_move_to_feed(self, workflow, jmap):
        """batch_move_emails uses Feed mailbox ID for @ToFeed destination."""
        workflow._process_sender(
            "bob@example.com", [("email-5", "@ToFeed")]
        )
        jmap.batch_move_emails.assert_called_once_with(
            ["email-5", "email-6"],
            "mb-screener",
            ["mb-feed"],
        )

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
        }
        carddav.search_by_email.return_value = []

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "carol@example.com":
                return ["email-10"]
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_batch_move_to_paper_trail(self, workflow, jmap):
        workflow._process_sender(
            "carol@example.com", [("email-10", "@ToPaperTrail")]
        )
        jmap.batch_move_emails.assert_called_once_with(
            ["email-10"],
            "mb-screener",
            ["mb-papertrl"],
        )


class TestProcessSenderJail:
    """Sender triaged to @ToJail: emails go to Jail mailbox."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "jail-uid",
            "group": "Jail",
        }
        carddav.search_by_email.return_value = []

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "spam@example.com":
                return ["email-20"]
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_batch_move_to_jail(self, workflow, jmap):
        workflow._process_sender(
            "spam@example.com", [("email-20", "@ToJail")]
        )
        jmap.batch_move_emails.assert_called_once_with(
            ["email-20"],
            "mb-screener",
            ["mb-jail"],
        )


class TestProcessSenderMultipleTriggering:
    """Sender with 5 triggering emails and 5 more in Screener: all swept, only triggering get remove_label."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "multi-uid",
            "group": "Imbox",
        }
        carddav.search_by_email.return_value = []

        # Sweep finds all 10 emails
        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "alice@example.com":
                return [f"email-{i}" for i in range(1, 11)]
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_all_swept(self, workflow, jmap):
        """All 10 Screener emails from sender are swept."""
        triggering = [(f"email-{i}", "@ToImbox") for i in range(1, 6)]
        workflow._process_sender("alice@example.com", triggering)
        jmap.batch_move_emails.assert_called_once_with(
            [f"email-{i}" for i in range(1, 11)],
            "mb-screener",
            ["mb-inbox"],
        )

    def test_only_triggering_get_remove_label(self, workflow, jmap):
        """Only the 5 triggering emails get triage label removed."""
        triggering = [(f"email-{i}", "@ToImbox") for i in range(1, 6)]
        workflow._process_sender("alice@example.com", triggering)
        assert jmap.remove_label.call_count == 5
        removed_ids = [c.args[0] for c in jmap.remove_label.call_args_list]
        assert removed_ids == [f"email-{i}" for i in range(1, 6)]


class TestProcessSenderStepOrder:
    """Verify strict step ordering: already-grouped check -> upsert -> sweep -> remove label."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "order-uid",
            "group": "Imbox",
        }

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "alice@example.com":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_upsert_before_sweep(self, workflow, jmap, carddav):
        """upsert_contact is called before any JMAP sweep/move calls."""
        call_order = []
        carddav.upsert_contact.side_effect = lambda *a, **kw: (
            call_order.append("upsert"),
            {"action": "created", "uid": "order-uid", "group": "Imbox"},
        )[1]

        orig_query = jmap.query_emails.side_effect

        def tracking_query(mailbox_id, **kwargs):
            if mailbox_id == "mb-screener":
                call_order.append("sweep_query")
            return orig_query(mailbox_id, **kwargs)

        jmap.query_emails.side_effect = tracking_query
        jmap.batch_move_emails.side_effect = lambda *a, **kw: call_order.append(
            "batch_move"
        )
        jmap.remove_label.side_effect = lambda *a, **kw: call_order.append(
            "remove_label"
        )

        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )

        assert call_order == ["upsert", "sweep_query", "batch_move", "remove_label"]

    def test_remove_label_is_last(self, workflow, jmap, carddav):
        """remove_label is the very last operation."""
        call_order = []
        carddav.upsert_contact.side_effect = lambda *a, **kw: (
            call_order.append("upsert"),
            {"action": "created", "uid": "order-uid", "group": "Imbox"},
        )[1]
        jmap.batch_move_emails.side_effect = lambda *a, **kw: call_order.append(
            "batch_move"
        )
        jmap.remove_label.side_effect = lambda *a, **kw: call_order.append(
            "remove_label"
        )

        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        assert call_order[-1] == "remove_label"


class TestAlreadyGroupedDifferentGroup:
    """Sender already in 'Feed' group, triaged to @ToImbox: error label applied, processing stops."""

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
        # The contact is in Feed group (not Imbox)
        carddav._groups = {
            "Imbox": {"href": "/group-imbox.vcf", "etag": '"etag-g1"', "uid": "g-imbox-uid"},
            "Feed": {"href": "/group-feed.vcf", "etag": '"etag-g2"', "uid": "g-feed-uid"},
            "Paper Trail": {"href": "/group-pt.vcf", "etag": '"etag-g3"', "uid": "g-pt-uid"},
            "Jail": {"href": "/group-jail.vcf", "etag": '"etag-g4"', "uid": "g-jail-uid"},
        }
        # Mock check_membership to return "Feed" (the group the contact is already in)
        carddav.check_membership.return_value = "Feed"

    def test_error_label_applied(self, workflow, jmap):
        """@MailroomError applied to all triggering emails."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox"), ("email-2", "@ToImbox")],
        )
        # Error label should be applied via jmap.call
        email_set_calls = [
            c
            for c in jmap.call.call_args_list
            if any("Email/set" in mc[0] for mc in c.args[0])
        ]
        assert len(email_set_calls) >= 1

    def test_upsert_not_called(self, workflow, carddav):
        """upsert_contact NOT called when sender already in different group."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox")],
        )
        carddav.upsert_contact.assert_not_called()

    def test_sweep_not_called(self, workflow, jmap):
        """No sweep performed when sender already in different group."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox")],
        )
        jmap.batch_move_emails.assert_not_called()

    def test_triage_label_not_removed(self, workflow, jmap):
        """Triage label NOT removed (manual resolution needed)."""
        workflow._process_sender(
            "bob@example.com",
            [("email-1", "@ToImbox")],
        )
        jmap.remove_label.assert_not_called()


class TestAlreadyGroupedSameGroup:
    """Sender already in 'Imbox' group, triaged to @ToImbox again: processes normally (idempotent)."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = [
            {
                "href": "/contact-789.vcf",
                "etag": '"etag-789"',
                "vcard_data": _make_vcard("alice@example.com", "contact-uid-789"),
            }
        ]
        # check_membership returns None (same group = safe)
        carddav.check_membership.return_value = None
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "contact-uid-789",
            "group": "Imbox",
        }

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "alice@example.com":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_upsert_called(self, workflow, carddav):
        """upsert_contact still called (idempotent add to same group)."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        carddav.upsert_contact.assert_called_once()

    def test_sweep_called(self, workflow, jmap):
        """Sweep still performed."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.batch_move_emails.assert_called_once()

    def test_triage_label_removed(self, workflow, jmap):
        """Triage label removed normally."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.remove_label.assert_called_once()


class TestAlreadyGroupedNewSender:
    """New sender (not in contacts): check_membership returns None, processing continues."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.check_membership.return_value = None
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "brand-new-uid",
            "group": "Imbox",
        }

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "newbie@example.com":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect

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


class TestJMAPFailureDuringSweep:
    """JMAP failure during sweep: exception propagates, triage label NOT removed."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "sweep-fail-uid",
            "group": "Imbox",
        }

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "alice@example.com":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect
        jmap.batch_move_emails.side_effect = RuntimeError("JMAP batch move failed")

    def test_exception_propagates(self, workflow):
        with pytest.raises(RuntimeError, match="JMAP batch move failed"):
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
        }

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "alice@example.com":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect
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

    def test_emails_were_swept(self, workflow, jmap):
        """Sweep succeeded before remove_label failed."""
        with pytest.raises(RuntimeError):
            workflow._process_sender(
                "alice@example.com", [("email-1", "@ToImbox")]
            )
        jmap.batch_move_emails.assert_called_once()


class TestProcessSenderEmptySweep:
    """Sweep query returns no emails (all already moved): batch_move not called."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "existing",
            "uid": "empty-sweep-uid",
            "group": "Imbox",
        }

        def query_side_effect(mailbox_id, **kwargs):
            # Sweep returns empty -- all emails already moved
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_batch_move_not_called(self, workflow, jmap):
        """batch_move_emails skipped when sweep finds nothing."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.batch_move_emails.assert_not_called()

    def test_triage_label_still_removed(self, workflow, jmap):
        """Triage label removal still happens even if sweep is empty."""
        workflow._process_sender(
            "alice@example.com", [("email-1", "@ToImbox")]
        )
        jmap.remove_label.assert_called_once_with("email-1", "mb-toimbox")


class TestProcessSenderIntegrationWithPoll:
    """End-to-end: poll() calls _process_sender which now works (not a stub)."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap, carddav):
        # Poll: one sender with one email in @ToImbox
        def poll_query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if sender is not None:
                # This is a sweep query from _process_sender
                if mailbox_id == "mb-screener" and sender == "alice@example.com":
                    return ["email-1"]
                return []
            # This is a poll collection query
            if mailbox_id == "mb-toimbox":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = poll_query_side_effect
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice Smith")}
        # Email/get for error filtering
        jmap.call.return_value = [
            ["Email/get", {"list": [{"id": "email-1", "mailboxIds": {"mb-toimbox": True}}]}, "g0"]
        ]

        carddav.search_by_email.return_value = []
        carddav.upsert_contact.return_value = {
            "action": "created",
            "uid": "poll-uid",
            "group": "Imbox",
        }

    def test_poll_returns_one_processed(self, workflow):
        """poll() now returns 1 (sender processed successfully)."""
        result = workflow.poll()
        assert result == 1

    def test_poll_calls_upsert(self, workflow, carddav):
        workflow.poll()
        carddav.upsert_contact.assert_called_once()

    def test_poll_calls_sweep(self, workflow, jmap):
        workflow.poll()
        jmap.batch_move_emails.assert_called_once()

    def test_poll_passes_display_name_to_upsert(self, workflow, carddav):
        """poll() propagates sender display name from JMAP to upsert_contact."""
        workflow.poll()
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice Smith", "Imbox"
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
        }

        def query_side_effect(mailbox_id, **kwargs):
            sender = kwargs.get("sender")
            if mailbox_id == "mb-screener" and sender == "alice@example.com":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect

    def test_display_name_passed_to_upsert(self, workflow, carddav):
        """_process_sender passes the sender's display name from sender_names to upsert_contact."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": "Alice Smith"},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", "Alice Smith", "Imbox"
        )

    def test_display_name_none_when_missing(self, workflow, carddav):
        """None is passed when no name available in sender_names."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {"alice@example.com": None},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", None, "Imbox"
        )

    def test_display_name_none_when_sender_not_in_names(self, workflow, carddav):
        """None passed when sender_names is empty dict (backward compatible)."""
        workflow._process_sender(
            "alice@example.com",
            [("email-1", "@ToImbox")],
            {},
        )
        carddav.upsert_contact.assert_called_once_with(
            "alice@example.com", None, "Imbox"
        )


class TestCollectTriagedReturnsSenderNames:
    """_collect_triaged returns sender_names dict alongside triaged emails."""

    @pytest.fixture(autouse=True)
    def setup(self, jmap):
        def query_side_effect(mailbox_id, **kwargs):
            if mailbox_id == "mb-toimbox":
                return ["email-1"]
            return []

        jmap.query_emails.side_effect = query_side_effect
        jmap.get_email_senders.return_value = {"email-1": ("alice@example.com", "Alice Smith")}
        jmap.call.return_value = [
            ["Email/get", {"list": [{"id": "email-1", "mailboxIds": {"mb-toimbox": True}}]}, "g0"]
        ]

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

    def test_empty_returns_empty_tuple(self, workflow, jmap):
        """When no emails found, returns ({}, {})."""
        jmap.query_emails.side_effect = lambda *a, **kw: []
        result = workflow._collect_triaged()
        assert result == ({}, {})


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
