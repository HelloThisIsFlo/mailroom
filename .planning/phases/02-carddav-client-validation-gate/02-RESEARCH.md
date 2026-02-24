# Phase 2: CardDAV Client (Validation Gate) - Research

**Researched:** 2026-02-24
**Domain:** CardDAV protocol (RFC 6352), vCard 3.0 format, Fastmail contact group model, WebDAV concurrency (ETags)
**Confidence:** HIGH

## Summary

Phase 2 builds a CardDAV client that can search, create, and update contacts in Fastmail, and assign them to contact groups (Imbox, Feed, Paper Trail, Jail). This is a validation gate -- the Fastmail KIND:group contact model must be proven against live Fastmail before the triage pipeline (Phase 3) is built on top of it.

CardDAV is a WebDAV extension (RFC 6352) that uses HTTP methods (PROPFIND, REPORT, PUT, DELETE) with XML request/response bodies and vCard 3.0 text payloads. Fastmail implements the Apple-style contact group model: groups are separate vCard entries marked with `X-ADDRESSBOOKSERVER-KIND:group` and members are referenced via `X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:{contact-uid}`. This is confirmed by DAVx5 testing documentation and community reports. Concurrency is handled via HTTP ETags with `If-Match` headers on PUT requests (412 Precondition Failed on conflict).

The recommended approach is a thin CardDAV client built directly on `httpx` (already a project dependency), consistent with the Phase 1 JMAP client pattern. XML request/response handling uses Python's stdlib `xml.etree.ElementTree` (sufficient for the small, well-defined XML structures in CardDAV). vCard parsing and generation uses the `vobject` library (v1.0.0, Apache 2.0, actively maintained), which handles the complex vCard 3.0 format reliably and avoids hand-rolling a parser for a deceptively complex format.

**Primary recommendation:** Build a thin CardDAV client on `httpx` + `xml.etree.ElementTree` for the protocol layer, and use `vobject` for vCard serialization/parsing. Do not use the `caldav` library (CalDAV only, no CardDAV support) or `pyCardDAV` (unmaintained). The CardDAV protocol surface needed is small: PROPFIND for discovery, REPORT addressbook-query for search, PUT for create/update, and GET for fetch.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Extract display name from email headers (e.g., "Jane Smith" from "Jane Smith <jane@example.com>"); fall back to email prefix if no display name present
- Include a NOTE field: "Added by Mailroom on YYYY-MM-DD" to distinguish auto-created contacts from manual ones
- Known limitation (v1): shared-sender addresses (e.g., noreply@dpd.com) may get the wrong display name from the first triaged email. Routing still works correctly -- name is cosmetic
- Merge cautiously: add group membership and fill empty fields, but never overwrite existing data (name, phone, notes, etc.)
- Match on any email address on a contact card to prevent duplicates (not just primary email)
- Contact groups (Imbox, Feed, Paper Trail, Jail) must pre-exist in Fastmail -- fail loudly if missing (config error)
- Verify all configured groups resolve to CardDAV URIs at startup -- fast feedback on typos or missing groups
- One group per contact -- no multi-group membership
- Re-triage in v1: if a sender is already in a group and gets triaged to a different destination, skip processing, apply @MailroomError label, keep triage label on the email for context
- @MailroomError is a Fastmail label used as a user-visible error notification
- Applied only for user-actionable errors (re-triage conflict, persistent failures), not transient issues
- Transient errors: retry silently for 3 poll cycles (~15 min), then escalate to @MailroomError
- @MailroomError must exist in Fastmail -- verified at startup alongside other labels
- Human test script against live Fastmail -- not automated integration tests
- Validation boundary: contact in correct group = Phase 2 success
- Test script includes: (1) create contact with correct data, (2) verify contact in correct group, (3) verify existing contact not duplicated, (4) ETag conflict test with paused execution
- Clear setup documentation for manual prerequisites (groups, rules, app password)

### Claude's Discretion
- ETag concurrency implementation details (retry strategy, backoff)
- vCard 3.0 field formatting specifics
- CardDAV REPORT query construction
- Loading/skeleton design for any CLI output
- Exact structured log format for CardDAV operations

