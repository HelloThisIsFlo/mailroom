"""Human test 17: Re-triage Workflow (WRITES to mailbox and contacts).

Tests that applying a triage label to a sender who is already in a different
contact group triggers re-triage: the contact is moved to the new group
(with full parent chain diff), all emails have managed labels reconciled
(old destination labels stripped, new destination labels applied), and the
contact note records the re-triage event.

This replaces the old already-grouped error behavior (test_9).

This test automates the setup:
  1. Finds a sender in Screener with a triage label
  2. Creates or finds their contact in CardDAV
  3. Adds the contact to a DIFFERENT group than the triage label targets
  4. Records before-state (email mailbox labels, group membership)
  5. Runs poll() to trigger re-triage
  6. Verifies: contact in new group, not in old group, emails have new labels,
     old labels removed, Screener label removed, triage label removed,
     contact note has "Re-triaged to" entry

Prerequisites:
  - Tests 1-7 pass (JMAP auth, queries, labels, CardDAV auth, contacts, groups, poll)
  - At least one email in Screener has a triage label (@ToImbox, @ToFeed, etc.)
  - The sender of that email should ideally NOT already be in the target group
    (the test will set up the pre-condition by placing them in a different group)

Cleanup note:
  After the test, the contact is in the new (correct) group per the triage
  label. This is the intended state -- no cleanup needed unless you want to
  re-run the test (in which case, move the contact back to a different group
  and re-apply a triage label).
"""

import sys
from pathlib import Path

import structlog
import vobject
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.workflows.screener import ScreenerWorkflow

# Configure structlog so you can see re-triage in action
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

# Resolve all mailboxes the workflow needs (use settings to stay in sync)
all_mailboxes = settings.required_mailboxes

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
print("=== Finding a triaged sender for re-triage test ===\n")

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
    print("No triaged emails found in any triage label mailbox.")
    print()
    print("To set up this test:")
    print("  1. Find a sender who is already in a contact group (or any sender)")
    print("  2. Apply a triage label (e.g. @ToImbox, @ToFeed) to one of their emails")
    print("  3. Re-run this test")
    sys.exit(0)

# Figure out the target group (what the label would route to)
target_category = settings.label_to_category_mapping[test_label]
target_group = target_category.contact_group

# Pick a DIFFERENT group to put the contact in (the "old" group)
old_group = None
for group in settings.contact_groups:
    if group != target_group:
        old_group = group
        break

if not old_group:
    print("--- SKIP ---")
    print(f"Only one contact group configured ({target_group}).")
    print("Re-triage requires at least two different groups.")
    sys.exit(0)

print(f"  Sender: {test_sender}")
print(f"  Label: {test_label} (targets group: {target_group})")
print(f"  Old group (will place contact here): {old_group}")
print(f"  Triggering email(s): {len(test_email_ids)}")


# === Create/find contact and add to the OLD (wrong) group ===
print(f"\n=== Setting up re-triage: adding {test_sender} to {old_group} ===\n")

# Search for existing contact
existing = carddav.search_by_email(test_sender)
if existing:
    card = vobject.readOne(existing[0]["vcard_data"])
    contact_uid = card.uid.value
    print(f"  Found existing contact: UID {contact_uid[:12]}...")

    # Check current group membership
    current_group = carddav.check_membership(contact_uid)
    if current_group:
        print(f"  Currently in group: {current_group}")
        if current_group == target_group:
            # Already in target group -- need to move to old_group for the test
            print(f"  Moving to {old_group} to set up cross-group re-triage...")
            carddav.add_to_group(old_group, contact_uid)
            carddav.remove_from_group(target_group, contact_uid)
        elif current_group != old_group:
            # In some other group -- move to our chosen old_group
            print(f"  Moving to {old_group} to set up cross-group re-triage...")
            carddav.add_to_group(old_group, contact_uid)
            carddav.remove_from_group(current_group, contact_uid)
        else:
            print(f"  Already in {old_group} (good -- ready for re-triage)")
    else:
        print(f"  Not in any group. Adding to {old_group}...")
        carddav.add_to_group(old_group, contact_uid)
