"""Tests for CardDAV client: discovery, connection, groups, and contact ops."""

import uuid

import httpx
import pytest
import vobject
from pytest_httpx import HTTPXMock

from mailroom.clients.carddav import CardDAVClient

# --- XML Response Fixtures ---

PROPFIND_PRINCIPAL_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/</D:href>
    <D:propstat>
      <D:prop>
        <D:current-user-principal>
          <D:href>/dav/principals/user/user@fastmail.com/</D:href>
        </D:current-user-principal>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

PROPFIND_HOME_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:response>
    <D:href>/dav/principals/user/user@fastmail.com/</D:href>
    <D:propstat>
      <D:prop>
        <C:addressbook-home-set>
          <D:href>/dav/addressbooks/user/user@fastmail.com/</D:href>
        </C:addressbook-home-set>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

PROPFIND_ADDRESSBOOKS_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:response>
    <D:href>/dav/addressbooks/user/user@fastmail.com/</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype><D:collection/></D:resourcetype>
        <D:displayname>Address Books</D:displayname>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
  <D:response>
    <D:href>/dav/addressbooks/user/user@fastmail.com/Default/</D:href>
    <D:propstat>
      <D:prop>
        <D:resourcetype><D:collection/><C:addressbook/></D:resourcetype>
        <D:displayname>Default</D:displayname>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""


# --- Fixtures ---


@pytest.fixture
def client() -> CardDAVClient:
    return CardDAVClient(username="user@fastmail.com", password="app-password-123")


def _mock_discovery(httpx_mock: HTTPXMock) -> None:
    """Helper: mock the 3-step PROPFIND discovery chain."""
    httpx_mock.add_response(
        url="https://carddav.fastmail.com/",
        status_code=207,
        content=PROPFIND_PRINCIPAL_RESPONSE,
    )
    httpx_mock.add_response(
        url="https://carddav.fastmail.com/dav/principals/user/user@fastmail.com/",
        status_code=207,
        content=PROPFIND_HOME_RESPONSE,
    )
    httpx_mock.add_response(
        url="https://carddav.fastmail.com/dav/addressbooks/user/user@fastmail.com/",
        status_code=207,
        content=PROPFIND_ADDRESSBOOKS_RESPONSE,
    )


# --- Connection Discovery Tests ---