### Deferred Ideas (OUT OF SCOPE)
- Programmatic Fastmail rule verification/creation via JMAP sieve extension -- future version
- Display name accuracy for shared-sender addresses -- low priority, routing works correctly regardless
- TRIAGE-11 (sender display name preservation) in REQUIREMENTS.md is related to the display name edge case
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CDAV-01 | Service can authenticate with Fastmail CardDAV using Basic auth (app password) | Fastmail CardDAV endpoint at `https://carddav.fastmail.com/` uses HTTP Basic auth with full email address as username and app-specific password. httpx supports Basic auth natively via `httpx.BasicAuth`. |
| CDAV-02 | Service can search contacts by email address to check for existing contacts | CardDAV REPORT `addressbook-query` with `prop-filter name="EMAIL"` and `text-match match-type="equals"` (case-insensitive via `i;unicode-casemap` collation). Must match on ALL email addresses on a contact, not just primary. |
| CDAV-03 | Service can create a new contact vCard for a sender | HTTP PUT to `{addressbook-url}/{uuid}.vcf` with `Content-Type: text/vcard; charset=utf-8`. vCard 3.0 format with FN, N, EMAIL, NOTE, UID fields. Use `If-None-Match: *` to prevent overwriting existing. |
| CDAV-04 | Service can add a contact to a contact group (Imbox, Feed, Paper Trail, Jail) | Fastmail uses Apple-style groups: fetch group vCard (GET), add `X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:{contact-uid}` line, PUT back with `If-Match: {etag}`. Group vCards have `X-ADDRESSBOOKSERVER-KIND:group`. |
| CDAV-05 | Service handles existing contacts -- adds to group without creating duplicates | Search by email (CDAV-02) before creating. If contact exists: add to group only (CDAV-04), fill empty fields via merge-cautious PUT with If-Match ETag, never overwrite existing data. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.28.x (existing) | HTTP client for CardDAV requests (PROPFIND, REPORT, PUT, GET, DELETE) | Already a project dependency from Phase 1. Supports arbitrary HTTP methods, Basic auth, custom headers. |
| vobject | 1.0.0 | vCard 3.0 parsing and serialization | De facto Python library for vCard/iCal. Apache 2.0 license. Handles encoding, line folding, property parameters, structured name fields. Actively maintained. |
| xml.etree.ElementTree | stdlib | XML construction and parsing for WebDAV/CardDAV requests/responses | Python stdlib -- zero additional dependencies. Sufficient for the small, well-defined XML structures in CardDAV (PROPFIND, REPORT, 207 Multi-Status responses). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uuid (stdlib) | stdlib | Generate UUIDs for new contact vCard UIDs and filenames | Every new contact creation needs a unique UID and filename (`{uuid}.vcf`). |
| structlog | existing | Structured logging for CardDAV operations | Already configured from Phase 1. Bind operation context (action, sender, group). |
| pydantic-settings | existing | Configuration (carddav_password, carddav_username, group names) | Already in use. Config already has `carddav_password` field (empty default from Phase 1 forward compat). |

### Alternatives Considered
| Instead of | Could Use | Why Not |
|------------|-----------|---------|
| httpx (thin client) | caldav library | caldav is CalDAV only -- explicitly does not support CardDAV/addressbooks. Wrong tool. |
| httpx (thin client) | pyCardDAV | Unmaintained (last release years ago), uses `requests` not `httpx`, includes CLI code we don't need. |
| xml.etree.ElementTree | lxml | lxml has better namespace handling but adds a C extension dependency (compilation step). The XML structures in CardDAV are small and well-defined -- stdlib is sufficient. |
| vobject | Hand-rolled vCard parser | vCard format is deceptively complex: line folding at 75 chars, quoted-printable encoding, multi-value fields, parameter escaping. vobject handles all edge cases. |

**Installation:**
```bash
uv add vobject
```

No other new dependencies needed -- httpx, structlog, pydantic-settings already installed.

## Architecture Patterns