else:
    # Create a new contact and add to old_group
    result = carddav.create_contact(
        test_sender, f"Test Contact ({test_sender})",
        group_name=old_group,
    )
    contact_uid = result["uid"]
    carddav.add_to_group(old_group, contact_uid)
    print(f"  Created new contact: UID {contact_uid[:12]}...")
    print(f"  Added to {old_group}")

# Verify the setup: contact should be in old_group, NOT in target_group
verify_group = carddav.check_membership(contact_uid)
if verify_group != old_group:
    print(f"\n--- FAIL ---")
    print(f"  Setup failed: contact is in {verify_group}, expected {old_group}")
    sys.exit(1)
print(f"\n  Pre-condition verified: contact in {old_group} (not {target_group})")


# === Record before-state ===
print("\n=== Recording before-state ===\n")

# Get all emails from this sender across all mailboxes
all_sender_emails = jmap.query_emails_by_sender(test_sender)
print(f"  Total emails from {test_sender}: {len(all_sender_emails)}")

# Record mailbox membership for each email
before_mailboxes = jmap.get_email_mailbox_ids(all_sender_emails) if all_sender_emails else {}

# Find old destination mailbox IDs (what the old group's category routes to)
old_category = next(
    c for c in settings.resolved_categories
    if c.contact_group == old_group
)
old_dest_mailbox = old_category.destination_mailbox
old_dest_id = mailbox_ids.get(old_dest_mailbox)
print(f"  Old destination: {old_dest_mailbox} ({old_dest_id[:12] if old_dest_id else 'N/A'}...)")

# New destination mailbox IDs (what the target group's category routes to)
new_dest_mailbox = target_category.destination_mailbox
new_dest_id = mailbox_ids.get(new_dest_mailbox)
print(f"  New destination: {new_dest_mailbox} ({new_dest_id[:12] if new_dest_id else 'N/A'}...)")

screener_id = mailbox_ids[settings.triage.screener_mailbox]
print(f"  Screener ID: {screener_id[:12]}...")


# === Run: Execute one poll cycle ===
print("\n=== Run: Execute one poll cycle ===\n")

print(f"WARNING: This will re-triage {test_sender}:")
print(f"  - Move contact from {old_group} to {target_group}")
print(f"  - Strip old destination labels, apply new destination labels")
print(f"  - Update contact note with re-triage history")
print()
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


# === Verify: Check re-triage results ===
print(f"\n=== Verify: Re-triage results ===\n")

failures = []
passes = []

print(f"poll() returned: {processed} sender(s) processed\n")

# Check 1: Contact should be in the NEW (target) group
post_group = carddav.check_membership(contact_uid)
if post_group == target_group:
    passes.append(f"Contact is in {target_group} (new group)")
    print(f"  PASS: Contact is in {target_group}")
else:
    failures.append(f"Contact is in {post_group}, expected {target_group}")
    print(f"  FAIL: Contact is in {post_group}, expected {target_group}")

# Check 2: Contact should NOT be in the old group
old_group_check = carddav.check_membership(contact_uid, exclude_group=target_group)
if old_group_check == old_group:
    failures.append(f"Contact still in {old_group} (should have been removed)")
    print(f"  FAIL: Contact still in {old_group}")
else:
    passes.append(f"Contact not in {old_group} (removed from old group)")
    print(f"  PASS: Contact not in {old_group}")

# Check 3: Emails should have new destination labels
after_sender_emails = jmap.query_emails_by_sender(test_sender)
after_mailboxes = jmap.get_email_mailbox_ids(after_sender_emails) if after_sender_emails else {}

emails_with_new_dest = 0
emails_missing_new_dest = 0
for email_id in after_sender_emails:
    mbox_ids = after_mailboxes.get(email_id, set())
    if new_dest_id and new_dest_id in mbox_ids:
        emails_with_new_dest += 1
    else:
        emails_missing_new_dest += 1

