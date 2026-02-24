"""CardDAV client for Fastmail: Basic auth, PROPFIND discovery, and group validation."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx
import vobject

# XML namespace constants (Clark notation for ElementTree)
DAV = "{DAV:}"
CARDDAV = "{urn:ietf:params:xml:ns:carddav}"

# PROPFIND request bodies
PROPFIND_PRINCIPAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:current-user-principal/>
  </D:prop>
</D:propfind>"""

PROPFIND_AB_HOME = b"""<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <C:addressbook-home-set/>
  </D:prop>
</D:propfind>"""

PROPFIND_ADDRESSBOOKS = b"""<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:resourcetype/>
    <D:displayname/>
  </D:prop>
</D:propfind>"""

# REPORT body for fetching all vCards (addressbook-query with no filter)
REPORT_ALL_VCARDS = b"""<?xml version="1.0" encoding="UTF-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data/>
  </D:prop>
</C:addressbook-query>"""


class CardDAVClient:
    """Thin CardDAV client over httpx for Fastmail contact operations.

    Usage:
        client = CardDAVClient(username="user@fastmail.com", password="app-password")
        client.connect()  # discovers addressbook via PROPFIND chain
        groups = client.validate_groups(["Imbox", "Feed", "Paper Trail", "Jail"])
    """

    def __init__(
        self,
        username: str,
        password: str,
        hostname: str = "carddav.fastmail.com",
    ) -> None:
        self._hostname = hostname
        self._http = httpx.Client(
            auth=httpx.BasicAuth(username, password),
            headers={"Content-Type": "application/xml; charset=utf-8"},
        )
        self._addressbook_url: str | None = None
        self._groups: dict[str, dict] = {}

    def connect(self) -> None:
        """Discover the default address book URL via 3-step PROPFIND chain.

        Steps:
        1. PROPFIND / for current-user-principal
        2. PROPFIND principal for addressbook-home-set
        3. PROPFIND home with Depth:1 for addressbook collections

        Raises:
            httpx.HTTPStatusError: On 401 (bad credentials) or other HTTP errors.
            httpx.ConnectError: On network failure.
        """
        # Step 1: Find principal URL
        resp = self._http.request(
            "PROPFIND",
            f"https://{self._hostname}/",
            content=PROPFIND_PRINCIPAL,
            headers={"Depth": "0"},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        principal_href = root.findtext(
            f".//{DAV}current-user-principal/{DAV}href", ""
        )

        # Step 2: Find addressbook home URL
        resp = self._http.request(
            "PROPFIND",
            f"https://{self._hostname}{principal_href}",
            content=PROPFIND_AB_HOME,
            headers={"Depth": "0"},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        home_href = root.findtext(
            f".//{CARDDAV}addressbook-home-set/{DAV}href", ""
        )

        # Step 3: Find the default addressbook collection
        resp = self._http.request(
            "PROPFIND",
            f"https://{self._hostname}{home_href}",
            content=PROPFIND_ADDRESSBOOKS,
            headers={"Depth": "1"},
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for response_el in root.findall(f"{DAV}response"):
            href = response_el.findtext(f"{DAV}href", "")
            propstat = response_el.find(f"{DAV}propstat")
            if propstat is None:
                continue
            status = propstat.findtext(f"{DAV}status", "")
            if "200" not in status:
                continue
            prop = propstat.find(f"{DAV}prop")
            if prop is None:
                continue
            resourcetype = prop.find(f"{DAV}resourcetype")
            if resourcetype is None:
                continue
            # Look for a resource that is both a collection and an addressbook
            if resourcetype.find(f"{CARDDAV}addressbook") is not None:
                self._addressbook_url = f"https://{self._hostname}{href}"
                return

    def _require_connection(self) -> str:
        """Guard: ensure connect() has been called. Returns addressbook URL.

        Raises:
            RuntimeError: If connect() has not been called or failed.
        """
        if self._addressbook_url is None:
            raise RuntimeError(
                "CardDAVClient is not connected. Call connect() first."
            )
        return self._addressbook_url

    def _parse_multistatus(self, xml_bytes: bytes) -> list[dict]:
        """Parse a 207 Multi-Status response into a list of resource dicts.

        Returns:
            List of dicts with 'href', 'etag', and 'vcard_data' keys.
        """
        root = ET.fromstring(xml_bytes)
        results = []

        for response_el in root.findall(f"{DAV}response"):
            href = response_el.findtext(f"{DAV}href", "")
            propstat = response_el.find(f"{DAV}propstat")
            if propstat is None:
                continue

            status = propstat.findtext(f"{DAV}status", "")
            if "200" not in status:
                continue

            prop = propstat.find(f"{DAV}prop")
            if prop is None:
                continue

            etag = prop.findtext(f"{DAV}getetag", "")
            address_data = prop.findtext(f"{CARDDAV}address-data", "")

            results.append({
                "href": href,
                "etag": etag,
                "vcard_data": address_data,
            })

        return results

    def validate_groups(self, required_groups: list[str]) -> dict[str, dict]:
        """Validate that all required contact groups exist in the addressbook.

        Fetches all vCards via REPORT addressbook-query, filters for Apple-style
        group vCards (X-ADDRESSBOOKSERVER-KIND:group), and matches by FN.

        Args:
            required_groups: List of group names that must exist.

        Returns:
            Dict mapping group name to {"href": ..., "etag": ..., "uid": ...}.

        Raises:
            RuntimeError: If connect() has not been called.
            ValueError: If any required groups are missing, listing all missing names.
        """
        addressbook_url = self._require_connection()

        # Fetch all vCards with a single REPORT request
        resp = self._http.request(
            "REPORT",
            addressbook_url,
            content=REPORT_ALL_VCARDS,
            headers={"Depth": "1"},
        )
        resp.raise_for_status()

        all_items = self._parse_multistatus(resp.content)

        # Filter for group vCards and build name -> info map
        groups: dict[str, dict] = {}
        for item in all_items:
            vcard_data = item.get("vcard_data", "")
            if not vcard_data:
                continue

            card = vobject.readOne(vcard_data)

            # Check for Apple-style group marker
            kind_list = card.contents.get("x-addressbookserver-kind", [])
            if not kind_list or kind_list[0].value.lower() != "group":
                continue

            fn = card.fn.value
            groups[fn] = {
                "href": item["href"],
                "etag": item["etag"],
                "uid": card.uid.value,
            }

        # Check all required groups exist
        missing = [g for g in required_groups if g not in groups]
        if missing:
            raise ValueError(
                f"Required contact groups not found in Fastmail: "
                f"{', '.join(missing)}. "
                "Create them in Fastmail Contacts before starting Mailroom."
            )

        # Store validated groups for later use
        self._groups = {g: groups[g] for g in required_groups}
        return self._groups