### Recommended Project Structure
```
src/mailroom/
├── clients/
│   ├── __init__.py
│   ├── jmap.py          # Existing from Phase 1
│   └── carddav.py       # NEW: Thin CardDAV client
├── core/
│   ├── config.py         # MODIFIED: Add carddav_username, validate groups config
│   └── logging.py        # Existing, unchanged
└── workflows/
    └── __init__.py       # Empty, Phase 3
tests/
├── test_carddav_client.py  # NEW: Unit tests with httpx mocking
└── ...                     # Existing tests unchanged
human-tests/
├── test_4_carddav_auth.py        # NEW: CardDAV auth + addressbook discovery
├── test_5_carddav_contacts.py    # NEW: Create, search, update contacts
├── test_6_carddav_groups.py      # NEW: Group membership + ETag conflict
└── ...                           # Existing human tests unchanged
```

### Pattern 1: Thin CardDAV Client (consistent with JMAPClient)
**What:** A class wrapping httpx that handles CardDAV authentication, address book discovery, and the specific operations mailroom needs. Not a full WebDAV implementation -- just search, create, update, and group management.
**When to use:** Always. This is the primary interface to Fastmail contacts.
**Example:**
```python
# Source: RFC 6352, sabre.io/dav/building-a-carddav-client/
import httpx
import xml.etree.ElementTree as ET

DAV_NS = "DAV:"
CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"

class CardDAVClient:
    """Thin CardDAV client over httpx for Fastmail contact operations."""

    def __init__(self, username: str, password: str,
                 hostname: str = "carddav.fastmail.com") -> None:
        self._hostname = hostname
        self._http = httpx.Client(
            auth=httpx.BasicAuth(username, password),
            headers={"Content-Type": "application/xml; charset=utf-8"},
        )
        self._addressbook_url: str | None = None

    def connect(self) -> None:
        """Discover the default address book URL via PROPFIND.

        Steps:
        1. PROPFIND / for current-user-principal
        2. PROPFIND principal for addressbook-home-set
        3. PROPFIND home for addressbook collections
        """
        # Step 1: Find principal
        principal_url = self._find_principal()
        # Step 2: Find addressbook home
        home_url = self._find_addressbook_home(principal_url)
        # Step 3: Find default addressbook
        self._addressbook_url = self._find_addressbook(home_url)
```

### Pattern 2: CardDAV addressbook-query REPORT for Email Search
**What:** Use the REPORT method with an addressbook-query XML body to search for contacts by email address.
**When to use:** Every time a sender needs to be checked for an existing contact (CDAV-02, CDAV-05).
**Example:**
```python
# Source: RFC 6352 Section 8.6, 10.5
def search_by_email(self, email: str) -> list[dict]:
    """Search for contacts matching an email address.

    Returns list of dicts with 'href', 'etag', and 'vcard_data' keys.
    """
    xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data/>
  </D:prop>
  <C:filter test="anyof">
    <C:prop-filter name="EMAIL">
      <C:text-match collation="i;unicode-casemap"
                    match-type="equals">{email}</C:text-match>
    </C:prop-filter>
  </C:filter>
</C:addressbook-query>"""

    resp = self._http.request(
        "REPORT",
        self._addressbook_url,
        content=xml_body.encode("utf-8"),
        headers={
            "Content-Type": "application/xml; charset=utf-8",
            "Depth": "1",
        },
    )
    resp.raise_for_status()
    return self._parse_multistatus(resp.content)
```

### Pattern 3: vCard 3.0 Contact Creation with vobject
**What:** Create a properly formatted vCard 3.0 for a new contact using the vobject library.
**When to use:** When creating a new contact for a sender who has no existing contact (CDAV-03).
**Example:**
```python
# Source: vobject docs (https://vobject.readthedocs.io/latest/),
#         Fastmail vCard 3.0 format requirements
import vobject
import uuid
from datetime import date

def create_contact_vcard(email: str, display_name: str) -> tuple[str, str]:
    """Create a vCard 3.0 for a new contact.

    Returns (uid, vcard_string) tuple.
    """
    card = vobject.vCard()

    # UID -- needed for group membership reference
    contact_uid = str(uuid.uuid4())
    card.add("uid").value = contact_uid

    # Name fields
    card.add("fn").value = display_name
    card.add("n").value = vobject.vcard.Name(given=display_name)

    # Email
    email_prop = card.add("email")
    email_prop.value = email
    email_prop.type_param = "INTERNET"

    # Mailroom attribution
    card.add("note").value = f"Added by Mailroom on {date.today().isoformat()}"

    return contact_uid, card.serialize()
```

