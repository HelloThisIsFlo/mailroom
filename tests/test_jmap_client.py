"""Tests for JMAP client: session discovery, mailbox resolution, and email operations."""

import httpx
import pytest
from pytest_httpx import HTTPXMock

from mailroom.clients.jmap import JMAPClient

# --- Fixtures ---

FASTMAIL_SESSION_RESPONSE = {
    "apiUrl": "https://api.fastmail.com/jmap/api/",
    "primaryAccounts": {
        "urn:ietf:params:jmap:core": "u1234",
        "urn:ietf:params:jmap:mail": "u1234",
    },
    "accounts": {
        "u1234": {"name": "user@fastmail.com"},
    },
    "capabilities": {},
}

MAILBOX_LIST = [
    {"id": "mb-inbox", "name": "Inbox", "role": "inbox", "parentId": None},
    {"id": "mb-drafts", "name": "Drafts", "role": "drafts", "parentId": None},
    {"id": "mb-screener", "name": "Screener", "role": None, "parentId": None},
    {"id": "mb-toimbox", "name": "@ToImbox", "role": None, "parentId": None},
    {"id": "mb-tofeed", "name": "@ToFeed", "role": None, "parentId": None},
    {"id": "mb-topaper", "name": "@ToPaperTrail", "role": None, "parentId": None},
    {"id": "mb-tojail", "name": "@ToJail", "role": None, "parentId": None},
    {"id": "mb-imbox", "name": "Imbox", "role": None, "parentId": None},
]


@pytest.fixture
def token() -> str:
    return "fmu1-test-token-abc123"


@pytest.fixture
def client(token: str) -> JMAPClient:
    return JMAPClient(token=token)


# --- Session Discovery Tests ---


