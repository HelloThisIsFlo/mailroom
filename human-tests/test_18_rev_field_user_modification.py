"""Human test 18: REV field user modification detection (CardDAV + Fastmail UI).

Validates an implicit dependency of _is_user_modified(): Fastmail adds a REV
timestamp field to any contact edited through their UI (web or mobile). Since
REV is NOT in MAILROOM_MANAGED_FIELDS, its presence triggers user-modification
detection. This is the key mechanism that makes provenance-aware reset safe --
contacts edited by the user get warned instead of deleted.

This test:
  1. Creates a test contact via CardDAV (programmatically)
  2. Fetches the vCard and records which fields are present
  3. Asks the human to edit the contact in Fastmail UI
  4. Re-fetches the vCard and checks if REV field appeared/changed
  5. Cleans up the test contact

Prerequisites:
  - Tests 4-5 pass (CardDAV auth and contact operations)
  - MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD set
  - Access to Fastmail web UI or mobile app

Expected result:
  After editing the contact in Fastmail UI, the re-fetched vCard should
  contain a REV field that was not present (or has changed) from the
  original programmatically-created version.
"""

import sys
from pathlib import Path

import vobject
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mailroom.clients.carddav import CardDAVClient
from mailroom.core.config import MailroomSettings
from mailroom.reset.resetter import MAILROOM_MANAGED_FIELDS, _is_user_modified

TEST_CONTACT_EMAIL = "rev-field-test@mailroom-test.example.com"
TEST_CONTACT_NAME = "REV Field Test (Mailroom)"

settings = MailroomSettings()

if not settings.carddav_username or not settings.carddav_password:
    print("--- FAIL ---")
    print("MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD must be set.")
    sys.exit(1)


# === Setup: Connect CardDAV ===
print("=== Setup: Connect CardDAV ===\n")

carddav = CardDAVClient(
    username=settings.carddav_username,
    password=settings.carddav_password,
)
print("Connecting CardDAV...")
carddav.connect()
print("  Connected!")


# === Step 1: Create a test contact ===
print("\n=== Step 1: Create test contact ===\n")

# Check if test contact already exists (from a previous failed run)
existing = carddav.search_by_email(TEST_CONTACT_EMAIL)
if existing:
    print(f"  Found existing test contact, cleaning up first...")
    for contact in existing:
        try:
            carddav.delete_contact(contact["href"], contact["etag"])
            print(f"  Deleted: {contact['href']}")
        except Exception as e:
            print(f"  Warning: Could not delete {contact['href']}: {e}")

# Create fresh contact
result = carddav.create_contact(
    TEST_CONTACT_EMAIL,
    TEST_CONTACT_NAME,
    group_name=settings.contact_groups[0],  # add to first group for valid creation
)
contact_uid = result["uid"]
contact_href = result["href"]
print(f"  Created contact: {TEST_CONTACT_NAME}")
print(f"  UID: {contact_uid}")
print(f"  href: {contact_href}")


# === Step 2: Fetch and record initial vCard fields ===
print("\n=== Step 2: Fetch initial vCard ===\n")

contacts = carddav.search_by_email(TEST_CONTACT_EMAIL)
if not contacts:
    print("--- FAIL ---")
    print("Could not find the contact we just created!")
    sys.exit(1)

initial_vcard_data = contacts[0]["vcard_data"]
initial_card = vobject.readOne(initial_vcard_data)
initial_fields = {k.lower() for k in initial_card.contents.keys()}

print(f"  Initial vCard fields: {sorted(initial_fields)}")
print(f"  REV present initially: {'rev' in initial_fields}")
print(f"  _is_user_modified() initially: {_is_user_modified(initial_vcard_data)}")

initial_rev = None
if "rev" in initial_fields:
    initial_rev = initial_card.contents["rev"][0].value
    print(f"  Initial REV value: {initial_rev}")

initial_etag = contacts[0]["etag"]


# === Step 3: Ask human to edit the contact ===
print("\n=== Step 3: Edit the contact in Fastmail UI ===\n")

print("  Please edit this contact in Fastmail's web UI or mobile app:")
print(f"  Contact name: {TEST_CONTACT_NAME}")
print(f"  Contact email: {TEST_CONTACT_EMAIL}")
print()
print("  Suggested edits (any one will do):")
print("    - Add a phone number")
print("    - Add a note")
print("    - Change the display name slightly")
print()
print("  After saving the edit in Fastmail, press Enter here to continue.")
print()
input("  Press Enter when you have edited and saved the contact... ")


