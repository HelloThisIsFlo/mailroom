"""Human test 5: Contact Create, Search, and Duplicate Prevention.

WARNING: This test CREATES contacts in your Fastmail account.
A test contact (mailroom-test@example.com) will be created.
You must manually delete it after the test.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from mailroom.clients.carddav import CardDAVClient
from mailroom.core.config import MailroomSettings

settings = MailroomSettings()

if not settings.carddav_username or not settings.carddav_password:
    print("--- FAIL ---")
    print("MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD must be set.")
    sys.exit(1)

TEST_EMAIL = "mailroom-test@example.com"
TEST_NAME = "Mailroom Test Contact"

print("WARNING: This test CREATES contacts in your Fastmail account.")
print(f"  A contact '{TEST_NAME}' ({TEST_EMAIL}) will be created.")
input("Press Enter to continue or Ctrl+C to cancel: ")

client = CardDAVClient(
    username=settings.carddav_username,
    password=settings.carddav_password,
)

print("\nConnecting...")
try:
    client.connect()
    client.validate_groups(settings.contact_groups)
except Exception as e:
    print(f"\n--- FAIL ---\nSetup failed: {e}")
    sys.exit(1)

# Step 1: Create test contact
print("\n=== Step 1: Create contact ===")
try:
    result = client.create_contact(email=TEST_EMAIL, display_name=TEST_NAME)
    print("  Created contact:")
    print(f"    UID:  {result['uid']}")
    print(f"    href: {result['href']}")
    print(f"    etag: {result['etag']}")
    print("  --- STEP 1 PASS ---")
except Exception as e:
    print(f"  --- STEP 1 FAIL ---\n  {e}")
    sys.exit(1)

# Step 2: Search for the test contact
print("\n=== Step 2: Search by email ===")
try:
    found = client.search_by_email(TEST_EMAIL)
    if len(found) == 0:
        print("  --- STEP 2 FAIL ---")
        print("  Search returned 0 results -- contact was created but not found.")
        sys.exit(1)
    if len(found) != 1:
        print("  --- STEP 2 FAIL ---")
        print(f"  Expected 1 result, got {len(found)}.")
        sys.exit(1)
    print(f"  Found {len(found)} contact:")
    print(f"    href: {found[0]['href']}")
    print(f"    etag: {found[0]['etag']}")
    print(f"    vcard preview: {found[0]['vcard_data'][:80]}...")
    print("  --- STEP 2 PASS ---")
except Exception as e:
    print(f"  --- STEP 2 FAIL ---\n  {e}")
    sys.exit(1)

# Step 3: Duplicate prevention
print("\n=== Step 3: Duplicate prevention ===")
try:
    # Search again -- should still find exactly one
    found_again = client.search_by_email(TEST_EMAIL)
    if len(found_again) != 1:
        print("  --- STEP 3 FAIL ---")
        print(f"  Second search found {len(found_again)} results (expected 1).")
        sys.exit(1)
    print(f"  Second search: {len(found_again)} result (correct)")

    # Upsert should NOT create a duplicate
    upsert_result = client.upsert_contact(
        TEST_EMAIL, TEST_NAME, settings.contact_groups[0]
    )
    print(f"  Upsert result: action={upsert_result['action']}, group={upsert_result['group']}")

    # Search once more -- should still be exactly one
    found_after_upsert = client.search_by_email(TEST_EMAIL)
    if len(found_after_upsert) != 1:
        print("  --- STEP 3 FAIL ---")
        print(f"  After upsert: {len(found_after_upsert)} results (expected 1).")
        sys.exit(1)
    print(f"  After upsert search: {len(found_after_upsert)} result (no duplicate)")
    print("  --- STEP 3 PASS ---")
except Exception as e:
    print(f"  --- STEP 3 FAIL ---\n  {e}")
    sys.exit(1)

# Step 4: Verify in Fastmail
print("\n=== Step 4: Verify in Fastmail ===")
print(f"  Now check Fastmail Contacts -- you should see '{TEST_NAME}'")
print(f"  with email {TEST_EMAIL}")
response = input("  Verified in Fastmail? Press Enter to continue or type 'fail': ")
if response.strip().lower() == "fail":
    print("  --- STEP 4 FAIL ---")
    sys.exit(1)
print("  --- STEP 4 PASS ---")

# Cleanup instructions
print("\n=== Cleanup ===")
print(f"  Please manually delete '{TEST_NAME}' ({TEST_EMAIL}) from Fastmail Contacts.")
print("  Also remove it from any groups it was added to.")

print("\n--- PASS ---")