class TestConnect:
    """Tests for JMAPClient.connect() session discovery."""

    def test_connect_success(self, client: JMAPClient, httpx_mock: HTTPXMock) -> None:
        """Valid token discovers session: account_id and api_url populated."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )

        client.connect()

        assert client.account_id == "u1234"

    def test_connect_stores_api_url(self, client: JMAPClient, httpx_mock: HTTPXMock) -> None:
        """connect() extracts apiUrl from session for subsequent JMAP calls."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )

        client.connect()

        # Verify the client uses the correct API URL for method calls
        # by making a call() and checking it goes to the right URL
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={"methodResponses": [["Mailbox/get", {"list": []}, "m0"]]},
        )
        client.call([["Mailbox/get", {"accountId": "u1234", "ids": None}, "m0"]])

    def test_connect_invalid_token(self, client: JMAPClient, httpx_mock: HTTPXMock) -> None:
        """Invalid token raises httpx.HTTPStatusError (401 from Fastmail)."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            status_code=401,
        )

        with pytest.raises(httpx.HTTPStatusError):
            client.connect()

    def test_connect_network_error(self, client: JMAPClient, httpx_mock: HTTPXMock) -> None:
        """Network failure during session discovery raises an exception."""
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://api.fastmail.com/jmap/session",
        )

        with pytest.raises(httpx.ConnectError):
            client.connect()

    def test_account_id_before_connect_raises(self, client: JMAPClient) -> None:
        """Accessing account_id before connect() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.account_id

    def test_connect_sends_bearer_auth(
        self, token: str, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """connect() sends Authorization: Bearer header with the token."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )

        client.connect()

        request = httpx_mock.get_request()
        assert request is not None
        assert request.headers["authorization"] == f"Bearer {token}"


# --- Mailbox Resolution Tests ---


class TestResolveMailboxes:
    """Tests for JMAPClient.resolve_mailboxes()."""

    def _setup_connected_client(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Helper: connect the client with a mocked session."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )
        client.connect()

    def test_resolve_all_found(self, client: JMAPClient, httpx_mock: HTTPXMock) -> None:
        """All required mailboxes resolved to their IDs."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    ["Mailbox/get", {"accountId": "u1234", "list": MAILBOX_LIST}, "m0"]
                ]
            },
        )

        result = client.resolve_mailboxes(["Screener", "@ToImbox", "Inbox"])

        assert result == {
            "Screener": "mb-screener",
            "@ToImbox": "mb-toimbox",
            "Inbox": "mb-inbox",
        }

    def test_resolve_inbox_by_role(self, client: JMAPClient, httpx_mock: HTTPXMock) -> None:
        """Inbox is resolved by role='inbox', not by name, to avoid parent/child collisions."""
        self._setup_connected_client(client, httpx_mock)

        # Include a child mailbox also named "Inbox" under a different parent
        mailboxes_with_duplicate_inbox = MAILBOX_LIST + [
            {"id": "mb-child-inbox", "name": "Inbox", "role": None, "parentId": "mb-some-parent"},
        ]
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Mailbox/get",
                        {"accountId": "u1234", "list": mailboxes_with_duplicate_inbox},
                        "m0",
                    ]
                ]
            },
        )

        result = client.resolve_mailboxes(["Inbox"])

        # Should pick the one with role="inbox", not the child
        assert result["Inbox"] == "mb-inbox"

    def test_resolve_missing_mailbox_raises(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Missing required mailbox raises ValueError listing the missing names."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    ["Mailbox/get", {"accountId": "u1234", "list": MAILBOX_LIST}, "m0"]
                ]
            },
        )

        with pytest.raises(ValueError, match="NonExistent"):
            client.resolve_mailboxes(["Screener", "NonExistent"])

    def test_resolve_prefers_top_level_for_custom_mailboxes(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """When duplicate custom mailbox names exist, prefer top-level (parentId=None)."""
        self._setup_connected_client(client, httpx_mock)

        mailboxes_with_duplicate = MAILBOX_LIST + [
            {
                "id": "mb-screener-child",
                "name": "Screener",
                "role": None,
                "parentId": "mb-some-parent",
            },
        ]
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Mailbox/get",
                        {"accountId": "u1234", "list": mailboxes_with_duplicate},
                        "m0",
                    ]
                ]
            },
        )

        result = client.resolve_mailboxes(["Screener"])

        # Should pick top-level (parentId=None) over child
        assert result["Screener"] == "mb-screener"

    def test_resolve_multiple_missing_lists_all(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """ValueError message lists all missing mailbox names, not just the first."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    ["Mailbox/get", {"accountId": "u1234", "list": MAILBOX_LIST}, "m0"]
                ]
            },
        )

        with pytest.raises(ValueError, match="Missing1") as exc_info:
            client.resolve_mailboxes(["Missing1", "Missing2"])

        assert "Missing2" in str(exc_info.value)


# --- JMAP call() Tests ---


class TestCall:
    """Tests for JMAPClient.call() method."""

    def test_call_returns_method_responses(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """call() sends JMAP request and returns methodResponses."""
        # Connect first
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )
        client.connect()

        expected_responses = [["Mailbox/get", {"accountId": "u1234", "list": []}, "m0"]]
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={"methodResponses": expected_responses},
        )

        result = client.call([["Mailbox/get", {"accountId": "u1234", "ids": None}, "m0"]])

        assert result == expected_responses

    def test_call_before_connect_raises(self, client: JMAPClient) -> None:
        """Calling call() before connect() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="not connected"):
            client.call([["Mailbox/get", {}, "m0"]])


# --- Email Query Tests ---


class TestQueryEmails:
    """Tests for JMAPClient.query_emails()."""

    def _setup_connected_client(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Helper: connect the client with a mocked session."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )
        client.connect()

    def test_query_emails_returns_ids(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Email/query returns list of email IDs for a mailbox."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/query",
                        {
                            "accountId": "u1234",
                            "ids": ["e1", "e2", "e3", "e4", "e5"],
                            "total": 5,
                            "position": 0,
                        },
                        "q0",
                    ]
                ]
            },
        )

        result = client.query_emails("mb-screener")

        assert result == ["e1", "e2", "e3", "e4", "e5"]

    def test_query_emails_empty_mailbox(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Empty mailbox returns empty list."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/query",
                        {
                            "accountId": "u1234",
                            "ids": [],
                            "total": 0,
                            "position": 0,
                        },
                        "q0",
                    ]
                ]
            },
        )

        result = client.query_emails("mb-screener")

        assert result == []

    def test_query_emails_paginates(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """When total > returned IDs, fetches additional pages."""
        self._setup_connected_client(client, httpx_mock)

        # Page 1: 100 IDs out of 150 total
        page1_ids = [f"e{i}" for i in range(100)]
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/query",
                        {
                            "accountId": "u1234",
                            "ids": page1_ids,
                            "total": 150,
                            "position": 0,
                        },
                        "q0",
                    ]
                ]
            },
        )

        # Page 2: remaining 50 IDs
        page2_ids = [f"e{i}" for i in range(100, 150)]
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/query",
                        {
                            "accountId": "u1234",
                            "ids": page2_ids,
                            "total": 150,
                            "position": 100,
                        },
                        "q0",
                    ]
                ]
            },
        )

        result = client.query_emails("mb-screener", limit=100)

        assert len(result) == 150
        assert result == page1_ids + page2_ids

    def test_query_emails_by_sender(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Email/query with sender filter returns matching IDs."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/query",
                        {
                            "accountId": "u1234",
                            "ids": ["e10", "e11", "e12"],
                            "total": 3,
                            "position": 0,
                        },
                        "q0",
                    ]
                ]
            },
        )

        result = client.query_emails("mb-screener", sender="alice@example.com")

        assert result == ["e10", "e11", "e12"]

        # Verify the request included the from filter
        requests = httpx_mock.get_requests()
        api_request = requests[-1]
        body = api_request.read()
        import json

        payload = json.loads(body)
        method_call = payload["methodCalls"][0]
        assert method_call[0] == "Email/query"
        assert method_call[1]["filter"]["from"] == "alice@example.com"
        assert method_call[1]["filter"]["inMailbox"] == "mb-screener"

    def test_query_emails_sender_empty_result(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Sender with no emails in mailbox returns empty list."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/query",
                        {
                            "accountId": "u1234",
                            "ids": [],
                            "total": 0,
                            "position": 0,
                        },
                        "q0",
                    ]
                ]
            },
        )

        result = client.query_emails("mb-screener", sender="nobody@example.com")

        assert result == []


