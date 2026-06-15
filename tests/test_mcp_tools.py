"""Tests for MCP tool definitions: verify correct JMAPClient dispatch."""

import asyncio
from unittest.mock import MagicMock

import pytest
from fastmcp import FastMCP

from mailroom.mcp.tools import register_tools


def _get_tool_fn(app: FastMCP, name: str):
    """Get the raw function behind a registered FastMCP tool."""
    tool = asyncio.run(app.get_tool(name))
    return tool.fn


@pytest.fixture
def app() -> FastMCP:
    """Create a FastMCP app with all tools registered."""
    app = FastMCP("test")
    register_tools(app)
    return app


@pytest.fixture
def jmap() -> MagicMock:
    return MagicMock()


@pytest.fixture
def ctx(jmap: MagicMock) -> MagicMock:
    """Create a mock FastMCP Context with a JMAPClient on lifespan_context."""
    ctx = MagicMock()
    ctx.lifespan_context = {"jmap": jmap, "settings": MagicMock()}
    return ctx


class TestToolRegistration:
    def test_all_tools_registered(self, app: FastMCP) -> None:
        """All 7 email tools are registered on the MCP app."""
        tools = asyncio.run(app.list_tools())
        tool_names = {t.name for t in tools}
        assert tool_names == {
            "list_mailboxes",
            "search_emails",
            "get_email_headers",
            "read_email",
            "add_labels",
            "remove_labels",
            "move_email",
        }


class TestListMailboxes:
    def test_delegates_to_jmap(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        fn = _get_tool_fn(app, "list_mailboxes")
        jmap.list_all_mailboxes.return_value = [{"id": "mb-1", "name": "Inbox", "role": "inbox"}]

        result = fn(ctx)

        jmap.list_all_mailboxes.assert_called_once()
        assert result == [{"id": "mb-1", "name": "Inbox", "role": "inbox"}]


class TestSearchEmails:
    def test_mailbox_and_sender(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        """Both params → query_emails(mailbox_id, sender=sender)."""
        fn = _get_tool_fn(app, "search_emails")
        jmap.query_emails.return_value = ["e1"]

        result = fn(ctx, mailbox_id="mb-1", sender="alice@example.com", limit=10)

        jmap.query_emails.assert_called_once_with("mb-1", sender="alice@example.com", limit=10)
        assert result == ["e1"]

    def test_mailbox_only(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        """mailbox_id only → query_emails(mailbox_id, sender=None)."""
        fn = _get_tool_fn(app, "search_emails")
        jmap.query_emails.return_value = ["e1", "e2"]

        result = fn(ctx, mailbox_id="mb-1")

        jmap.query_emails.assert_called_once_with("mb-1", sender=None, limit=50)
        assert result == ["e1", "e2"]

    def test_sender_only(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        """sender only → query_emails_by_sender(sender)."""
        fn = _get_tool_fn(app, "search_emails")
        jmap.query_emails_by_sender.return_value = ["e3"]

        result = fn(ctx, sender="bob@example.com", limit=25)

        jmap.query_emails_by_sender.assert_called_once_with("bob@example.com", limit=25)
        assert result == ["e3"]

    def test_neither_param(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        """No params → query_recent_emails(limit)."""
        fn = _get_tool_fn(app, "search_emails")
        jmap.query_recent_emails.return_value = ["e5", "e4"]

        result = fn(ctx)

        jmap.query_recent_emails.assert_called_once_with(limit=50)
        assert result == ["e5", "e4"]


class TestGetEmailHeaders:
    def test_delegates_to_jmap(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        fn = _get_tool_fn(app, "get_email_headers")
        headers = [{"id": "e1", "subject": "Hello"}]
        jmap.get_email_headers.return_value = headers

        result = fn(ctx, email_ids=["e1"])

        jmap.get_email_headers.assert_called_once_with(["e1"])
        assert result == headers


class TestReadEmail:
    def test_delegates_to_jmap(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        fn = _get_tool_fn(app, "read_email")
        email = {"id": "e1", "subject": "Hello", "bodyValues": {"1": {"value": "Hi"}}}
        jmap.get_email.return_value = email

        result = fn(ctx, email_id="e1")

        jmap.get_email.assert_called_once_with("e1")
        assert result == email


class TestAddLabels:
    def test_delegates_to_jmap(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        fn = _get_tool_fn(app, "add_labels")

        result = fn(ctx, email_ids=["e1", "e2"], mailbox_ids=["mb-1"])

        jmap.batch_add_labels.assert_called_once_with(["e1", "e2"], ["mb-1"])
        assert "2 email(s)" in result


class TestRemoveLabels:
    def test_delegates_to_jmap(self, app: FastMCP, ctx: MagicMock, jmap: MagicMock) -> None:
        fn = _get_tool_fn(app, "remove_labels")

        result = fn(ctx, email_ids=["e1"], mailbox_ids=["mb-1", "mb-2"])

        jmap.batch_remove_labels.assert_called_once_with(["e1"], ["mb-1", "mb-2"])
        assert "2 label(s)" in result


class TestMoveEmail:
    def test_adds_then_removes(self, app: FastMCP, ctx: MagicMock) -> None:
        """move_email adds destination label first, then removes source."""
        jmap = MagicMock()
        call_order = []
        jmap.batch_add_labels.side_effect = lambda *a: call_order.append("add")
        jmap.batch_remove_labels.side_effect = lambda *a: call_order.append("remove")
        ctx.lifespan_context = {"jmap": jmap, "settings": MagicMock()}

        fn = _get_tool_fn(app, "move_email")

        result = fn(ctx, email_ids=["e1"], from_mailbox_id="mb-src", to_mailbox_id="mb-dst")

        jmap.batch_add_labels.assert_called_once_with(["e1"], ["mb-dst"])
        jmap.batch_remove_labels.assert_called_once_with(["e1"], ["mb-src"])
        assert call_order == ["add", "remove"]
        assert "1 email(s)" in result
