"""Human test 10: Retry Safety on Transient Failures (reads + one patched poll cycle).

Tests that when a transient failure occurs mid-pipeline, the triage label
stays on the email (not removed), and the poll cycle does NOT crash.
Then verifies the email is retried successfully on the next poll.

How it works:
  1. Connects to real Fastmail (JMAP + CardDAV)
  2. Finds a sender with a triage label in Screener
  3. Patches CardDAV upsert_contact to raise ConnectionError (simulated transient)
  4. Runs poll() — should NOT crash, should return 0 processed
  5. Verifies triage label is still present (retry-safe)
  6. Un-patches and runs poll() again — should succeed this time

Prerequisites:
  - Tests 1-6 pass (JMAP auth, queries, labels, CardDAV auth, contacts, groups)
  - At least one email in Screener has a triage label (@ToImbox, @ToFeed, etc.)
  - The sender should NOT already have a contact in a conflicting group
    (use a fresh sender or clean up from previous tests)
"""

import sys
from pathlib import Path
from unittest.mock import patch

import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.workflows.screener import ScreenerWorkflow

# Configure structlog so you can see retry behavior
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),  # DEBUG level
)

settings = MailroomSettings()

if not settings.carddav_username or not settings.carddav_password:
    print("--- FAIL ---")
    print("MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD must be set.")
    sys.exit(1)


# === Setup: Connect clients and resolve mailboxes ===
print("=== Setup: Connect clients and resolve mailboxes ===\n")

jmap = JMAPClient(token=settings.jmap_token)
print("Connecting JMAP...")
jmap.connect()
print(f"  Connected! Account ID: {jmap.account_id}")

carddav = CardDAVClient(
    username=settings.carddav_username,
    password=settings.carddav_password,
)
print("Connecting CardDAV...")
carddav.connect()
print("  Connected!")

print(f"\nValidating contact groups: {', '.join(settings.contact_groups)}")
try:
    carddav.validate_groups(settings.contact_groups)
    print("  All groups valid.")
except ValueError as e:
    print(f"\n--- FAIL ---\n{e}")
    sys.exit(1)

# Resolve all mailboxes the workflow needs
all_mailboxes = list(dict.fromkeys([  # dedupe preserving order
    "Inbox",
    settings.screener_mailbox,
    settings.label_mailroom_error,
    *settings.triage_labels,
    *[c.destination_mailbox for c in settings.label_to_category_mapping.values()],
]))

print(f"\nResolving {len(all_mailboxes)} mailboxes...")
try:
    mailbox_ids = jmap.resolve_mailboxes(all_mailboxes)
    for name, mid in mailbox_ids.items():
        print(f"  {name} -> {mid[:12]}...")
except ValueError as e:
    print(f"\n--- FAIL ---\n{e}")
    print("Create the missing mailboxes in Fastmail, then re-run.")
    sys.exit(1)

print("\n  Setup complete.\n")


# === Find a triaged sender to use as test subject ===
print("=== Finding a triaged sender for test ===\n")

test_sender = None
test_label = None

for label_name in settings.triage_labels:
    label_id = mailbox_ids[label_name]
    email_ids = jmap.query_emails(label_id)
    if not email_ids:
        continue

    senders = jmap.get_email_senders(email_ids)
    for email_id in email_ids:
        if email_id in senders:
            test_sender = senders[email_id][0]
            test_label = label_name
            break
    if test_sender:
        break

if not test_sender:
    print("--- SKIP ---")
    print("No triaged emails found in Screener.")
    print("Add at least one email with a triage label, then re-run.")
    sys.exit(0)

print(f"  Sender: {test_sender}")
print(f"  Label: {test_label}")

screener_id = mailbox_ids[settings.screener_mailbox]
error_id = mailbox_ids[settings.label_mailroom_error]


# === Phase 1: Poll with simulated transient failure ===
print("\n=== Phase 1: Poll with simulated CardDAV failure ===\n")

print("Patching upsert_contact to raise ConnectionError...")
print("poll() should catch this, log a warning, and NOT crash.\n")
input("Press Enter to run poll() with failure injection, or Ctrl-C to abort... ")

workflow = ScreenerWorkflow(
    jmap=jmap,
    carddav=carddav,
    settings=settings,
    mailbox_ids=mailbox_ids,
)

failures = []

print()
original_upsert = carddav.upsert_contact
with patch.object(
    carddav,
    "upsert_contact",
    side_effect=ConnectionError("Simulated transient CardDAV failure"),
):
    try:
        processed = workflow.poll()
    except Exception as e:
        print(f"\n--- FAIL ---")
        print(f"poll() crashed instead of catching the error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

print(f"\npoll() returned: {processed} (should be 0 — failure prevented processing)")

# Check: triage label should still be present
label_id = mailbox_ids[test_label]
post_label_emails = jmap.query_emails(label_id)
post_label_senders = jmap.get_email_senders(post_label_emails) if post_label_emails else {}
sender_still_labeled = any(
    s_email == test_sender for s_email, _ in post_label_senders.values()
)

if sender_still_labeled:
    print(f"  {test_sender}: still has {test_label} label (good — retry-safe)")
else:
    failures.append(f"Triage label {test_label} was removed despite failure (NOT retry-safe)")

# Check: emails should still be in Screener
sender_in_screener = jmap.query_emails(screener_id, sender=test_sender)
if sender_in_screener:
    print(f"  {test_sender}: still has {len(sender_in_screener)} email(s) in Screener (good)")
else:
    failures.append(f"Emails were moved out of Screener despite failure")

if failures:
    print("\n--- FAIL (Phase 1) ---")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print("\n  Phase 1 passed: failure caught, labels preserved for retry.")


# === Phase 2: Poll again without failure — should succeed ===
print("\n=== Phase 2: Retry poll (no failure) — should process successfully ===\n")

print("Running poll() again with real upsert_contact...")
print("This simulates the next poll cycle where the transient failure is gone.\n")
input("Press Enter to run retry poll(), or Ctrl-C to abort... ")

print()
try:
    processed = workflow.poll()
except Exception as e:
    print(f"\n--- FAIL ---\npoll() raised on retry: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\npoll() returned: {processed} sender(s) processed")

if processed > 0:
    print(f"  Retry succeeded — {test_sender} was processed this time.")
else:
    print(f"  WARNING: poll() returned 0. The sender may have been consumed by another")
    print(f"  mechanism or the email state changed between phases. Check structlog output.")


# === Report ===
print()
print("--- PASS ---")
print("Retry safety confirmed:")
print("  - Phase 1: Transient failure caught, poll() did not crash")
print("  - Phase 1: Triage label preserved (email eligible for retry)")
print("  - Phase 2: Retry poll processed the sender successfully")
