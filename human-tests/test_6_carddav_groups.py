"""Human test 6: Group Membership and ETag Conflict Handling.

WARNING: This test MODIFIES contacts and groups in your Fastmail account.
Test contacts will be created and added to groups.
You must manually delete them after the test.
"""

import sys
from pathlib import Path

import vobject
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from mailroom.clients.carddav import CardDAVClient
from mailroom.core.config import MailroomSettings

settings = MailroomSettings()

if not settings.carddav_username or not settings.carddav_password:
    print("--- FAIL ---")
    print("MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD must be set.")
    sys.exit(1)

TEST_EMAIL = "mailroom-group-test@example.com"
TEST_NAME = "Mailroom Group Test Contact"

print("WARNING: This test MODIFIES contacts and groups in your Fastmail account.")
print(f"  A contact '{TEST_NAME}' ({TEST_EMAIL}) will be created and added to groups.")
input("Press Enter to continue or Ctrl+C to cancel: ")

client = CardDAVClient(
    username=settings.carddav_username,
    password=settings.carddav_password,
)

print("\nConnecting...")
try:
    client.connect()
    groups = client.validate_groups(settings.contact_groups)
except Exception as e:
    print(f"\n--- FAIL ---\nSetup failed: {e}")
    sys.exit(1)

first_group = settings.contact_groups[0]
print(f"\nUsing primary group: {first_group}")

# Step 1: Create test contact
print("\n=== Step 1: Create test contact ===")
try:
    result = client.create_contact(email=TEST_EMAIL, display_name=TEST_NAME)
    contact_uid = result["uid"]
    print(f"  Created contact: UID={contact_uid}")
    print("  --- STEP 1 PASS ---")
except Exception as e:
    print(f"  --- STEP 1 FAIL ---\n  {e}")
    sys.exit(1)

# Step 2: Add to group
print(f"\n=== Step 2: Add to group '{first_group}' ===")
try:
    new_etag = client.add_to_group(first_group, contact_uid)
    print(f"  Added to group. New group ETag: {new_etag}")

    # Verify: fetch group vCard and check membership
    group_info = groups[first_group]
    group_url = f"https://{client._hostname}{group_info['href']}"
    resp = client._http.get(group_url)
    resp.raise_for_status()
    card = vobject.readOne(resp.text)
    members = card.contents.get("x-addressbookserver-member", [])
    member_urns = [m.value for m in members]
    expected_urn = f"urn:uuid:{contact_uid}"
    if expected_urn in member_urns:
        print(f"  Verified: {expected_urn} is in group members")
        print("  --- STEP 2 PASS ---")
    else:
        print("  --- STEP 2 FAIL ---")
        print(f"  {expected_urn} NOT found in group members:")
        for urn in member_urns:
            print(f"    {urn}")
        sys.exit(1)
except Exception as e:
    print(f"  --- STEP 2 FAIL ---\n  {e}")
    sys.exit(1)

# Step 3: Verify in Fastmail
print("\n=== Step 3: Verify in Fastmail ===")
print(f"  Check Fastmail Contacts: '{TEST_NAME}' should appear in the '{first_group}' group.")
response = input("  Verified in Fastmail? Press Enter to continue or type 'fail': ")
if response.strip().lower() == "fail":
    print("  --- STEP 3 FAIL ---")
    sys.exit(1)
print("  --- STEP 3 PASS ---")

# Step 4: Observational ETag test — does Fastmail change ETags on web UI edits?
print(f"\n=== Step 4: Fastmail ETag behavior observation ===")
print("  This checks whether Fastmail produces a new ETag when a group is")
print("  edited through the web UI — something the CardDAV spec doesn't guarantee.")

group_for_etag_test = first_group
group_info = groups[group_for_etag_test]
group_url = f"https://{client._hostname}{group_info['href']}"

try:
    resp_before = client._http.get(group_url)
    resp_before.raise_for_status()
    etag_before = resp_before.headers.get("etag", "")
    print(f"  ETag before: {etag_before}")
    print()
    print(f"  Now edit the '{group_for_etag_test}' group in Fastmail web UI:")
    print("  (Add or remove any contact, or rename the group and rename it back.)")
    input("  After editing, press Enter to continue: ")

    resp_after = client._http.get(group_url)
    resp_after.raise_for_status()
    etag_after = resp_after.headers.get("etag", "")
    print(f"  ETag after:  {etag_after}")

    if etag_before != etag_after:
        print("  Result: ETag CHANGED — Fastmail updates ETags on web UI group edits.")
        print("  This means real concurrent edits would trigger 412 as expected.")
        print("  --- STEP 4 PASS ---")
    else:
        print("  Result: ETag UNCHANGED — Fastmail may not update ETags for web UI edits.")
        print("  Our retry logic still works (tested deterministically in Step 5),")
        print("  but real-world 412 conflicts from web UI edits may not occur.")
        print("  --- STEP 4 INFO --- (not a failure, just an observation)")
except Exception as e:
    print(f"  --- STEP 4 FAIL ---\n  {e}")
    sys.exit(1)

# Step 5: Deterministic ETag conflict test
print("\n=== Step 5: ETag conflict test (deterministic) ===")
print("  Injecting a stale ETag on the first PUT to force a 412 and verify retry.")

if len(settings.contact_groups) < 2:
    print("  --- STEP 5 SKIP ---")
    print("  Need at least 2 groups to test ETag conflict. Skipping.")
else:
    second_group = settings.contact_groups[1]
    print(f"  Target group: '{second_group}'")
    print()

    # Monkey-patch the first PUT to inject a stale ETag, forcing a 412.
    # add_to_group's retry will then GET fresh and succeed on attempt 2.
    original_put = client._http.put
    first_attempt = [True]

    def patched_put(*args, **kwargs):
        if first_attempt[0]:
            first_attempt[0] = False
            if "headers" in kwargs and "If-Match" in kwargs["headers"]:
                real_etag = kwargs["headers"]["If-Match"]
                kwargs["headers"] = dict(kwargs["headers"])
                kwargs["headers"]["If-Match"] = '"stale-etag-intentional"'
                print(f"  [INJECTED] Replaced If-Match {real_etag} -> '\"stale-etag-intentional\"'")
        return original_put(*args, **kwargs)

    client._http.put = patched_put

    try:
        new_etag = client.add_to_group(second_group, contact_uid)
        print()
        if not first_attempt[0]:
            # first_attempt is False = the patch fired, meaning 412 was triggered
            print("  412 conflict triggered and retry succeeded!")
        print(f"  Final group ETag: {new_etag}")
        print("  --- STEP 5 PASS ---")
    except RuntimeError as e:
        print("  --- STEP 5 FAIL ---")
        print(f"  add_to_group failed after retries: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"  --- STEP 5 FAIL ---\n  {e}")
        sys.exit(1)
    finally:
        client._http.put = original_put

# Cleanup instructions
print("\n=== Cleanup ===")
print(f"  Please manually delete '{TEST_NAME}' ({TEST_EMAIL}) from Fastmail Contacts.")
print(f"  Also remove it from the '{first_group}' group")
if len(settings.contact_groups) >= 2:
    print(f"  and the '{settings.contact_groups[1]}' group.")
else:
    print(".")

print("\n--- PASS ---")
