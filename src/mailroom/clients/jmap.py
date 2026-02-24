"""JMAP client for Fastmail session discovery, method calls, and mailbox resolution."""

from __future__ import annotations

import httpx


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

    @property
    def account_id(self) -> str:
        """Return the primary mail account ID. Raises if not connected."""
        if self._account_id is None:
            raise RuntimeError("JMAPClient is not connected. Call connect() first.")
        return self._account_id

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