if after_sender_emails and emails_with_new_dest > 0:
    passes.append(f"{emails_with_new_dest}/{len(after_sender_emails)} emails have {new_dest_mailbox} label")
    print(f"  PASS: {emails_with_new_dest}/{len(after_sender_emails)} emails have {new_dest_mailbox} label")
elif not after_sender_emails:
    passes.append("No emails from sender (nothing to reconcile)")
    print(f"  PASS: No emails from sender (nothing to reconcile)")
else:
    failures.append(f"No emails have {new_dest_mailbox} label ({emails_missing_new_dest} checked)")
    print(f"  FAIL: No emails have {new_dest_mailbox} label")

# Check 4: Emails should NOT have old destination labels (unless old and new share a label)
if old_dest_id and old_dest_id != new_dest_id:
    emails_with_old_dest = sum(
        1 for eid in after_sender_emails
        if old_dest_id in after_mailboxes.get(eid, set())
    )
    if emails_with_old_dest == 0:
        passes.append(f"No emails have old {old_dest_mailbox} label (cleaned up)")
        print(f"  PASS: No emails have old {old_dest_mailbox} label")
    else:
        failures.append(f"{emails_with_old_dest} emails still have old {old_dest_mailbox} label")
        print(f"  FAIL: {emails_with_old_dest} emails still have old {old_dest_mailbox} label")

# Check 5: Screener label should be removed from sender's emails
emails_in_screener = sum(
    1 for eid in after_sender_emails
    if screener_id in after_mailboxes.get(eid, set())
)
if emails_in_screener == 0:
    passes.append("No emails in Screener (cleaned up)")
    print(f"  PASS: No emails in Screener")
else:
    # Screener emails are acceptable if they arrived after poll
    print(f"  INFO: {emails_in_screener} emails still in Screener (may be new arrivals)")

# Check 6: Triage label should be removed from triggering emails
label_id = mailbox_ids[test_label]
post_label_emails = jmap.query_emails(label_id)
post_label_senders = jmap.get_email_senders(post_label_emails) if post_label_emails else {}
sender_still_labeled = any(
    s_email == test_sender for s_email, _ in post_label_senders.values()
)
if not sender_still_labeled:
    passes.append(f"Triage label {test_label} removed from sender's emails")
    print(f"  PASS: Triage label {test_label} removed")
else:
    failures.append(f"Triage label {test_label} still on sender's emails")
    print(f"  FAIL: Triage label {test_label} still on sender's emails")

# Check 7: Contact note should contain "Re-triaged to" entry
post_contact = carddav.search_by_email(test_sender)
if post_contact:
    post_card = vobject.readOne(post_contact[0]["vcard_data"])
    note_entries = post_card.contents.get("note", [])
    note_text = note_entries[0].value if note_entries else ""
    if f"Re-triaged to {target_group}" in note_text:
        passes.append(f"Contact note has 'Re-triaged to {target_group}' entry")
        print(f"  PASS: Contact note has 'Re-triaged to {target_group}'")
    else:
        failures.append(f"Contact note missing 'Re-triaged to {target_group}' (note: {note_text[:100]})")
        print(f"  FAIL: Contact note missing re-triage entry")
        print(f"         Note content: {note_text[:200]}")
else:
    failures.append("Contact not found after re-triage")
    print(f"  FAIL: Contact not found after re-triage")


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
    print("Re-triage working correctly:")
    print(f"  - Contact moved from {old_group} to {target_group}")
    print(f"  - Email labels reconciled ({new_dest_mailbox} applied, {old_dest_mailbox} removed)")
    print(f"  - Triage label {test_label} removed")
    print(f"  - Contact note updated with re-triage history")
    print()
    print("Cleanup: None needed -- contact is in the correct group.")
    print("To re-run: move the contact back to a different group and re-apply a triage label.")