### Pattern 4: Apple-Style Contact Group Membership
**What:** Add a contact to a Fastmail group by modifying the group's vCard to include a new `X-ADDRESSBOOKSERVER-MEMBER` entry.
**When to use:** Every time a contact is assigned to a triage destination group (CDAV-04).
**Example:**
```python
# Source: DAVx5 docs, rcmcarddav GROUPS.md, Apple AddressBook extensions
# Group vCard format (Fastmail uses this):
#
# BEGIN:VCARD
# VERSION:3.0
# FN:Imbox
# N:Imbox;;;;
# X-ADDRESSBOOKSERVER-KIND:group
# X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:abc123-...
# X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:def456-...
# UID:group-uid-here
# END:VCARD

def add_member_to_group(self, group_href: str, group_etag: str,
                        contact_uid: str) -> str:
    """Add a contact to a group vCard. Returns new ETag.

    Fetches current group vCard, appends MEMBER line, PUTs back
    with If-Match to handle concurrent edits.
    """
    # GET current group vCard
    resp = self._http.get(
        f"https://{self._hostname}{group_href}",
        headers={"Accept": "text/vcard"},
    )
    resp.raise_for_status()
    current_etag = resp.headers["etag"]

    # Parse, add member, serialize
    card = vobject.readOne(resp.text)
    member = card.add("x-addressbookserver-member")
    member.value = f"urn:uuid:{contact_uid}"

    # PUT with If-Match for concurrency safety
    put_resp = self._http.put(
        f"https://{self._hostname}{group_href}",
        content=card.serialize().encode("utf-8"),
        headers={
            "Content-Type": "text/vcard; charset=utf-8",
            "If-Match": current_etag,
        },
    )
    if put_resp.status_code == 412:
        raise PreconditionFailed(group_href, current_etag)
    put_resp.raise_for_status()
    return put_resp.headers.get("etag", "")
```

### Pattern 5: 207 Multi-Status XML Response Parsing
**What:** Parse WebDAV 207 Multi-Status responses using stdlib ElementTree with namespace-aware element access.
**When to use:** Every PROPFIND and REPORT response.
**Example:**
```python
# Source: RFC 4918 Section 13, WebDAV Multi-Status response format
import xml.etree.ElementTree as ET

DAV = "{DAV:}"
CARDDAV = "{urn:ietf:params:xml:ns:carddav}"

def _parse_multistatus(self, xml_bytes: bytes) -> list[dict]:
    """Parse a 207 Multi-Status response into a list of resource dicts."""
    root = ET.fromstring(xml_bytes)
    results = []

    for response in root.findall(f"{DAV}response"):
        href = response.findtext(f"{DAV}href", "")
        propstat = response.find(f"{DAV}propstat")
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
```

### Pattern 6: Group Validation at Startup
**What:** Verify that all configured contact groups exist as CardDAV group vCards at startup.
**When to use:** At service startup, before any triage processing.
**Example:**
```python
# Fetch all vCards, filter for X-ADDRESSBOOKSERVER-KIND:group,
# match by FN against configured group names
def validate_groups(self, required_groups: list[str]) -> dict[str, dict]:
    """Validate all required groups exist. Returns {name: {href, etag, uid}}.

    Raises ValueError if any required group is missing.
    """
    # REPORT: fetch all group vCards from addressbook
    all_vcards = self._fetch_all_vcards()

    groups = {}
    for item in all_vcards:
        card = vobject.readOne(item["vcard_data"])
        kind = getattr(card, "x_addressbookserver_kind", None)
        if kind and kind.value.lower() == "group":
            fn = card.fn.value
            groups[fn] = {
                "href": item["href"],
                "etag": item["etag"],
                "uid": card.uid.value,
            }

    missing = [g for g in required_groups if g not in groups]
    if missing:
        raise ValueError(
            f"Required contact groups not found in Fastmail: {', '.join(missing)}. "
            "Create them in Fastmail Contacts before starting Mailroom."
        )

    return {g: groups[g] for g in required_groups}
```

