"""Tests for CardDAV client: PROPFIND discovery, connection, and group validation."""

import httpx
import pytest
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


def _group_vcard(fn: str, uid: str) -> str:
    """Build an Apple-style group vCard string."""
    return (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        f"UID:{uid}\r\n"
        f"FN:{fn}\r\n"
        f"N:{fn};;;;\r\n"
        "X-ADDRESSBOOKSERVER-KIND:group\r\n"
        "END:VCARD"
    )


def _contact_vcard(fn: str, uid: str, email: str) -> str:
    """Build a regular contact vCard string (not a group)."""
    return (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        f"UID:{uid}\r\n"
        f"FN:{fn}\r\n"
        f"N:{fn};;;;\r\n"
        f"EMAIL;TYPE=INTERNET:{email}\r\n"
        "END:VCARD"
    )


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
