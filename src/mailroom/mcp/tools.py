"""MCP tool definitions for interactive email access.

Tools operate on JMAPClient directly — no workflow dependency.
All tools are sync (JMAPClient uses httpx.Client, stdio is serial).
"""

from fastmcp import Context, FastMCP


def register_tools(mcp: FastMCP) -> None:
    """Register all email tools on the given FastMCP instance."""

    @mcp.tool
    def list_mailboxes(ctx: Context) -> list[dict]:
        """List all Fastmail mailboxes with their IDs, names, and roles."""
        jmap = ctx.lifespan_context["jmap"]
        return jmap.list_all_mailboxes()

    @mcp.tool
    def search_emails(
        ctx: Context,
        mailbox_id: str | None = None,
        sender: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        """Search for emails by mailbox and/or sender. Returns email IDs.

        - mailbox_id + sender: emails from sender in that mailbox
        - mailbox_id only: all emails in that mailbox
        - sender only: emails from sender across all mailboxes
        - neither: most recent emails across all mailboxes
        """
        jmap = ctx.lifespan_context["jmap"]
        if mailbox_id is not None:
            return jmap.query_emails(mailbox_id, sender=sender, limit=limit)
        if sender is not None:
            return jmap.query_emails_by_sender(sender, limit=limit)
        return jmap.query_recent_emails(limit=limit)

    @mcp.tool
    def get_email_headers(ctx: Context, email_ids: list[str]) -> list[dict]:
        """Get header summary (subject, sender, date, preview) for a list of email IDs."""
        jmap = ctx.lifespan_context["jmap"]
        return jmap.get_email_headers(email_ids)

    @mcp.tool
    def read_email(ctx: Context, email_id: str) -> dict:
        """Read the full content of an email by ID, including body text."""
        jmap = ctx.lifespan_context["jmap"]
        return jmap.get_email(email_id)

    @mcp.tool
    def add_labels(ctx: Context, email_ids: list[str], mailbox_ids: list[str]) -> str:
        """Add mailbox labels to emails. Use list_mailboxes to find mailbox IDs."""
        jmap = ctx.lifespan_context["jmap"]
        jmap.batch_add_labels(email_ids, mailbox_ids)
        return f"Added {len(mailbox_ids)} label(s) to {len(email_ids)} email(s)."

    @mcp.tool
    def remove_labels(ctx: Context, email_ids: list[str], mailbox_ids: list[str]) -> str:
        """Remove mailbox labels from emails."""
        jmap = ctx.lifespan_context["jmap"]
        jmap.batch_remove_labels(email_ids, mailbox_ids)
        return f"Removed {len(mailbox_ids)} label(s) from {len(email_ids)} email(s)."

    @mcp.tool
    def move_email(
        ctx: Context,
        email_ids: list[str],
        from_mailbox_id: str,
        to_mailbox_id: str,
    ) -> str:
        """Move emails from one mailbox to another (add destination, then remove source)."""
        jmap = ctx.lifespan_context["jmap"]
        jmap.batch_add_labels(email_ids, [to_mailbox_id])
        jmap.batch_remove_labels(email_ids, [from_mailbox_id])
        return f"Moved {len(email_ids)} email(s) from {from_mailbox_id} to {to_mailbox_id}."
