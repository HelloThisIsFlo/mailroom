"""Human test 12: Company Contact Creation via @ToImbox (WRITES to mailbox and contacts).

Validates that applying @ToImbox to an email in Screener creates a company-type
contact in Fastmail with correct vCard fields: FN + ORG, empty N (N:;;;;),
and a NOTE field with "Added by Mailroom".

This will:
  - Run one poll() cycle after you apply @ToImbox to an email
  - Verify via CardDAV that the new contact has company-type vCard fields
  - Verify via JMAP that the @ToImbox label was removed and emails swept

Prerequisites:
  - Tests 1-7 pass (JMAP auth, queries, labels, CardDAV auth, contacts, groups, screener poll)
  - @ToImbox label must exist in Fastmail
  - A test email from a known COMPANY/NEWSLETTER sender must be in Screener
    (no existing contact for that sender)
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
    settings.label_mailroom_warning,
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


# === Step 1: Instruct user to apply @ToImbox label ===
print("=== Step 1: Apply @ToImbox label ===\n")

print("Instructions:")
print("  1. Find an email from a known COMPANY/NEWSLETTER sender in Screener")
print("     (e.g., a service, newsletter, or business)")
print("  2. Make sure that sender does NOT already have a contact in Fastmail")
print("  3. Apply the @ToImbox label to that email")
print()
input("Press Enter when you have applied @ToImbox to an email in Screener... ")

# Record the sender email for later verification
print("\nEnter the sender's email address (for verification):")
test_sender = input("  Sender email: ").strip()
if not test_sender:
    print("--- FAIL ---")
    print("Sender email is required for verification.")
    sys.exit(1)


# === Step 2: Run poll() ===
print("\n=== Step 2: Run poll() ===\n")

print("Running one poll cycle...")
print("This will create a company-type contact and sweep emails.\n")

workflow = ScreenerWorkflow(
    jmap=jmap,
    carddav=carddav,
    settings=settings,
    mailbox_ids=mailbox_ids,
)

try:
    processed = workflow.poll()
except Exception as e:
    print(f"\n--- FAIL ---\npoll() raised: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print(f"\npoll() returned: {processed} sender(s) processed")

if processed == 0:
    print("\n--- FAIL ---")
    print("poll() returned 0 -- no senders were processed.")
    print("Check that @ToImbox was applied correctly and the sender has no conflicts.")
    sys.exit(1)

print("  --- STEP 2 PASS ---")


# === Step 3: Verify contact via CardDAV ===
print("\n=== Step 3: Verify contact via CardDAV ===\n")

failures = []

results = carddav.search_by_email(test_sender)
if not results:
    print(f"  --- STEP 3 FAIL ---")
    print(f"  No contact found for {test_sender} in CardDAV.")
    sys.exit(1)

print(f"  Found {len(results)} contact(s) for {test_sender}")

# Parse the vCard
vcard_data = results[0]["vcard_data"]
card = vobject.readOne(vcard_data)

# Check FN field
fn_value = getattr(card, "fn", None)
if fn_value and fn_value.value.strip():
    print(f"  FN: {fn_value.value}")
    print("    FN is set -- PASS")
else:
    failures.append("FN field is missing or empty")
    print("    FN is missing or empty -- FAIL")

# Check N field (should be empty: N:;;;; -- all components empty)
n_value = getattr(card, "n", None)
if n_value:
    n_obj = n_value.value
    given = n_obj.given or ""
    family = n_obj.family or ""
    additional = n_obj.additional or ""
    prefix = n_obj.prefix or ""
    suffix = n_obj.suffix or ""
    all_empty = not any([given.strip(), family.strip(), additional.strip(),
                         prefix.strip(), suffix.strip()])
    print(f"  N: given='{given}', family='{family}', additional='{additional}'")
    if all_empty:
        print("    N is empty (N:;;;;) -- PASS")
    else:
        failures.append(f"N field has components (given='{given}', family='{family}') -- should be empty for company")
        print("    N has name components -- FAIL (companies should have empty N)")
else:
    # No N field at all is also acceptable for a company
    print("  N: not present")
    print("    No N field -- PASS (acceptable for company)")

# Check ORG field (should be present and match FN)
org_entries = card.contents.get("org", [])
if org_entries:
    org_value = org_entries[0].value
    # org_value may be a list (vCard 3.0 ORG is structured) or a string
    if isinstance(org_value, list):
        org_display = org_value[0] if org_value else ""
    else:
        org_display = str(org_value)
    print(f"  ORG: {org_display}")

    # Compare with FN
    fn_text = fn_value.value.strip() if fn_value else ""
    if org_display.strip() == fn_text:
        print("    ORG matches FN -- PASS")
    else:
        failures.append(f"ORG ('{org_display}') does not match FN ('{fn_text}')")
        print(f"    ORG does not match FN -- FAIL")
else:
    failures.append("ORG field is missing -- should be present for company contacts")
    print("  ORG: not present")
    print("    ORG is missing -- FAIL (companies should have ORG)")

# Check NOTE field
note_entries = card.contents.get("note", [])
if note_entries and "Added by Mailroom" in note_entries[0].value:
    print(f"  NOTE: {note_entries[0].value}")
    print("    NOTE contains 'Added by Mailroom' -- PASS")
else:
    note_text = note_entries[0].value if note_entries else "(none)"
    failures.append(f"NOTE field does not contain 'Added by Mailroom' (got: {note_text})")
    print(f"  NOTE: {note_text}")
    print("    NOTE missing 'Added by Mailroom' -- FAIL")

if failures:
    print(f"\n  --- STEP 3 FAIL ---")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print("\n  --- STEP 3 PASS ---")


# === Step 4: Verify via JMAP ===
print("\n=== Step 4: Verify JMAP state ===\n")

jmap_failures = []

# Check @ToImbox label removed
toimbox_id = mailbox_ids["@ToImbox"]
toimbox_emails = jmap.query_emails(toimbox_id)
if toimbox_emails:
    toimbox_senders = jmap.get_email_senders(toimbox_emails)
    sender_still_labeled = any(
        s_email == test_sender for s_email, _ in toimbox_senders.values()
    )
    if sender_still_labeled:
        jmap_failures.append("@ToImbox label still present on sender's emails")
        print(f"  @ToImbox label: still present -- FAIL")
    else:
        print(f"  @ToImbox label: removed -- PASS")
else:
    print(f"  @ToImbox label: removed (no emails with label) -- PASS")

# Check emails swept from Screener
screener_id = mailbox_ids[settings.screener_mailbox]
sender_in_screener = jmap.query_emails(screener_id, sender=test_sender)
if sender_in_screener:
    jmap_failures.append(f"Sender still has {len(sender_in_screener)} email(s) in Screener")
    print(f"  Screener: {len(sender_in_screener)} email(s) remain -- FAIL")
else:
    print(f"  Screener: no emails from sender (swept) -- PASS")

if jmap_failures:
    print(f"\n  --- STEP 4 FAIL ---")
    for f in jmap_failures:
        print(f"  - {f}")
    sys.exit(1)

print("\n  --- STEP 4 PASS ---")


# === Step 5: Visual verification in Fastmail ===
print("\n=== Step 5: Visual verification ===\n")

print("Check Fastmail Contacts:")
print(f"  - Find the contact for {test_sender}")
print("  - It should appear as a COMPANY (with organization icon, not a person)")
print("  - The name should show as an organization/company name")
print("  - The NOTE field should say 'Added by Mailroom on <date>'")
print()
response = input("Does the contact render correctly as a company? Press Enter to confirm or type 'fail': ")
if response.strip().lower() == "fail":
    print("  --- STEP 5 FAIL ---")
    sys.exit(1)
print("  --- STEP 5 PASS ---")


# === Cleanup ===
print("\n=== Cleanup ===")
print(f"  Please manually delete the test contact for {test_sender} from Fastmail Contacts.")
print("  Also remove it from the Imbox group if needed.")


# === Report ===
print("\n--- PASS ---")
print("Company contact creation verified:")
print("  - poll() processed the sender successfully")
print("  - CardDAV: FN set, N empty (N:;;;;), ORG matches FN, NOTE present")
print("  - JMAP: @ToImbox label removed, emails swept from Screener")
print("  - Fastmail UI: contact renders as a company")