# === Step 4: Re-fetch and check for REV field ===
print("\n=== Step 4: Re-fetch vCard and check REV field ===\n")

contacts_after = carddav.search_by_email(TEST_CONTACT_EMAIL)
if not contacts_after:
    print("--- FAIL ---")
    print("Could not find the contact after editing!")
    sys.exit(1)

after_vcard_data = contacts_after[0]["vcard_data"]
after_card = vobject.readOne(after_vcard_data)
after_fields = {k.lower() for k in after_card.contents.keys()}

print(f"  After-edit vCard fields: {sorted(after_fields)}")
print(f"  REV present after edit: {'rev' in after_fields}")
print(f"  _is_user_modified() after edit: {_is_user_modified(after_vcard_data)}")

after_rev = None
if "rev" in after_fields:
    after_rev = after_card.contents["rev"][0].value
    print(f"  After REV value: {after_rev}")

# Determine new fields added by the edit
new_fields = after_fields - initial_fields
extra_beyond_managed = after_fields - MAILROOM_MANAGED_FIELDS
print(f"  New fields added by edit: {sorted(new_fields) if new_fields else 'none'}")
print(f"  Fields beyond managed set: {sorted(extra_beyond_managed)}")


# === Step 5: Evaluate result ===
print("\n=== Step 5: Evaluate ===\n")

passes = []
failures = []

# Check 1: REV field should be present after edit
if "rev" in after_fields:
    passes.append("REV field is present after Fastmail UI edit")
    print("  PASS: REV field is present after edit")
else:
    failures.append("REV field NOT present after Fastmail UI edit")
    print("  FAIL: REV field NOT present after edit")

# Check 2: If REV was present before, it should have changed
if initial_rev and after_rev:
    if after_rev != initial_rev:
        passes.append(f"REV field changed: {initial_rev} -> {after_rev}")
        print(f"  PASS: REV field changed ({initial_rev} -> {after_rev})")
    else:
        failures.append(f"REV field did NOT change (still {initial_rev})")
        print(f"  FAIL: REV field did NOT change")

# Check 3: _is_user_modified should return True after edit
if _is_user_modified(after_vcard_data):
    passes.append("_is_user_modified() returns True after Fastmail UI edit")
    print("  PASS: _is_user_modified() returns True")
else:
    failures.append("_is_user_modified() returns False after Fastmail UI edit")
    print("  FAIL: _is_user_modified() returns False")

# Check 4: REV should NOT be in MAILROOM_MANAGED_FIELDS
if "rev" not in MAILROOM_MANAGED_FIELDS:
    passes.append("REV is not in MAILROOM_MANAGED_FIELDS (by design)")
    print("  PASS: REV is not in MAILROOM_MANAGED_FIELDS")
else:
    failures.append("REV is in MAILROOM_MANAGED_FIELDS (should not be!)")
    print("  FAIL: REV is in MAILROOM_MANAGED_FIELDS")


# === Step 6: Clean up ===
print("\n=== Step 6: Clean up ===\n")

try:
    # Re-fetch to get current etag after edit
    cleanup_contacts = carddav.search_by_email(TEST_CONTACT_EMAIL)
    if cleanup_contacts:
        carddav.delete_contact(cleanup_contacts[0]["href"], cleanup_contacts[0]["etag"])
        print(f"  Deleted test contact: {TEST_CONTACT_NAME}")
    else:
        print("  Test contact not found for cleanup (may have been deleted)")
except Exception as e:
    print(f"  Warning: Could not clean up test contact: {e}")
    print(f"  You may need to manually delete '{TEST_CONTACT_NAME}' from Fastmail.")


# === Report ===
print()
if failures:
    print("--- FAIL ---")
    print(f"  {len(passes)} checks passed, {len(failures)} checks failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("--- PASS ---")
    print(f"  All {len(passes)} checks passed:")
    for p in passes:
        print(f"  - {p}")
    print()
    print("This confirms Fastmail adds REV on contact edits, which is the")
    print("mechanism _is_user_modified() relies on for provenance-aware reset.")