### Anti-Patterns to Avoid
- **Hand-rolling vCard format:** vCard line folding, quoted-printable encoding, and parameter escaping are complex. Use vobject. Never construct vCard strings manually.
- **Skipping If-Match on PUT:** Always send `If-Match: {etag}` when updating existing contacts or groups. Without it, concurrent edits (user editing in Fastmail web UI while Mailroom processes) will silently overwrite changes.
- **Creating contacts without UID:** Every vCard must have a UID. The UID is used for group membership references (`urn:uuid:{uid}`). Always generate a UUID4 for new contacts.
- **Assuming single email per contact:** Existing contacts may have multiple EMAIL properties. Match against ALL of them to prevent duplicates.
- **Overwriting existing contact data:** When adding group membership to an existing contact, GET the full vCard, add only the missing fields, PUT back. Never replace the entire vCard with a new one containing only Mailroom fields.
- **Using vCard 4.0 `KIND`/`MEMBER` instead of Apple extensions:** Fastmail uses the vCard 3.0 Apple-style extensions (`X-ADDRESSBOOKSERVER-KIND`, `X-ADDRESSBOOKSERVER-MEMBER`), not the vCard 4.0 standard `KIND`/`MEMBER` properties.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| vCard parsing/serialization | String splitting, regex on vCard text | `vobject` library | Line folding (75 char), quoted-printable encoding, multi-value fields, parameter escaping, charset handling. Edge cases everywhere. |
| UUID generation | Custom ID scheme, timestamp-based IDs | `uuid.uuid4()` (stdlib) | RFC 4122 compliant, cryptographically random, collision-proof. CardDAV expects standard UUIDs. |
| XML construction for WebDAV | f-string XML templates with user input | `xml.etree.ElementTree` | Proper escaping, namespace handling, well-formed XML guaranteed. f-string templates break with special characters in search terms. |
| HTTP Basic auth encoding | Manual base64 of `user:pass` | `httpx.BasicAuth` | Already handles encoding, header formatting, and special characters in passwords. |
| ETag retry logic | Custom while loops with sleep | Structured retry with configurable max attempts | Exponential backoff, jitter, max retries, proper logging. Simple loops miss edge cases. |

**Key insight:** CardDAV is a protocol with many sharp edges hidden behind apparent simplicity. The vCard format, WebDAV XML namespaces, and ETag concurrency each have non-obvious complexity. Use established libraries for each layer (vobject for vCards, ElementTree for XML, httpx for HTTP) and only build the thin glue between them.

## Common Pitfalls

### Pitfall 1: vCard 3.0 vs 4.0 Group Properties
**What goes wrong:** Using `KIND:group` and `MEMBER:` (vCard 4.0 / RFC 6350) instead of `X-ADDRESSBOOKSERVER-KIND:group` and `X-ADDRESSBOOKSERVER-MEMBER:` (Apple vCard 3.0 extension).
**Why it happens:** Training data and RFC 6350 describe the standard properties. Fastmail uses the Apple proprietary extensions because vCard 3.0 has no standard group mechanism.
**How to avoid:** Always use `X-ADDRESSBOOKSERVER-KIND` and `X-ADDRESSBOOKSERVER-MEMBER` for Fastmail. Verify with a manual test before writing any code.
**Warning signs:** Groups appear empty in Fastmail, contacts not routing correctly.

### Pitfall 2: ETag Quoting and Comparison
**What goes wrong:** ETags from headers may or may not include surrounding double quotes. Comparing `"abc123"` with `abc123` fails.
**Why it happens:** HTTP spec says ETags are opaque strings that may be quoted. Different servers handle quoting differently. The `If-Match` header must include the exact ETag string as returned by the server (including quotes if present).
**How to avoid:** Store ETags exactly as returned by the server. Pass them back in `If-Match` headers without modification. Never strip quotes.
**Warning signs:** 412 Precondition Failed on every PUT, even when no concurrent edit occurred.

### Pitfall 3: Addressbook Discovery vs Hardcoded URL
**What goes wrong:** Hardcoding `https://carddav.fastmail.com/dav/addressbooks/user/{email}/Default` breaks if the path changes or differs for custom domains.
**Why it happens:** Documentation shows the full URL, making it tempting to skip PROPFIND discovery.
**How to avoid:** Use PROPFIND-based discovery (current-user-principal -> addressbook-home-set -> addressbook). Cache the result for the session. Fall back to the known Fastmail default URL if discovery fails (defense in depth).
**Warning signs:** 404 errors on CardDAV operations.

