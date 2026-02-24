"""Tests for CardDAV client: PROPFIND discovery, connection, and group validation."""

import httpx
import pytest
from pytest_httpx import HTTPXMock

# Will fail until CardDAVClient is created (RED phase)
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
