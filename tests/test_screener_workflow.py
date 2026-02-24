"""TDD tests for ScreenerWorkflow poll cycle, conflict detection, and error labeling."""

from unittest.mock import MagicMock, call

import pytest

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
        # Should query each of the 4 triage labels
        assert jmap.query_emails.call_count == 4
        queried_ids = [c.args[0] for c in jmap.query_emails.call_args_list]
        assert "mb-toimbox" in queried_ids
        assert "mb-tofeed" in queried_ids
        assert "mb-topapertrl" in queried_ids
        assert "mb-tojail" in queried_ids

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
        jmap.get_email_senders.return_value = {"email-1": "alice@example.com"}
        # Email/get: email-1 does NOT have error label
        jmap.call.return_value = [
            ["Email/get", {"list": [{"id": "email-1", "mailboxIds": {"mb-toimbox": True}}]}, "g0"]
        ]

    def test_process_sender_called(self, workflow, jmap):
        """_process_sender is called for clean senders (it will raise NotImplementedError)."""
        with pytest.raises(NotImplementedError):
            workflow.poll()

    def test_error_label_not_applied(self, workflow, jmap):
        """No error label applied for non-conflicted sender."""
        with pytest.raises(NotImplementedError):
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
                result[eid] = "bob@example.com"
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
            "email-1": "alice@example.com",
            "email-2": "carol@example.com",
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
        """Both senders get _process_sender called (raises NotImplementedError)."""
        with pytest.raises(NotImplementedError):
            workflow.poll()


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
                "email-1": "alice@example.com",
                "email-2": "bob@example.com",
                "email-3": "bob@example.com",
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

    def test_clean_sender_processed(self, workflow):
        """Alice (clean) gets _process_sender called."""
        with pytest.raises(NotImplementedError):
            workflow.poll()

    def test_conflicted_sender_gets_error_label(self, workflow, jmap):
        """Bob (conflicted) gets @MailroomError but not _process_sender."""
        with pytest.raises(NotImplementedError):
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
        jmap.get_email_senders.return_value = {"email-1": "alice@example.com"}
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
        jmap.get_email_senders.return_value = {"email-2": "alice@example.com"}
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
        """alice@example.com is still processed even though email-1 has no sender."""
        with pytest.raises(NotImplementedError):
            workflow.poll()


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
            return {eid: "bob@example.com" for eid in email_ids}

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
        jmap.get_email_senders.return_value = {"email-1": "alice@example.com"}
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
            "email-1": "alice@example.com",
            "email-2": "bob@example.com",
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
        result = workflow._collect_triaged()
        # alice's email-1 should be filtered out (has error label)
        # bob's email-2 should remain
        assert "bob@example.com" in result
        assert "alice@example.com" not in result
