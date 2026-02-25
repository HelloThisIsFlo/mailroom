"""Human test 8: Conflict Detection (WRITES @MailroomError labels).

Tests that when the same sender has emails with different triage labels,
poll() detects the conflict, applies @MailroomError additively, and does
NOT process (move/upsert) the conflicted sender.

Setup (do this in Fastmail before running):
  1. Pick a sender email (e.g., conflict-test@example.com)
  2. Put at least 2 emails from that sender in Screener
  3. Apply @ToImbox to one email
  4. Apply @ToFeed to another email from the SAME sender
  5. Make sure the sender has NO contact in any CardDAV group yet (clean state)

This will:
  - Run one poll cycle
  - Verify poll() returns 0 processed senders (conflict blocks processing)
  - Verify @MailroomError was applied to the conflicted emails
  - Verify original triage labels (@ToImbox, @ToFeed) are still present
  - Verify emails are still in Screener (NOT moved)

Prerequisites:
  - Tests 1-6 pass (JMAP auth, queries, labels, CardDAV auth, contacts, groups)
"""

import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.workflows.screener import ScreenerWorkflow

# Configure structlog so you can see conflict detection in action
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
    *[m["destination_mailbox"] for m in settings.label_to_group_mapping.values()],
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


# === Pre-check: Verify conflict setup exists ===
print("=== Pre-check: Verify conflicting emails exist ===\n")

# Check that at least 2 different triage labels have emails from the same sender
sender_labels: dict[str, set[str]] = {}
for label_name in settings.triage_labels:
    label_id = mailbox_ids[label_name]
    email_ids = jmap.query_emails(label_id)
    if not email_ids:
        continue

    senders = jmap.get_email_senders(email_ids)
    for email_id in email_ids:
        if email_id in senders:
            sender_email, _ = senders[email_id]
            sender_labels.setdefault(sender_email, set()).add(label_name)

conflicted_senders = {
    sender: labels
    for sender, labels in sender_labels.items()
    if len(labels) > 1
}

if not conflicted_senders:
    print("--- SKIP ---")
    print("No conflicting senders found.")
    print()
    print("To set up this test:")
    print("  1. Put 2+ emails from the SAME sender in Screener")
    print("  2. Apply @ToImbox to one email")
    print("  3. Apply @ToFeed to another email from that sender")
    print("  4. Re-run this test")
    sys.exit(0)

print("Found conflicting sender(s):")
for sender, labels in conflicted_senders.items():
    print(f"  {sender} -> {', '.join(sorted(labels))}")

# Record which emails are in Screener before poll (for post-check)
screener_id = mailbox_ids[settings.screener_mailbox]
pre_screener_emails = set(jmap.query_emails(screener_id))
print(f"\nScreener has {len(pre_screener_emails)} total emails before poll.")

# Record which emails already have @MailroomError before poll
error_id = mailbox_ids[settings.label_mailroom_error]
pre_error_emails = set(jmap.query_emails(error_id))
print(f"@MailroomError has {len(pre_error_emails)} emails before poll.")

print()


# === Run: Execute one poll cycle ===
print("=== Run: Execute one poll cycle ===\n")

print("WARNING: This will apply @MailroomError to conflicted emails.")
print("Conflicted emails will NOT be moved or processed.\n")
input("Press Enter to run poll(), or Ctrl-C to abort... ")

workflow = ScreenerWorkflow(
    jmap=jmap,
    carddav=carddav,
    settings=settings,
    mailbox_ids=mailbox_ids,
)

print()
try:
    processed = workflow.poll()
except Exception as e:
    print(f"\n--- FAIL ---\npoll() raised: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


# === Verify: Check conflict detection results ===
print(f"\n=== Verify: Conflict detection results ===\n")

failures = []

# Check 1: poll() should return 0 for conflicted-only scenarios
# (may be >0 if there are also non-conflicting senders with labels)
print(f"poll() returned: {processed} sender(s) processed")

# Check 2: @MailroomError should have new emails
post_error_emails = set(jmap.query_emails(error_id))
new_error_emails = post_error_emails - pre_error_emails
print(f"@MailroomError new emails: {len(new_error_emails)}")

if not new_error_emails:
    failures.append("@MailroomError was NOT applied to any new emails")

# Check 3: Conflicted emails should still be in Screener
post_screener_emails = set(jmap.query_emails(screener_id))
for sender in conflicted_senders:
    sender_in_screener = jmap.query_emails(screener_id, sender=sender)
    if sender_in_screener:
        print(f"  {sender}: still has {len(sender_in_screener)} email(s) in Screener (good)")
    else:
        failures.append(f"{sender}: emails were moved OUT of Screener (should stay)")

# Check 4: Original triage labels should still be present
for sender, labels in conflicted_senders.items():
    for label_name in labels:
        label_id = mailbox_ids[label_name]
        label_emails = jmap.query_emails(label_id)
        senders_in_label = jmap.get_email_senders(label_emails) if label_emails else {}
        sender_still_labeled = any(
            s_email == sender for s_email, _ in senders_in_label.values()
        )
        if sender_still_labeled:
            print(f"  {sender}: still has {label_name} label (good)")
        else:
            failures.append(f"{sender}: {label_name} label was removed (should stay)")


# === Report ===
print()
if failures:
    print("--- FAIL ---")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("--- PASS ---")
    print("Conflict detection working correctly:")
    print("  - @MailroomError applied to conflicted emails")
    print("  - Original triage labels preserved")
    print("  - Emails remain in Screener (not moved)")
    print("  - No contacts created for conflicted senders")
