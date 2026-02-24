"""Tests for JMAP client session discovery and mailbox resolution."""

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