# --- Sender Extraction Tests ---


class TestGetEmailSenders:
    """Tests for JMAPClient.get_email_senders()."""

    def _setup_connected_client(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Helper: connect the client with a mocked session."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )
        client.connect()

    def test_get_senders_single_email(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Extract sender email address from a single email."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/get",
                        {
                            "accountId": "u1234",
                            "list": [
                                {
                                    "id": "e1",
                                    "from": [
                                        {
                                            "name": "Alice Smith",
                                            "email": "alice@example.com",
                                        }
                                    ],
                                }
                            ],
                        },
                        "g0",
                    ]
                ]
            },
        )

        result = client.get_email_senders(["e1"])

        assert result == {"e1": "alice@example.com"}

    def test_get_senders_multiple_emails(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Extract sender addresses from multiple emails, same sender."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/get",
                        {
                            "accountId": "u1234",
                            "list": [
                                {
                                    "id": "e1",
                                    "from": [
                                        {
                                            "name": "Alice",
                                            "email": "alice@example.com",
                                        }
                                    ],
                                },
                                {
                                    "id": "e2",
                                    "from": [
                                        {
                                            "name": "Alice",
                                            "email": "alice@example.com",
                                        }
                                    ],
                                },
                            ],
                        },
                        "g0",
                    ]
                ]
            },
        )

        result = client.get_email_senders(["e1", "e2"])

        assert result == {"e1": "alice@example.com", "e2": "alice@example.com"}

    def test_get_senders_extracts_email_from_display_name(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Extracts the email field, not the display name."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/get",
                        {
                            "accountId": "u1234",
                            "list": [
                                {
                                    "id": "e1",
                                    "from": [
                                        {
                                            "name": "Alice <alice@example.com>",
                                            "email": "alice@example.com",
                                        }
                                    ],
                                }
                            ],
                        },
                        "g0",
                    ]
                ]
            },
        )

        result = client.get_email_senders(["e1"])

        assert result == {"e1": "alice@example.com"}


# --- Remove Label Tests ---


class TestRemoveLabel:
    """Tests for JMAPClient.remove_label()."""

    def _setup_connected_client(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Helper: connect the client with a mocked session."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )
        client.connect()

    def test_remove_label_success(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Remove label builds correct patch and succeeds."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/set",
                        {
                            "accountId": "u1234",
                            "updated": {"e1": None},
                        },
                        "s0",
                    ]
                ]
            },
        )

        # Should not raise
        client.remove_label("e1", "mb-toimbox")

        # Verify the correct patch syntax was sent
        requests = httpx_mock.get_requests()
        api_request = requests[-1]
        import json

        payload = json.loads(api_request.read())
        method_call = payload["methodCalls"][0]
        assert method_call[0] == "Email/set"
        update = method_call[1]["update"]
        assert update["e1"] == {"mailboxIds/mb-toimbox": None}

    def test_remove_label_error_raises(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Email/set error raises RuntimeError with descriptive message."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/set",
                        {
                            "accountId": "u1234",
                            "notUpdated": {
                                "e1": {
                                    "type": "invalidPatch",
                                    "description": "Cannot remove last mailbox",
                                }
                            },
                        },
                        "s0",
                    ]
                ]
            },
        )

        with pytest.raises(RuntimeError, match="e1"):
            client.remove_label("e1", "mb-toimbox")