### Pitfall 4: XML Namespace Handling in Responses
**What goes wrong:** ElementTree searches fail because namespace URIs are not included in element searches. `root.find("response")` returns None when the element is actually `{DAV:}response`.
**Why it happens:** WebDAV responses use XML namespaces extensively. ElementTree requires Clark notation `{namespace}element` or namespace maps for searches.
**How to avoid:** Always use the `{DAV:}` and `{urn:ietf:params:xml:ns:carddav}` prefixes in find/findall calls. Define namespace constants at module level.
**Warning signs:** Empty results from PROPFIND/REPORT parsing despite 207 responses with data.

### Pitfall 5: Duplicate Contact Creation on Retry
**What goes wrong:** Network timeout after PUT succeeds server-side. Client retries, creates a second contact with a different UID for the same sender.
**Why it happens:** PUT is not idempotent if the URL contains a new UUID each time.
**How to avoid:** Before creating, always search by email first (CDAV-02). Use `If-None-Match: *` on PUT to prevent overwriting if somehow a contact was already created. If PUT times out, search again before retrying.
**Warning signs:** Duplicate contacts appearing in Fastmail for the same sender.

### Pitfall 6: Group vCard Modification Race Condition
**What goes wrong:** Two triage operations try to add members to the same group simultaneously. Second PUT gets 412 because the first changed the ETag.
**Why it happens:** GET group vCard, modify, PUT back is not atomic. Another operation may modify the group between GET and PUT.
**How to avoid:** Handle 412 with retry: re-GET the group vCard (with fresh ETag), re-add the member, re-PUT. Limit retries (3 attempts). Since Phase 2 is single-threaded this is unlikely, but Phase 3 may introduce concurrency.
**Warning signs:** Intermittent 412 errors during group updates.

### Pitfall 7: vobject Property Name Case Sensitivity
**What goes wrong:** Accessing `card.X_ADDRESSBOOKSERVER_KIND` or `card.x-addressbookserver-kind` fails or returns None.
**Why it happens:** vobject normalizes property names by lowercasing and replacing hyphens with underscores. The property `X-ADDRESSBOOKSERVER-KIND` becomes accessible as `card.x_addressbookserver_kind`.
**How to avoid:** Test property access patterns against real Fastmail vCard data. Use `card.contents.get("x-addressbookserver-kind")` as a reliable fallback if attribute access is inconsistent.
**Warning signs:** KeyError or AttributeError when reading group vCards, groups not detected during validation.

## Code Examples

Verified patterns from official sources:

### Fastmail CardDAV Authentication
```python
# Source: Fastmail help (https://www.fastmail.help/hc/en-us/articles/1500000278342)
# Authentication uses HTTP Basic Auth with email + app password
import httpx

client = httpx.Client(
    auth=httpx.BasicAuth("user@example.com", "app-password-here"),
)

# Test connection with a simple PROPFIND
resp = client.request(
    "PROPFIND",
    "https://carddav.fastmail.com/",
    content=b"""<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:current-user-principal/>
  </D:prop>
</D:propfind>""",
    headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
)
# Expect 207 Multi-Status
```

### PROPFIND Discovery Chain
```python
# Source: sabre.io/dav/building-a-carddav-client/, RFC 6352
# Step 1: Find principal URL
PROPFIND_PRINCIPAL = """<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:current-user-principal/>
  </D:prop>
</D:propfind>"""

# Step 2: Find addressbook home
PROPFIND_AB_HOME = """<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <C:addressbook-home-set/>
  </D:prop>
</D:propfind>"""

# Step 3: List addressbooks in home (Depth: 1)
PROPFIND_ADDRESSBOOKS = """<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:resourcetype/>
    <D:displayname/>
  </D:prop>
</D:propfind>"""
```

### Contact vCard 3.0 Format
```
BEGIN:VCARD
VERSION:3.0
UID:550e8400-e29b-41d4-a716-446655440000
FN:Jane Smith
N:Smith;Jane;;;
EMAIL;TYPE=INTERNET:jane@example.com
NOTE:Added by Mailroom on 2026-02-24
END:VCARD
```

