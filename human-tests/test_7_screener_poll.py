"""Human test 7: Screener Poll Cycle (WRITES to mailbox and contacts).

Runs one full ScreenerWorkflow.poll() cycle against your live Fastmail account.

This will:
  - Move emails from Screener to destination mailboxes (Inbox, Feed, etc.)
  - Create/update contacts in CardDAV groups
  - Remove triage labels from processed emails
  - Apply @MailroomError to conflicting senders

Prerequisites:
  - Tests 1-6 pass (JMAP auth, queries, labels, CardDAV auth, contacts, groups)
  - At least one email in Screener has a triage label (@ToImbox, @ToFeed, etc.)
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

# Configure structlog so you can see what the workflow is doing
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


# === Run: Execute one poll cycle ===
print("=== Run: Execute one poll cycle ===\n")

print("WARNING: This will modify your mailbox and contacts.")
print("Make sure you have at least one email with a triage label in Screener.\n")
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

print(f"\npoll() returned: {processed} sender(s) processed")

if processed > 0:
    print("\nCheck Fastmail to verify:")
    print("  - Emails moved from Screener to correct destination mailboxes")
    print("  - Contacts added to correct groups in Contacts")
    print("  - Triage labels removed from processed emails")

print("\n--- PASS ---")