# --- Batch Move Tests ---


class TestBatchMoveEmails:
    """Tests for JMAPClient.batch_move_emails()."""

    def _setup_connected_client(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Helper: connect the client with a mocked session."""
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/session",
            json=FASTMAIL_SESSION_RESPONSE,
        )
        client.connect()

    def test_batch_move_basic(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Batch move builds correct patch: remove source, add destination."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/set",
                        {
                            "accountId": "u1234",
                            "updated": {"e1": None, "e2": None, "e3": None},
                        },
                        "s0",
                    ]
                ]
            },
        )

        client.batch_move_emails(
            ["e1", "e2", "e3"],
            remove_mailbox_id="mb-screener",
            add_mailbox_ids=["mb-tofeed"],
        )

        # Verify patch syntax
        requests = httpx_mock.get_requests()
        api_request = requests[-1]
        import json

        payload = json.loads(api_request.read())
        method_call = payload["methodCalls"][0]
        assert method_call[0] == "Email/set"
        update = method_call[1]["update"]

        for email_id in ["e1", "e2", "e3"]:
            assert update[email_id] == {
                "mailboxIds/mb-screener": None,
                "mailboxIds/mb-tofeed": True,
            }

    def test_batch_move_with_inbox_label(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """When destination is Imbox, inbox_id in add_mailbox_ids adds Inbox label."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/set",
                        {
                            "accountId": "u1234",
                            "updated": {"e1": None, "e2": None},
                        },
                        "s0",
                    ]
                ]
            },
        )

        # Caller passes both imbox_id and inbox_id
        client.batch_move_emails(
            ["e1", "e2"],
            remove_mailbox_id="mb-screener",
            add_mailbox_ids=["mb-imbox", "mb-inbox"],
        )

        # Verify patch includes both Imbox and Inbox labels
        requests = httpx_mock.get_requests()
        api_request = requests[-1]
        import json

        payload = json.loads(api_request.read())
        method_call = payload["methodCalls"][0]
        update = method_call[1]["update"]

        for email_id in ["e1", "e2"]:
            assert update[email_id] == {
                "mailboxIds/mb-screener": None,
                "mailboxIds/mb-imbox": True,
                "mailboxIds/mb-inbox": True,
            }

    def test_batch_move_chunks_large_lists(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Lists > 100 emails are chunked into multiple Email/set calls."""
        self._setup_connected_client(client, httpx_mock)

        # 150 emails -> should make 2 calls (100 + 50)
        email_ids = [f"e{i}" for i in range(150)]

        # Response for chunk 1 (100 emails)
        chunk1_updated = {eid: None for eid in email_ids[:100]}
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/set",
                        {"accountId": "u1234", "updated": chunk1_updated},
                        "s0",
                    ]
                ]
            },
        )

        # Response for chunk 2 (50 emails)
        chunk2_updated = {eid: None for eid in email_ids[100:]}
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/set",
                        {"accountId": "u1234", "updated": chunk2_updated},
                        "s0",
                    ]
                ]
            },
        )

        client.batch_move_emails(
            email_ids,
            remove_mailbox_id="mb-screener",
            add_mailbox_ids=["mb-tofeed"],
        )

        # Verify 2 API calls were made (session + 2 batch calls)
        api_requests = [
            r
            for r in httpx_mock.get_requests()
            if str(r.url) == "https://api.fastmail.com/jmap/api/"
        ]
        assert len(api_requests) == 2

    def test_batch_move_partial_failure_raises(
        self, client: JMAPClient, httpx_mock: HTTPXMock
    ) -> None:
        """Partial failure in Email/set raises RuntimeError with failed IDs."""
        self._setup_connected_client(client, httpx_mock)
        httpx_mock.add_response(
            url="https://api.fastmail.com/jmap/api/",
            json={
                "methodResponses": [
                    [
                        "Email/set",
                        {
                            "accountId": "u1234",
                            "updated": {"e1": None},
                            "notUpdated": {
                                "e2": {
                                    "type": "notFound",
                                    "description": "Email not found",
                                }
                            },
                        },
                        "s0",
                    ]
                ]
            },
        )

        with pytest.raises(RuntimeError, match="e2"):
            client.batch_move_emails(
                ["e1", "e2"],
                remove_mailbox_id="mb-screener",
                add_mailbox_ids=["mb-tofeed"],
            )