### Group vCard 3.0 Format (Fastmail/Apple Style)
```
BEGIN:VCARD
VERSION:3.0
UID:group-uid-12345
FN:Imbox
N:Imbox;;;;
X-ADDRESSBOOKSERVER-KIND:group
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:550e8400-e29b-41d4-a716-446655440000
X-ADDRESSBOOKSERVER-MEMBER:urn:uuid:660e8400-e29b-41d4-a716-446655440001
END:VCARD
```

### ETag-Protected PUT for Contact Update
```python
# Source: RFC 6352, sabre.io/dav/building-a-carddav-client/
def update_contact(self, href: str, etag: str, vcard_str: str) -> str:
    """Update existing contact with ETag concurrency protection.

    Returns new ETag on success.
    Raises PreconditionFailed on 412 (concurrent edit detected).
    """
    resp = self._http.put(
        f"https://{self._hostname}{href}",
        content=vcard_str.encode("utf-8"),
        headers={
            "Content-Type": "text/vcard; charset=utf-8",
            "If-Match": etag,
        },
    )
    if resp.status_code == 412:
        raise PreconditionFailed(href, etag)
    resp.raise_for_status()
    return resp.headers.get("etag", "")
```

### Merge-Cautious Contact Update
```python
# Source: User decision -- fill empty fields, never overwrite existing data
import vobject

def merge_contact(existing_vcard: str, new_email: str,
                  display_name: str) -> str:
    """Merge new data into existing contact, preserving existing fields.

    Only fills empty fields. Never overwrites name, phone, notes, etc.
    """
    card = vobject.readOne(existing_vcard)

    # Check if email already present (across all EMAIL properties)
    existing_emails = [
        e.value.lower()
        for e in card.contents.get("email", [])
    ]
    if new_email.lower() not in existing_emails:
        email_prop = card.add("email")
        email_prop.value = new_email
        email_prop.type_param = "INTERNET"

    # Only set FN/N if currently empty or missing
    if not hasattr(card, "fn") or not card.fn.value.strip():
        card.add("fn").value = display_name

    return card.serialize()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LDAP for contact management | CardDAV (RFC 6352) over HTTPS | 2011 (RFC published) | Standard protocol, works with all major providers |
| vCard 2.1 (Windows/Outlook) | vCard 3.0 (CardDAV mandatory), vCard 4.0 (RFC 6350) | 2006/2011 | 3.0 is the universal baseline for CardDAV |
| CATEGORIES for contact groups | X-ADDRESSBOOKSERVER-KIND:group (Apple) or KIND:group (vCard 4.0) | 2010s | Groups as separate vCards, proper membership tracking |
| `requests` library for HTTP | `httpx` for HTTP | 2020+ | Modern API, arbitrary method support (PROPFIND, REPORT) |
| Custom vCard string parsing | `vobject` library | 2006+ (mature) | Handles all vCard edge cases, actively maintained v1.0.0 |

**Deprecated/outdated:**
- `pyCardDAV`: Last meaningful release years ago, uses `requests`, unmaintained
- `caldav` library for contacts: Only supports CalDAV (calendars), not CardDAV (contacts)
- CATEGORIES-based groups: Fastmail uses Apple-style separate vCard groups, not CATEGORIES

## Open Questions

1. **Fastmail addressbook discovery exact path**
   - What we know: Fastmail docs show `https://carddav.fastmail.com/dav/addressbooks/user/{email}/Default` as the addressbook URL. PROPFIND-based discovery should also work (standard CardDAV).
   - What's unclear: Whether Fastmail fully supports the 3-step PROPFIND discovery chain, or if we should use the known URL directly.
   - Recommendation: Implement PROPFIND discovery first (correct, portable). If it fails, fall back to the documented Fastmail URL. The human test script will validate which approach works. **Confidence: MEDIUM** -- needs live testing.

2. **vobject handling of X-ADDRESSBOOKSERVER properties**
   - What we know: vobject parses arbitrary X-properties and stores them. Property names are normalized (lowercased, hyphens to underscores).
   - What's unclear: Exact attribute access pattern for `X-ADDRESSBOOKSERVER-KIND` and `X-ADDRESSBOOKSERVER-MEMBER`. May need `card.contents["x-addressbookserver-kind"]` list access.
   - Recommendation: Test with a real Fastmail group vCard in the human test script before building the full client. **Confidence: MEDIUM** -- needs live testing.

