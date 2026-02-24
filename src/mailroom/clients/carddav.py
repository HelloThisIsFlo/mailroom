"""CardDAV client for Fastmail: auth, discovery, group validation, and contact ops."""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from datetime import date

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
            follow_redirects=True,
        )
        self._addressbook_url: str | None = None
        self._groups: dict[str, dict] = {}

    def connect(self) -> None:
        """Discover the default address book URL via 3-step PROPFIND chain.

        Steps:
        1. PROPFIND /.well-known/carddav for current-user-principal
        2. PROPFIND principal for addressbook-home-set
        3. PROPFIND home with Depth:1 for addressbook collections

        Raises:
            httpx.HTTPStatusError: On 401 (bad credentials) or other HTTP errors.
            httpx.ConnectError: On network failure.
        """
        # Step 1: Find principal URL (RFC 6764 well-known entry point)
        resp = self._http.request(
            "PROPFIND",
            f"https://{self._hostname}/.well-known/carddav",
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

    def search_by_email(self, email: str) -> list[dict]:
        """Search for contacts matching an email address.

        Sends a REPORT addressbook-query with a case-insensitive email
        prop-filter to find existing contacts.

        Args:
            email: Email address to search for.

        Returns:
            List of dicts with 'href', 'etag', and 'vcard_data' keys.

        Raises:
            RuntimeError: If connect() has not been called.
        """
        addressbook_url = self._require_connection()

        # Build the REPORT XML body using ElementTree for proper escaping
        query = ET.Element(
            f"{CARDDAV}addressbook-query",
            {
                "xmlns:D": "DAV:",
                "xmlns:C": "urn:ietf:params:xml:ns:carddav",
            },
        )
        prop = ET.SubElement(query, f"{DAV}prop")
        ET.SubElement(prop, f"{DAV}getetag")
        ET.SubElement(prop, f"{CARDDAV}address-data")

        filt = ET.SubElement(query, f"{CARDDAV}filter", {"test": "anyof"})
        prop_filter = ET.SubElement(
            filt, f"{CARDDAV}prop-filter", {"name": "EMAIL"}
        )
        text_match = ET.SubElement(
            prop_filter,
            f"{CARDDAV}text-match",
            {
                "collation": "i;unicode-casemap",
                "match-type": "equals",
            },
        )
        text_match.text = email

        xml_body = ET.tostring(query, encoding="unicode", xml_declaration=True)

        resp = self._http.request(
            "REPORT",
            addressbook_url,
            content=xml_body.encode("utf-8"),
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Depth": "1",
            },
        )
        resp.raise_for_status()

        return self._parse_multistatus(resp.content)

    def create_contact(
        self, email: str, display_name: str | None = None
    ) -> dict:
        """Create a new contact vCard in the addressbook.

        Builds a vCard 3.0 with FN, N, EMAIL, NOTE, UID and PUTs it
        using If-None-Match: * to prevent overwriting existing contacts.

        Args:
            email: Contact email address.
            display_name: Display name (falls back to email prefix if None).

        Returns:
            Dict with 'href', 'etag', and 'uid' keys.

        Raises:
            RuntimeError: If connect() has not been called.
        """
        addressbook_url = self._require_connection()

        contact_uid = str(uuid.uuid4())
        name = display_name or email.split("@")[0]

        # Build vCard using vobject
        card = vobject.vCard()
        card.add("uid").value = contact_uid
        card.add("fn").value = name
        card.add("n").value = vobject.vcard.Name(given=name)
        email_prop = card.add("email")
        email_prop.value = email
        email_prop.type_param = "INTERNET"
        card.add("note").value = (
            f"Added by Mailroom on {date.today().isoformat()}"
        )

        # PUT to addressbook with If-None-Match
        href_path = f"{contact_uid}.vcf"
        put_url = f"{addressbook_url}{href_path}"

        resp = self._http.put(
            put_url,
            content=card.serialize().encode("utf-8"),
            headers={
                "Content-Type": "text/vcard; charset=utf-8",
                "If-None-Match": "*",
            },
        )
        resp.raise_for_status()

        return {
            "href": f"/{contact_uid}.vcf",
            "etag": resp.headers.get("etag", ""),
            "uid": contact_uid,
        }

    def add_to_group(
        self,
        group_name: str,
        contact_uid: str,
        max_retries: int = 3,
    ) -> str:
        """Add a contact to a group by modifying the group's vCard.

        Fetches the group vCard, appends an X-ADDRESSBOOKSERVER-MEMBER
        entry, and PUTs it back with If-Match for concurrency safety.
        Retries on 412 Precondition Failed (ETag conflict).

        Args:
            group_name: Name of the group (must exist in self._groups).
            contact_uid: UID of the contact to add.
            max_retries: Maximum number of retry attempts on 412.

        Returns:
            The new ETag of the group vCard after successful PUT.

        Raises:
            RuntimeError: After exhausting retries on 412 conflicts.
        """
        self._require_connection()
        group_info = self._groups[group_name]
        href = group_info["href"]
        group_url = f"https://{self._hostname}{href}"

        member_urn = f"urn:uuid:{contact_uid}"

        for _attempt in range(max_retries):
            # GET current group vCard
            resp = self._http.get(group_url)
            resp.raise_for_status()
            current_etag = resp.headers.get("etag", "")

            card = vobject.readOne(resp.text)

            # Check if already a member
            existing_members = card.contents.get(
                "x-addressbookserver-member", []
            )
            existing_urns = [m.value for m in existing_members]
            if member_urn in existing_urns:
                return current_etag

            # Add new member
            card.add("x-addressbookserver-member").value = member_urn

            # PUT with If-Match
            put_resp = self._http.put(
                group_url,
                content=card.serialize().encode("utf-8"),
                headers={
                    "Content-Type": "text/vcard; charset=utf-8",
                    "If-Match": current_etag,
                },
            )

            if put_resp.status_code == 412:
                continue  # ETag conflict, retry

            put_resp.raise_for_status()

            # Update stored ETag
            new_etag = put_resp.headers.get("etag", "")
            self._groups[group_name]["etag"] = new_etag
            return new_etag

        raise RuntimeError(
            f"Failed to add member to group {group_name} "
            f"after {max_retries} retries (ETag conflict)"
        )

    def upsert_contact(
        self,
        email: str,
        display_name: str | None,
        group_name: str,
    ) -> dict:
        """Search-or-create a contact and add it to a group.

        Orchestrates the full contact management flow:
        1. Search for existing contact by email
        2. If not found: create new contact
        3. If found: merge-cautious update (fill empty fields only)
        4. Add contact to the specified group

        Args:
            email: Sender email address.
            display_name: Sender display name (may be None).
            group_name: Target group name (must exist in self._groups).

        Returns:
            Dict with 'action' ("created" or "existing"),
            'uid', and 'group' keys.
        """
        results = self.search_by_email(email)

        if not results:
            # New contact
            new_contact = self.create_contact(email, display_name)
            self.add_to_group(group_name, new_contact["uid"])
            return {
                "action": "created",
                "uid": new_contact["uid"],
                "group": group_name,
            }

        # Existing contact -- use first match
        result = results[0]
        card = vobject.readOne(result["vcard_data"])
        contact_uid = card.uid.value

        # Merge-cautious update: fill empty fields, never overwrite
        changed = False

        # Check if this email is already on the contact
        existing_emails = [
            e.value.lower()
            for e in card.contents.get("email", [])
        ]
        if email.lower() not in existing_emails:
            new_email = card.add("email")
            new_email.value = email
            new_email.type_param = "INTERNET"
            changed = True

        # Only set FN if missing or empty
        fn_value = getattr(card, "fn", None)
        if (
            fn_value is None
            or not fn_value.value.strip()
        ) and display_name:
            if fn_value is None:
                card.add("fn").value = display_name
            else:
                card.fn.value = display_name
            changed = True

        # Only add NOTE if none exists
        note_value = card.contents.get("note", [])
        if not note_value:
            card.add("note").value = (
                f"Added by Mailroom on {date.today().isoformat()}"
            )
            changed = True

        # PUT updated vCard if anything changed
        if changed:
            href = result["href"]
            etag = result["etag"]
            self._http.put(
                f"https://{self._hostname}{href}",
                content=card.serialize().encode("utf-8"),
                headers={
                    "Content-Type": "text/vcard; charset=utf-8",
                    "If-Match": etag,
                },
            )

        self.add_to_group(group_name, contact_uid)
        return {
            "action": "existing",
            "uid": contact_uid,
            "group": group_name,
        }
