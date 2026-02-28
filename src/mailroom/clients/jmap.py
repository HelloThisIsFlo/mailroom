"""JMAP client for Fastmail: session, mailbox resolution, and email operations."""

from __future__ import annotations

import httpx

BATCH_SIZE = 100  # Max emails per Email/set call (conservative under Fastmail's 500 minimum)


class JMAPClient:
    """Thin JMAP client over httpx for Fastmail operations.

    Usage:
        client = JMAPClient(token="fmu1-...")
        client.connect()  # discovers session (account_id, api_url)
        mailboxes = client.resolve_mailboxes(["Inbox", "Screener", "@ToImbox"])
    """

    def __init__(self, token: str, hostname: str = "api.fastmail.com") -> None:
        self._token = token
        self._hostname = hostname
        self._http = httpx.Client(
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        self._api_url: str | None = None
        self._account_id: str | None = None
        self._download_url: str | None = None
        self._event_source_url: str | None = None

    @property
    def account_id(self) -> str:
        """Return the primary mail account ID. Raises if not connected."""
        if self._account_id is None:
            raise RuntimeError("JMAPClient is not connected. Call connect() first.")
        return self._account_id

    @property
    def event_source_url(self) -> str | None:
        """Return the EventSource URL from the JMAP session, or None."""
        return self._event_source_url

    def connect(self) -> None:
        """Discover JMAP session: fetch account ID and API URL from Fastmail.

        Raises:
            httpx.HTTPStatusError: On 401 (bad token) or other HTTP errors.
            httpx.ConnectError: On network failure.
        """
        resp = self._http.get(f"https://{self._hostname}/jmap/session")
        resp.raise_for_status()
        data = resp.json()
        self._account_id = data["primaryAccounts"]["urn:ietf:params:jmap:mail"]
        self._api_url = data["apiUrl"]
        self._download_url = data.get("downloadUrl")
        self._event_source_url = data.get("eventSourceUrl")

    def call(self, method_calls: list) -> list:
        """Execute JMAP method calls against the API endpoint.

        Args:
            method_calls: List of [method_name, args, call_id] triples.

        Returns:
            List of methodResponses from the JMAP server.

        Raises:
            RuntimeError: If connect() has not been called.
            httpx.HTTPStatusError: On HTTP errors from the API.
        """
        if self._api_url is None:
            raise RuntimeError("JMAPClient is not connected. Call connect() first.")

        payload = {
            "using": [
                "urn:ietf:params:jmap:core",
                "urn:ietf:params:jmap:mail",
            ],
            "methodCalls": method_calls,
        }
        resp = self._http.post(self._api_url, json=payload)
        resp.raise_for_status()
        return resp.json()["methodResponses"]

    def resolve_mailboxes(self, required_names: list[str]) -> dict[str, str]:
        """Resolve mailbox names to Fastmail mailbox IDs.

        Fetches all mailboxes via Mailbox/get and builds a name-to-ID map.
        Special handling:
        - "Inbox" is resolved by role="inbox" (not by name) to avoid
          parent/child name collisions.
        - Custom mailboxes prefer top-level (parentId is None) when
          duplicate names exist at different hierarchy levels.

        Args:
            required_names: List of mailbox names that must exist.

        Returns:
            Dict mapping each required name to its Fastmail mailbox ID.

        Raises:
            ValueError: If any required mailbox names are not found,
                listing all missing names.
        """
        responses = self.call(
            [["Mailbox/get", {"accountId": self.account_id, "ids": None}, "m0"]]
        )
        mailbox_list = responses[0][1]["list"]

        # Build lookup structures
        name_to_id: dict[str, str] = {}
        inbox_id: str | None = None

        for mb in mailbox_list:
            # Track the role-based Inbox
            if mb.get("role") == "inbox":
                inbox_id = mb["id"]

            name = mb["name"]
            parent_id = mb.get("parentId")

            # For custom mailboxes: prefer top-level (parentId=None)
            if name not in name_to_id:
                # First occurrence -- always record it
                name_to_id[name] = mb["id"]
            elif parent_id is None:
                # This is a top-level duplicate -- prefer it over a child
                name_to_id[name] = mb["id"]

        # Build result map with special Inbox handling
        result: dict[str, str] = {}
        missing: list[str] = []

        for name in required_names:
            if name == "Inbox":
                if inbox_id is not None:
                    result["Inbox"] = inbox_id
                else:
                    missing.append("Inbox")
            elif name in name_to_id:
                result[name] = name_to_id[name]
            else:
                missing.append(name)

        if missing:
            raise ValueError(
                f"Required mailboxes not found in Fastmail: {', '.join(missing)}"
            )

        return result

    def create_mailbox(self, name: str, parent_id: str | None = None) -> str:
        """Create a mailbox and return its server-assigned ID.

        Args:
            name: Mailbox display name (e.g., "Feed", not "Triage/Feed").
            parent_id: Parent mailbox ID for nested mailboxes, or None for top-level.

        Returns:
            Server-assigned mailbox ID string.

        Raises:
            RuntimeError: If Mailbox/set reports creation failed, with error type and description.
        """
        create_args: dict = {
            "name": name,
            "isSubscribed": True,
        }
        if parent_id is not None:
            create_args["parentId"] = parent_id

        responses = self.call(
            [["Mailbox/set", {
                "accountId": self.account_id,
                "create": {"mb0": create_args},
            }, "c0"]]
        )
        data = responses[0][1]
        created = data.get("created", {})
        if "mb0" in created:
            return created["mb0"]["id"]
        not_created = data.get("notCreated", {})
        error = not_created.get("mb0", {})
        raise RuntimeError(
            f"Failed to create mailbox '{name}': "
            f"{error.get('type', 'unknown')} - {error.get('description', '')}"
        )

    def query_emails(
        self,
        mailbox_id: str,
        sender: str | None = None,
        limit: int = 100,
    ) -> list[str]:
        """Query email IDs in a mailbox, optionally filtered by sender.

        Handles pagination automatically when total exceeds the page size.

        Args:
            mailbox_id: The JMAP mailbox ID to query.
            sender: Optional sender email address to filter by.
            limit: Maximum emails per page (used for pagination).

        Returns:
            List of email ID strings.
        """
        email_filter: dict = {"inMailbox": mailbox_id}
        if sender is not None:
            email_filter["from"] = sender

        all_ids: list[str] = []
        position = 0

        while True:
            responses = self.call(
                [
                    [
                        "Email/query",
                        {
                            "accountId": self.account_id,
                            "filter": email_filter,
                            "limit": limit,
                            "position": position,
                        },
                        "q0",
                    ]
                ]
            )
            data = responses[0][1]
            ids = data["ids"]
            total = data["total"]
            all_ids.extend(ids)

            if len(all_ids) >= total:
                break
            position = len(all_ids)

        return all_ids

    def get_email_senders(
        self, email_ids: list[str]
    ) -> dict[str, tuple[str, str | None]]:
        """Get sender email address and display name for each email ID.

        Uses Email/get with properties=["id", "from"] and extracts
        the first from[].email and from[].name values.

        Args:
            email_ids: List of email IDs to look up.

        Returns:
            Dict mapping email_id to (sender_email, display_name) tuple.
            display_name is None when the From header has no name,
            an empty name, or a whitespace-only name.
        """
        responses = self.call(
            [
                [
                    "Email/get",
                    {
                        "accountId": self.account_id,
                        "ids": email_ids,
                        "properties": ["id", "from"],
                    },
                    "g0",
                ]
            ]
        )
        email_list = responses[0][1]["list"]

        result: dict[str, tuple[str, str | None]] = {}
        for email in email_list:
            from_list = email.get("from", [])
            if from_list:
                sender_email = from_list[0]["email"]
                name = from_list[0].get("name") or None
                if name and not name.strip():
                    name = None
                result[email["id"]] = (sender_email, name)

        return result

    def remove_label(self, email_id: str, mailbox_id: str) -> None:
        """Remove a single mailbox label from an email.

        Uses JMAP patch syntax to remove only the specified label
        without affecting other mailbox assignments.

        Args:
            email_id: The email to modify.
            mailbox_id: The mailbox label to remove.

        Raises:
            RuntimeError: If Email/set reports the update failed.
        """
        responses = self.call(
            [
                [
                    "Email/set",
                    {
                        "accountId": self.account_id,
                        "update": {
                            email_id: {f"mailboxIds/{mailbox_id}": None},
                        },
                    },
                    "s0",
                ]
            ]
        )
        data = responses[0][1]
        not_updated = data.get("notUpdated")
        if not_updated:
            errors = [
                f"{eid}: {err.get('description', 'unknown error')}"
                for eid, err in not_updated.items()
            ]
            raise RuntimeError(
                f"Failed to remove label from emails: {', '.join(errors)}"
            )

    def batch_move_emails(
        self,
        email_ids: list[str],
        remove_mailbox_id: str,
        add_mailbox_ids: list[str],
    ) -> None:
        """Batch-move emails: remove source label, add destination label(s).

        Builds JMAP patch syntax for each email and processes in chunks
        of BATCH_SIZE to stay under Fastmail's maxObjectsInSet limit.

        The caller includes inbox_id in add_mailbox_ids when the
        destination is Imbox (JMAP-08 special case).

        Args:
            email_ids: List of email IDs to move.
            remove_mailbox_id: Mailbox label to remove from each email.
            add_mailbox_ids: Mailbox labels to add to each email.

        Raises:
            RuntimeError: If any emails fail to update, with failed IDs listed.
        """
        for chunk_start in range(0, len(email_ids), BATCH_SIZE):
            chunk = email_ids[chunk_start : chunk_start + BATCH_SIZE]

            update: dict = {}
            for email_id in chunk:
                patch: dict = {f"mailboxIds/{remove_mailbox_id}": None}
                for add_id in add_mailbox_ids:
                    patch[f"mailboxIds/{add_id}"] = True
                update[email_id] = patch

            responses = self.call(
                [
                    [
                        "Email/set",
                        {
                            "accountId": self.account_id,
                            "update": update,
                        },
                        "s0",
                    ]
                ]
            )
            data = responses[0][1]
            not_updated = data.get("notUpdated")
            if not_updated:
                errors = [
                    f"{eid}: {err.get('description', 'unknown error')}"
                    for eid, err in not_updated.items()
                ]
                raise RuntimeError(
                    f"Failed to move emails: {', '.join(errors)}"
                )