3. **Fastmail addressbook-query filter support for EMAIL**
   - What we know: RFC 6352 requires CardDAV servers to support prop-filter on standard vCard properties. Fastmail is a mature CardDAV implementation.
   - What's unclear: Whether Fastmail supports `match-type="equals"` on EMAIL prop-filter, or only `contains`. An `equals` match is more precise for duplicate detection.
   - Recommendation: Try `equals` first. If Fastmail doesn't support it, fall back to `contains` and filter client-side for exact match. **Confidence: MEDIUM** -- needs live testing.

4. **Config: CardDAV username source**
   - What we know: Fastmail CardDAV requires the full email address as username. The JMAP session may contain the email, or it could be a separate config value.
   - What's unclear: Whether deriving it from JMAP session is reliable for all account types (custom domains, aliases).
   - Recommendation: Add `MAILROOM_CARDDAV_USERNAME` as a required config value (full Fastmail email address). Simple, explicit, no magic. **Confidence: HIGH** -- straightforward.

## Sources

### Primary (HIGH confidence)
- [RFC 6352: CardDAV](https://www.rfc-editor.org/rfc/rfc6352) - addressbook-query REPORT, prop-filter, text-match syntax, ETag handling
- [sabre.io: Building a CardDAV Client](https://sabre.io/dav/building-a-carddav-client/) - Complete guide: discovery, PROPFIND, REPORT, PUT, sync, ETags
- [Fastmail: Server names and ports](https://www.fastmail.help/hc/en-us/articles/1500000278342) - CardDAV endpoint URL, authentication format, addressbook paths
- [Fastmail: Troubleshooting CardDAV fields](https://www.fastmail.help/hc/en-us/articles/360058753094) - vCard 3.0 as primary format, field handling
- [vobject documentation](https://vobject.readthedocs.io/latest/) - vCard creation, parsing, serialization API
- [DAVx5: Tested with Fastmail](https://www.davx5.com/tested-with/fastmail) - Confirms Fastmail uses "groups are separate vCards" model

### Secondary (MEDIUM confidence)
- [rcmcarddav GROUPS.md](https://github.com/mstilkerich/rcmcarddav/blob/master/doc/GROUPS.md) - X-ADDRESSBOOKSERVER-KIND:group format, vCard 3.0 vs 4.0 group properties
- [DAVx5 Technical Information](https://manual.davx5.com/technical_information.html) - Apple-style groups, X-ADDRESSBOOKSERVER-MEMBER format
- [vdirsyncer Fastmail tutorial](https://vdirsyncer.pimutils.org/en/stable/tutorials/fastmail.html) - Fastmail CardDAV endpoint, no known issues
- [Nylas sync-engine carddav.py](https://github.com/nylas/sync-engine/blob/master/inbox/contacts/carddav.py) - Python CardDAV implementation patterns (PROPFIND, lxml, requests)
- [carddav-util](https://github.com/ljanyst/carddav-util) - Python CardDAV utility using requests + vobject + lxml

### Tertiary (LOW confidence)
- Fastmail X-ADDRESSBOOKSERVER-KIND support: Confirmed by DAVx5 and community reports, but not explicitly documented in Fastmail's own docs. Needs live validation in Phase 2 human tests.
- vobject X-property access patterns: Documentation shows basic properties. X-ADDRESSBOOKSERVER handling inferred from library design. Needs live testing.
- Fastmail addressbook-query filter completeness: RFC 6352 compliance assumed. Match-type support (`equals` vs `contains`) needs live testing.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - httpx already proven (Phase 1), vobject is the de facto vCard library, xml.etree.ElementTree is stdlib. All verified via official docs.
- Architecture: HIGH - CardDAV protocol is well-specified via RFC 6352. Thin client pattern proven in Phase 1 with JMAP. Group model confirmed by multiple sources.
- Pitfalls: MEDIUM - Protocol pitfalls (ETags, namespaces, vCard format) well-documented. Fastmail-specific behaviors (group model, filter support) need live validation via human tests.

**Research date:** 2026-02-24
**Valid until:** 2026-03-24 (stable domain, 30 days)
