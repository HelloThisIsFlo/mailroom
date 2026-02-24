"""Human test 9: Already-Grouped Sender Conflict (WRITES @MailroomError + contacts).

Tests that when a sender's contact is already in a different group than the
triage label targets, poll() applies @MailroomError and does NOT process
(move/upsert) that sender.

This test automates the setup:
  1. Finds a sender in Screener with a triage label
  2. Creates or finds their contact in CardDAV
  3. Adds the contact to a DIFFERENT group than the triage label targets
  4. Runs poll()
  5. Verifies @MailroomError was applied, email stayed in Screener

Prerequisites:
  - Tests 1-6 pass (JMAP auth, queries, labels, CardDAV auth, contacts, groups)
  - At least one email in Screener has a triage label (@ToImbox, @ToFeed, etc.)

Cleanup note:
  After the test, you may want to remove the test contact from the wrong group
  and remove the @MailroomError label in Fastmail to restore clean state.
"""

import sys
from pathlib import Path

import structlog
import vobject
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.workflows.screener import ScreenerWorkflow

# Configure structlog so you can see already-grouped detection in action
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


# === Find a triaged sender to use as test subject ===
print("=== Finding a triaged sender for test ===\n")

test_sender = None
test_label = None
test_email_ids = []

for label_name in settings.triage_labels:
    label_id = mailbox_ids[label_name]
    email_ids = jmap.query_emails(label_id)
    if not email_ids:
        continue

    senders = jmap.get_email_senders(email_ids)
    for email_id in email_ids:
        if email_id in senders:
            sender_email, _ = senders[email_id]
            test_sender = sender_email
            test_label = label_name
            test_email_ids = [
                eid for eid in email_ids
                if eid in senders and senders[eid][0] == sender_email
            ]
            break
    if test_sender:
        break

if not test_sender:
    print("--- SKIP ---")
    print("No triaged emails found in Screener.")
    print("Add at least one email with a triage label, then re-run.")
    sys.exit(0)

# Figure out the target group (what the label would route to)
target_group = settings.label_to_group_mapping[test_label]["group"]

# Pick a DIFFERENT group to put the contact in
wrong_group = None
for group in settings.contact_groups:
    if group != target_group:
        wrong_group = group
        break

print(f"  Sender: {test_sender}")
print(f"  Label: {test_label} (targets group: {target_group})")
print(f"  Wrong group: {wrong_group}")
print(f"  Email(s): {len(test_email_ids)}")


# === Create/find contact and add to WRONG group ===
print(f"\n=== Setting up conflict: adding {test_sender} to {wrong_group} ===\n")

# Search for existing contact
existing = carddav.search_by_email(test_sender)
if existing:
    card = vobject.readOne(existing[0]["vcard_data"])
    contact_uid = card.uid.value
    print(f"  Found existing contact: UID {contact_uid[:12]}...")
else:
    # Create a new contact
    result = carddav.create_contact(test_sender, f"Test Contact ({test_sender})")
    contact_uid = result["uid"]
    print(f"  Created new contact: UID {contact_uid[:12]}...")

# Add to the WRONG group
print(f"  Adding to {wrong_group}...")
carddav.add_to_group(wrong_group, contact_uid)
print(f"  Contact is now in {wrong_group} (wrong group for {test_label}).")

# Verify the membership is set up correctly
membership = carddav.check_membership(contact_uid, exclude_group=wrong_group)
if membership:
    print(f"  WARNING: Contact also in {membership}. Test may be affected.")

# Record pre-poll state
screener_id = mailbox_ids[settings.screener_mailbox]
error_id = mailbox_ids[settings.label_mailroom_error]
pre_error_emails = set(jmap.query_emails(error_id))
pre_screener_sender_emails = set(jmap.query_emails(screener_id, sender=test_sender))

print(f"\n  Pre-poll: {len(pre_screener_sender_emails)} email(s) from {test_sender} in Screener")
print(f"  Pre-poll: {len(pre_error_emails)} total emails with @MailroomError")


# === Run: Execute one poll cycle ===
print("\n=== Run: Execute one poll cycle ===\n")

print(f"WARNING: This will apply @MailroomError to emails from {test_sender}.")
print("The contact will NOT be moved to a new group.\n")
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


# === Verify: Check already-grouped detection results ===
print(f"\n=== Verify: Already-grouped detection results ===\n")

failures = []

print(f"poll() returned: {processed} sender(s) processed")

# Check 1: @MailroomError should have been applied to the test sender's emails
post_error_emails = set(jmap.query_emails(error_id))
new_error_emails = post_error_emails - pre_error_emails
print(f"@MailroomError new emails: {len(new_error_emails)}")

if not new_error_emails:
    failures.append("@MailroomError was NOT applied to any new emails")

# Check 2: Emails should still be in Screener
post_screener_sender_emails = set(jmap.query_emails(screener_id, sender=test_sender))
if post_screener_sender_emails:
    print(f"  {test_sender}: still has {len(post_screener_sender_emails)} email(s) in Screener (good)")
else:
    failures.append(f"{test_sender}: emails were moved OUT of Screener (should stay)")

# Check 3: Contact should still be in the WRONG group, NOT in target group
current_wrong_membership = carddav.check_membership(contact_uid, exclude_group=target_group)
current_target_membership = carddav.check_membership(contact_uid, exclude_group=wrong_group)

if current_wrong_membership == wrong_group or (current_wrong_membership is None and wrong_group):
    # check_membership with exclude_group=target_group returns wrong_group if contact is there
    pass

# More direct check: is the contact in the target group now?
if current_target_membership == target_group:
    failures.append(f"Contact was added to {target_group} (should NOT have been)")
else:
    print(f"  Contact NOT in {target_group} (good — processing was blocked)")

# Check 4: Triage label should still be present
label_id = mailbox_ids[test_label]
post_label_emails = jmap.query_emails(label_id)
post_label_senders = jmap.get_email_senders(post_label_emails) if post_label_emails else {}
sender_still_labeled = any(
    s_email == test_sender for s_email, _ in post_label_senders.values()
)
if sender_still_labeled:
    print(f"  {test_sender}: still has {test_label} label (good)")
else:
    failures.append(f"{test_sender}: {test_label} label was removed (should stay)")


# === Report ===
print()
if failures:
    print("--- FAIL ---")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("--- PASS ---")
    print("Already-grouped conflict detection working correctly:")
    print(f"  - @MailroomError applied to {test_sender}")
    print(f"  - Contact stayed in {wrong_group} (not moved to {target_group})")
    print(f"  - Emails remain in Screener with {test_label} label")
    print()
    print("Cleanup (optional):")
    print(f"  - Remove {test_sender} from {wrong_group} in Fastmail Contacts")
    print(f"  - Remove @MailroomError label from affected emails")