class TestConnect:
    """Tests for CardDAVClient.connect() PROPFIND discovery."""

    def test_connect_discovers_addressbook(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """3-step PROPFIND chain discovers the default addressbook URL."""
        _mock_discovery(httpx_mock)

        client.connect()

        assert client._addressbook_url is not None
        assert "Default" in client._addressbook_url

    def test_connect_auth_failure(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """401 on the first PROPFIND raises HTTPStatusError."""
        httpx_mock.add_response(
            url="https://carddav.fastmail.com/",
            status_code=401,
        )

        with pytest.raises(httpx.HTTPStatusError):
            client.connect()

    def test_connect_sets_addressbook_url(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """After connect, addressbook URL matches the parsed PROPFIND response."""
        _mock_discovery(httpx_mock)

        client.connect()

        assert (
            client._addressbook_url
            == "https://carddav.fastmail.com/dav/addressbooks/user/user@fastmail.com/Default/"
        )

    def test_not_connected_guard(self, client: CardDAVClient) -> None:
        """Before connect(), accessing operations raises RuntimeError."""
        with pytest.raises(RuntimeError, match="not connected"):
            client.validate_groups(["Imbox"])


# --- vCard Fixtures for Group Validation ---


def _group_vcard(
    fn: str, uid: str, members: list[str] | None = None
) -> str:
    """Build an Apple-style group vCard string.

    Args:
        fn: Group display name.
        uid: Group UID.
        members: Optional list of member contact UIDs.
    """
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"UID:{uid}",
        f"FN:{fn}",
        f"N:{fn};;;;",
        "X-ADDRESSBOOKSERVER-KIND:group",
    ]
    for member_uid in members or []:
        lines.append(
            f"X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:{member_uid}"
        )
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def _contact_vcard(
    fn: str,
    uid: str,
    email: str,
    *,
    note: str | None = None,
    extra_emails: list[str] | None = None,
) -> str:
    """Build a regular contact vCard string (not a group)."""
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"UID:{uid}",
        f"FN:{fn}",
        f"N:{fn};;;;",
        f"EMAIL;TYPE=INTERNET:{email}",
    ]
    for extra in extra_emails or []:
        lines.append(f"EMAIL;TYPE=INTERNET:{extra}")
    if note:
        lines.append(f"NOTE:{note}")
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def _build_report_response(items: list[tuple[str, str, str]]) -> bytes:
    """Build a 207 Multi-Status REPORT response.

    Args:
        items: List of (href, etag, vcard_data) tuples.

    Returns:
        XML bytes for a 207 response.
    """
    responses = ""
    for href, etag, vcard_data in items:
        # Escape XML special characters in vCard data
        safe_vcard = vcard_data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        responses += f"""
  <D:response>
    <D:href>{href}</D:href>
    <D:propstat>
      <D:prop>
        <D:getetag>"{etag}"</D:getetag>
        <C:address-data>{safe_vcard}</C:address-data>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
{responses}
</D:multistatus>""".encode()


def _connect_client(client: CardDAVClient, httpx_mock: HTTPXMock) -> None:
    """Helper: run the discovery chain to connect the client."""
    _mock_discovery(httpx_mock)
    client.connect()


# --- Group Validation Tests ---


class TestValidateGroups:
    """Tests for CardDAVClient.validate_groups()."""

    def test_validate_groups_finds_all_groups(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """validate_groups returns href/etag/uid map for all found groups."""
        _connect_client(client, httpx_mock)

        report_body = _build_report_response([
            (
                "/dav/ab/Default/group-imbox.vcf",
                "etag-imbox",
                _group_vcard("Imbox", "uid-imbox"),
            ),
            (
                "/dav/ab/Default/group-feed.vcf",
                "etag-feed",
                _group_vcard("Feed", "uid-feed"),
            ),
            (
                "/dav/ab/Default/group-paper.vcf",
                "etag-paper",
                _group_vcard("Paper Trail", "uid-paper"),
            ),
            (
                "/dav/ab/Default/group-jail.vcf",
                "etag-jail",
                _group_vcard("Jail", "uid-jail"),
            ),
        ])
        httpx_mock.add_response(
            url="https://carddav.fastmail.com/dav/addressbooks/user/user@fastmail.com/Default/",
            status_code=207,
            content=report_body,
        )

        result = client.validate_groups(["Imbox", "Feed", "Paper Trail", "Jail"])

        assert result == {
            "Imbox": {
                "href": "/dav/ab/Default/group-imbox.vcf",
                "etag": '"etag-imbox"',
                "uid": "uid-imbox",
            },
            "Feed": {
                "href": "/dav/ab/Default/group-feed.vcf",
                "etag": '"etag-feed"',
                "uid": "uid-feed",
            },
            "Paper Trail": {
                "href": "/dav/ab/Default/group-paper.vcf",
                "etag": '"etag-paper"',
                "uid": "uid-paper",
            },
            "Jail": {
                "href": "/dav/ab/Default/group-jail.vcf",
                "etag": '"etag-jail"',
                "uid": "uid-jail",
            },
        }

    def test_validate_groups_missing_group_raises(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """Missing required groups raises ValueError listing the missing names."""
        _connect_client(client, httpx_mock)

        # Only 3 of 4 groups exist
        report_body = _build_report_response([
            (
                "/dav/ab/Default/group-imbox.vcf",
                "etag-imbox",
                _group_vcard("Imbox", "uid-imbox"),
            ),
            (
                "/dav/ab/Default/group-feed.vcf",
                "etag-feed",
                _group_vcard("Feed", "uid-feed"),
            ),
            (
                "/dav/ab/Default/group-jail.vcf",
                "etag-jail",
                _group_vcard("Jail", "uid-jail"),
            ),
        ])
        httpx_mock.add_response(
            url="https://carddav.fastmail.com/dav/addressbooks/user/user@fastmail.com/Default/",
            status_code=207,
            content=report_body,
        )

        with pytest.raises(ValueError, match="Paper Trail"):
            client.validate_groups(["Imbox", "Feed", "Paper Trail", "Jail"])

    def test_validate_groups_ignores_non_group_vcards(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """Regular contact vCards (without KIND:group) are filtered out."""
        _connect_client(client, httpx_mock)

        report_body = _build_report_response([
            # Regular contacts (should be ignored)
            (
                "/dav/ab/Default/contact-alice.vcf",
                "etag-alice",
                _contact_vcard("Alice Smith", "uid-alice", "alice@example.com"),
            ),
            (
                "/dav/ab/Default/contact-bob.vcf",
                "etag-bob",
                _contact_vcard("Bob Jones", "uid-bob", "bob@example.com"),
            ),
            # Group vCard
            (
                "/dav/ab/Default/group-imbox.vcf",
                "etag-imbox",
                _group_vcard("Imbox", "uid-imbox"),
            ),
        ])
        httpx_mock.add_response(
            url="https://carddav.fastmail.com/dav/addressbooks/user/user@fastmail.com/Default/",
            status_code=207,
            content=report_body,
        )

        result = client.validate_groups(["Imbox"])

        # Only the group should appear, not the regular contacts
        assert len(result) == 1
        assert "Imbox" in result
        assert "Alice Smith" not in result
        assert "Bob Jones" not in result


# --- Search by Email Tests ---


ADDRESSBOOK_URL = (
    "https://carddav.fastmail.com"
    "/dav/addressbooks/user/user@fastmail.com/Default/"
)


class TestSearchByEmail:
    """Tests for CardDAVClient.search_by_email()."""

    def test_search_by_email_finds_contact(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """REPORT with email filter returns matching contact data."""
        _connect_client(client, httpx_mock)

        report_body = _build_report_response([
            (
                "/dav/ab/Default/contact-alice.vcf",
                "etag-alice",
                _contact_vcard("Alice Smith", "uid-alice", "alice@example.com"),
            ),
        ])
        httpx_mock.add_response(
            url=ADDRESSBOOK_URL,
            status_code=207,
            content=report_body,
        )

        results = client.search_by_email("alice@example.com")

        assert len(results) == 1
        assert results[0]["href"] == "/dav/ab/Default/contact-alice.vcf"
        assert results[0]["etag"] == '"etag-alice"'
        assert "vcard_data" in results[0]

    def test_search_by_email_no_results(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """REPORT with no matches returns empty list."""
        _connect_client(client, httpx_mock)

        report_body = _build_report_response([])
        httpx_mock.add_response(
            url=ADDRESSBOOK_URL,
            status_code=207,
            content=report_body,
        )

        results = client.search_by_email("nobody@example.com")

        assert results == []

    def test_search_by_email_multiple_results(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """REPORT returns multiple contacts when the same email appears on different vCards."""
        _connect_client(client, httpx_mock)

        report_body = _build_report_response([
            (
                "/dav/ab/Default/contact-alice.vcf",
                "etag-alice",
                _contact_vcard(
                    "Alice Smith", "uid-alice", "shared@example.com"
                ),
            ),
            (
                "/dav/ab/Default/contact-bob.vcf",
                "etag-bob",
                _contact_vcard(
                    "Bob Jones", "uid-bob", "shared@example.com"
                ),
            ),
        ])
        httpx_mock.add_response(
            url=ADDRESSBOOK_URL,
            status_code=207,
            content=report_body,
        )

        results = client.search_by_email("shared@example.com")

        assert len(results) == 2

    def test_search_not_connected_raises(self, client: CardDAVClient) -> None:
        """search_by_email before connect() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="not connected"):
            client.search_by_email("test@example.com")

    def test_search_by_email_sends_report_request(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """search_by_email sends a REPORT request with addressbook-query XML."""
        _connect_client(client, httpx_mock)

        report_body = _build_report_response([])
        httpx_mock.add_response(
            url=ADDRESSBOOK_URL,
            status_code=207,
            content=report_body,
        )

        client.search_by_email("test@example.com")

        # The 4th request (after 3 PROPFIND discovery) should be a REPORT
        requests = httpx_mock.get_requests()
        report_req = requests[3]
        assert report_req.method == "REPORT"
        body = report_req.content.decode("utf-8")
        assert "addressbook-query" in body
        assert "prop-filter" in body
        assert "EMAIL" in body
        assert "test@example.com" in body


# --- Create Contact Tests ---


class TestCreateContact:
    """Tests for CardDAVClient.create_contact()."""

    def test_create_contact_sends_valid_vcard(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """PUT sends a valid vCard 3.0 with FN, EMAIL, NOTE, UID."""
        _connect_client(client, httpx_mock)

        httpx_mock.add_response(
            status_code=201,
            headers={"etag": '"new-etag"'},
        )

        client.create_contact("jane@example.com", "Jane Smith")

        # The 4th request (after 3 PROPFIND) should be the PUT
        requests = httpx_mock.get_requests()
        put_req = requests[3]
        assert put_req.method == "PUT"

        # Parse the sent vCard body
        vcard_body = put_req.content.decode("utf-8")
        card = vobject.readOne(vcard_body)
        assert card.version.value == "3.0"
        assert card.fn.value == "Jane Smith"
        assert card.email.value == "jane@example.com"
        assert "Added by Mailroom on" in card.note.value
        # UID should be a valid UUID
        uuid.UUID(card.uid.value)

    def test_create_contact_returns_href_etag_uid(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """create_contact returns dict with href, etag, and uid keys."""
        _connect_client(client, httpx_mock)

        httpx_mock.add_response(
            status_code=201,
            headers={"etag": '"new-etag"'},
        )

        result = client.create_contact("jane@example.com", "Jane Smith")

        assert "href" in result
        assert "etag" in result
        assert "uid" in result
        assert result["etag"] == '"new-etag"'
        # href should contain the UUID and end with .vcf
        assert result["href"].endswith(".vcf")

    def test_create_contact_uses_if_none_match(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """PUT request includes If-None-Match: * to prevent overwriting."""
        _connect_client(client, httpx_mock)

        httpx_mock.add_response(
            status_code=201,
            headers={"etag": '"new-etag"'},
        )

        client.create_contact("jane@example.com", "Jane Smith")

        requests = httpx_mock.get_requests()
        put_req = requests[3]
        assert put_req.headers.get("if-none-match") == "*"

    def test_create_contact_email_prefix_fallback(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """When display_name is None, FN is set to the email prefix."""
        _connect_client(client, httpx_mock)

        httpx_mock.add_response(
            status_code=201,
            headers={"etag": '"new-etag"'},
        )

        client.create_contact("jane@example.com")

        requests = httpx_mock.get_requests()
        put_req = requests[3]
        vcard_body = put_req.content.decode("utf-8")
        card = vobject.readOne(vcard_body)
        assert card.fn.value == "jane"


# --- Add to Group Tests ---

GROUP_HREF = "/dav/ab/Default/group-imbox.vcf"
GROUP_URL = f"https://carddav.fastmail.com{GROUP_HREF}"


def _setup_client_with_groups(
    client: CardDAVClient, httpx_mock: HTTPXMock
) -> None:
    """Connect client and populate _groups dict for add_to_group tests."""
    _connect_client(client, httpx_mock)
    # Manually set up the groups dict as if validate_groups() ran
    client._groups = {
        "Imbox": {
            "href": GROUP_HREF,
            "etag": '"etag-imbox-1"',
            "uid": "uid-imbox",
        },
    }


class TestAddToGroup:
    """Tests for CardDAVClient.add_to_group()."""

    def test_add_to_group_appends_member(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """PUT body contains new member and preserves existing members."""
        _setup_client_with_groups(client, httpx_mock)

        existing_member = "existing-member-uid"
        group_body = _group_vcard(
            "Imbox", "uid-imbox", members=[existing_member]
        )
        # Mock GET for group vCard
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-imbox-1"'},
        )
        # Mock PUT success
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=204,
            headers={"etag": '"etag-imbox-2"'},
        )

        new_uid = "new-contact-uid"
        client.add_to_group("Imbox", new_uid)

        # Check the PUT body
        requests = httpx_mock.get_requests()
        # After 3 PROPFIND + 1 GET + 1 PUT
        put_req = requests[4]
        assert put_req.method == "PUT"
        put_body = put_req.content.decode("utf-8")

        # Both old and new members should be present
        assert f"urn:uuid:{existing_member}" in put_body
        assert f"urn:uuid:{new_uid}" in put_body

    def test_add_to_group_uses_if_match(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """PUT includes If-Match with the ETag from the GET response."""
        _setup_client_with_groups(client, httpx_mock)

        group_body = _group_vcard("Imbox", "uid-imbox")
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-imbox-1"'},
        )
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=204,
            headers={"etag": '"etag-imbox-2"'},
        )

        client.add_to_group("Imbox", "some-uid")

        requests = httpx_mock.get_requests()
        put_req = requests[4]
        assert put_req.headers.get("if-match") == '"etag-imbox-1"'

    def test_add_to_group_retries_on_412(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """On 412, re-fetches group and retries PUT successfully."""
        _setup_client_with_groups(client, httpx_mock)

        group_body = _group_vcard("Imbox", "uid-imbox")

        # Attempt 1: GET -> PUT returns 412
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-v1"'},
        )
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=412,
        )
        # Attempt 2: GET (fresh) -> PUT success
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-v2"'},
        )
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=204,
            headers={"etag": '"etag-v3"'},
        )

        client.add_to_group("Imbox", "new-uid")

        # Count PUTs: should be exactly 2
        requests = httpx_mock.get_requests()
        put_requests = [
            r for r in requests if r.method == "PUT"
        ]
        assert len(put_requests) == 2

    def test_add_to_group_raises_after_max_retries(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """After exhausting retries, raises RuntimeError."""
        _setup_client_with_groups(client, httpx_mock)

        group_body = _group_vcard("Imbox", "uid-imbox")

        # 3 attempts: GET -> PUT(412) each time
        for etag_n in range(1, 4):
            httpx_mock.add_response(
                url=GROUP_URL,
                status_code=200,
                content=group_body.encode("utf-8"),
                headers={"etag": f'"etag-v{etag_n}"'},
            )
            httpx_mock.add_response(
                url=GROUP_URL,
                status_code=412,
            )

        with pytest.raises(RuntimeError, match="retries"):
            client.add_to_group("Imbox", "new-uid")

    def test_add_to_group_skips_if_already_member(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """No PUT when contact is already in the group."""
        _setup_client_with_groups(client, httpx_mock)

        existing_uid = "already-in-group-uid"
        group_body = _group_vcard(
            "Imbox", "uid-imbox", members=[existing_uid]
        )
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-imbox-1"'},
        )

        client.add_to_group("Imbox", existing_uid)

        # No PUT should have been sent (only PROPFIND + GET)
        requests = httpx_mock.get_requests()
        put_requests = [
            r for r in requests if r.method == "PUT"
        ]
        assert len(put_requests) == 0


# --- Upsert Contact Tests ---


class TestUpsertContact:
    """Tests for CardDAVClient.upsert_contact()."""

    def test_upsert_new_contact(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """New sender: creates contact then adds to group."""
        _setup_client_with_groups(client, httpx_mock)

        # Mock search_by_email returning empty
        search_body = _build_report_response([])
        httpx_mock.add_response(
            url=ADDRESSBOOK_URL,
            status_code=207,
            content=search_body,
        )
        # Mock create_contact PUT
        httpx_mock.add_response(
            status_code=201,
            headers={"etag": '"new-contact-etag"'},
        )
        # Mock add_to_group: GET group vCard
        group_body = _group_vcard("Imbox", "uid-imbox")
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-imbox-1"'},
        )
        # Mock add_to_group: PUT group vCard
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=204,
            headers={"etag": '"etag-imbox-2"'},
        )

        result = client.upsert_contact(
            "jane@example.com", "Jane Smith", "Imbox"
        )

        assert result["action"] == "created"
        assert result["group"] == "Imbox"
        assert "uid" in result

    def test_upsert_existing_contact_adds_to_group(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """Existing sender: skips create, adds to group."""
        _setup_client_with_groups(client, httpx_mock)

        # Mock search returning existing contact
        existing = _contact_vcard(
            "Jane Smith",
            "existing-uid",
            "jane@example.com",
            note="Personal contact",
        )
        search_body = _build_report_response([
            (
                "/dav/ab/Default/jane.vcf",
                "etag-jane",
                existing,
            ),
        ])
        httpx_mock.add_response(
            url=ADDRESSBOOK_URL,
            status_code=207,
            content=search_body,
        )
        # Mock add_to_group: GET group vCard
        group_body = _group_vcard("Imbox", "uid-imbox")
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-imbox-1"'},
        )
        # Mock add_to_group: PUT group vCard
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=204,
            headers={"etag": '"etag-imbox-2"'},
        )

        result = client.upsert_contact(
            "jane@example.com", "Jane Smith", "Imbox"
        )

        assert result["action"] == "existing"
        assert result["uid"] == "existing-uid"
        assert result["group"] == "Imbox"

        # create_contact should NOT have been called (no extra PUT)
        requests = httpx_mock.get_requests()
        put_requests = [
            r for r in requests if r.method == "PUT"
        ]
        # Only the group PUT, no contact PUT
        assert len(put_requests) == 1

    def test_upsert_existing_contact_no_overwrite(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """Existing contact with filled fields: nothing overwritten."""
        _setup_client_with_groups(client, httpx_mock)

        # Contact already has FN, N, NOTE, EMAIL -- nothing to fill
        existing = _contact_vcard(
            "Jane Smith",
            "existing-uid",
            "jane@example.com",
            note="Personal contact",
        )
        search_body = _build_report_response([
            (
                "/dav/ab/Default/jane.vcf",
                "etag-jane",
                existing,
            ),
        ])
        httpx_mock.add_response(
            url=ADDRESSBOOK_URL,
            status_code=207,
            content=search_body,
        )
        # Mock add_to_group: GET + PUT
        group_body = _group_vcard("Imbox", "uid-imbox")
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-imbox-1"'},
        )
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=204,
            headers={"etag": '"etag-imbox-2"'},
        )

        result = client.upsert_contact(
            "jane@example.com", "Jane Smith", "Imbox"
        )

        assert result["action"] == "existing"
        # No contact update PUT should have been sent
        # (only the group PUT from add_to_group)
        requests = httpx_mock.get_requests()
        put_requests = [
            r for r in requests if r.method == "PUT"
        ]
        assert len(put_requests) == 1  # only group PUT

    def test_upsert_existing_contact_merge_cautious(
        self, client: CardDAVClient, httpx_mock: HTTPXMock
    ) -> None:
        """Existing contact missing email: new email added without overwrite."""
        _setup_client_with_groups(client, httpx_mock)

        # Contact has a different email; the new one should be added
        existing = _contact_vcard(
            "Jane Smith",
            "existing-uid",
            "jane.personal@example.com",
            note="My friend Jane",
        )
        search_body = _build_report_response([
            (
                "/dav/ab/Default/jane.vcf",
                "etag-jane",
                existing,
            ),
        ])
        httpx_mock.add_response(
            url=ADDRESSBOOK_URL,
            status_code=207,
            content=search_body,
        )
        # Mock the merge PUT for the contact update
        httpx_mock.add_response(
            url="https://carddav.fastmail.com/dav/ab/Default/jane.vcf",
            status_code=204,
            headers={"etag": '"etag-jane-updated"'},
        )
        # Mock add_to_group: GET + PUT
        group_body = _group_vcard("Imbox", "uid-imbox")
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=200,
            content=group_body.encode("utf-8"),
            headers={"etag": '"etag-imbox-1"'},
        )
        httpx_mock.add_response(
            url=GROUP_URL,
            status_code=204,
            headers={"etag": '"etag-imbox-2"'},
        )

        result = client.upsert_contact(
            "jane.work@example.com", "Jane Smith", "Imbox"
        )

        assert result["action"] == "existing"

        # Find the contact update PUT (not the group PUT)
        requests = httpx_mock.get_requests()
        contact_puts = [
            r for r in requests
            if r.method == "PUT" and "jane.vcf" in str(r.url)
        ]
        assert len(contact_puts) == 1

        # Parse the updated vCard
        updated_body = contact_puts[0].content.decode("utf-8")
        card = vobject.readOne(updated_body)

        # Original fields preserved
        assert card.fn.value == "Jane Smith"
        assert card.note.value == "My friend Jane"

        # Both emails present
        emails = [e.value for e in card.contents.get("email", [])]
        assert "jane.personal@example.com" in emails
        assert "jane.work@example.com" in emails
