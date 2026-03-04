"""
Inspect raw vCard data for a contact — see exactly what fields exist.

Useful for understanding what Fastmail adds when you edit a contact
through their UI, and how _is_user_modified() detection works.

Usage:
    python .research/contact-modification/inspect_vcard.py "email@example.com"
    python .research/contact-modification/inspect_vcard.py "John Smith"  # search by name

Requires:
    - MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD in .env
    - pip install httpx vobject python-dotenv
"""

import sys
import httpx
import vobject
from dotenv import load_dotenv
import os
import xml.etree.ElementTree as ET

load_dotenv()

USERNAME = os.environ["MAILROOM_CARDDAV_USERNAME"]
PASSWORD = os.environ["MAILROOM_CARDDAV_PASSWORD"]
HOSTNAME = "carddav.fastmail.com"

# What Mailroom creates — anything else is "user-modified"
MAILROOM_MANAGED_FIELDS = {
    "version", "uid", "fn", "n", "email", "note", "org", "prodid",
}
SYSTEM_PREFIXES = ("x-addressbookserver-",)

DAV = "{DAV:}"
CARDDAV = "{urn:ietf:params:xml:ns:carddav}"

PROPFIND_PRINCIPAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:current-user-principal/></D:prop>
</D:propfind>"""

PROPFIND_AB_HOME = b"""<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop><C:addressbook-home-set/></D:prop>
</D:propfind>"""

REPORT_ALL = b"""<?xml version="1.0" encoding="UTF-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data/>
  </D:prop>
</C:addressbook-query>"""


def connect(http: httpx.Client) -> str:
    """Discover addressbook URL via PROPFIND chain."""
    resp = http.request(
        "PROPFIND",
        f"https://{HOSTNAME}/.well-known/carddav",
        content=PROPFIND_PRINCIPAL,
        headers={"Depth": "0"},
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    principal = root.findtext(f".//{DAV}current-user-principal/{DAV}href", "")

    resp = http.request(
        "PROPFIND",
        f"https://{HOSTNAME}{principal}",
        content=PROPFIND_AB_HOME,
        headers={"Depth": "0"},
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    home = root.findtext(f".//{CARDDAV}addressbook-home-set/{DAV}href", "")

    resp = http.request(
        "PROPFIND",
        f"https://{HOSTNAME}{home}",
        content=b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:resourcetype/></D:prop></D:propfind>',
        headers={"Depth": "1"},
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    for response in root.findall(f"{DAV}response"):
        href = response.findtext(f"{DAV}href", "")
        rt = response.find(f".//{DAV}resourcetype")
        if rt is not None and rt.find(f"{CARDDAV}addressbook") is not None:
            return f"https://{HOSTNAME}{href}"

    raise RuntimeError("No addressbook found")


def fetch_all(http: httpx.Client, ab_url: str) -> list[dict]:
    """Fetch all vCards from addressbook."""
    resp = http.request("REPORT", ab_url, content=REPORT_ALL, headers={"Depth": "1"})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    results = []
    for response in root.findall(f"{DAV}response"):
        href = response.findtext(f"{DAV}href", "")
        etag = response.findtext(f".//{DAV}getetag", "").strip('"')
        data = response.findtext(f".//{CARDDAV}address-data", "")
        if data:
            results.append({"href": href, "etag": etag, "vcard_data": data})
    return results


def analyze_vcard(vcard_data: str) -> dict:
    """Analyze a vCard and classify its fields."""
    card = vobject.readOne(vcard_data)
    all_keys = set(card.contents.keys())

    managed = set()
    system = set()
    user_added = set()

    for k in all_keys:
        kl = k.lower()
        if any(kl.startswith(p) for p in SYSTEM_PREFIXES):
            system.add(k)
        elif kl in MAILROOM_MANAGED_FIELDS:
            managed.add(k)
        else:
            user_added.add(k)

    email_count = len(card.contents.get("email", []))

    return {
        "managed": managed,
        "system": system,
        "user_added": user_added,
        "email_count": email_count,
        "is_user_modified": bool(user_added) or email_count > 1,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python inspect_vcard.py <email-or-name>")
        sys.exit(1)

    query = sys.argv[1].lower()

    http = httpx.Client(
        auth=httpx.BasicAuth(USERNAME, PASSWORD),
        headers={"Content-Type": "application/xml; charset=utf-8"},
        follow_redirects=True,
    )

    print(f"Connecting to {HOSTNAME}...")
    ab_url = connect(http)
    print(f"Addressbook: {ab_url}")
    print(f"Fetching contacts...")

    contacts = fetch_all(http, ab_url)
    print(f"Found {len(contacts)} vCards total\n")

    matches = []
    for c in contacts:
        try:
            card = vobject.readOne(c["vcard_data"])
        except Exception:
            continue

        # Skip groups
        kind = card.contents.get("x-addressbookserver-kind", [])
        if kind and kind[0].value.lower() == "group":
            continue

        fn = getattr(card, "fn", None)
        fn_val = fn.value if fn else ""
        emails = [e.value for e in card.contents.get("email", [])]

        if query in fn_val.lower() or any(query in e.lower() for e in emails):
            matches.append((fn_val, emails, c["vcard_data"]))

    if not matches:
        print(f"No contacts matching '{query}'")
        sys.exit(1)

    for fn_val, emails, vcard_data in matches:
        analysis = analyze_vcard(vcard_data)

        print("=" * 70)
        print(f"  {fn_val}")
        print(f"  {', '.join(emails)}")
        print("=" * 70)

        print(f"\n  Mailroom-managed fields: {sorted(analysis['managed'])}")
        print(f"  System fields (ignored): {sorted(analysis['system'])}")
        print(f"  User-added fields:       {sorted(analysis['user_added'])}")
        print(f"  Email count:             {analysis['email_count']}")
        print(f"\n  → is_user_modified = {analysis['is_user_modified']}")

        if analysis["user_added"]:
            print(f"\n  REASON: Extra fields detected: {sorted(analysis['user_added'])}")
        if analysis["email_count"] > 1:
            print(f"\n  REASON: Multiple EMAIL entries ({analysis['email_count']})")

        print(f"\n{'─' * 70}")
        print("  RAW VCARD:")
        print("─" * 70)
        for line in vcard_data.strip().splitlines():
            print(f"  {line}")
        print()


if __name__ == "__main__":
    main()
