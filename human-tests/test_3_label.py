"""Human test 3: Label Removal (WRITES to your mailbox).

Removes a triage label from ONE test email. Pick @ToImbox or another
triage label that has at least one email in it.

This modifies your mailbox -- use a test email you don't mind changing.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings

settings = MailroomSettings()
client = JMAPClient(token=settings.jmap_token)

print("Connecting...")
client.connect()

# Resolve just the label we're testing
label = settings.label_to_imbox  # @ToImbox by default
print(f"\nResolving mailbox for label: {label}")

try:
    mailboxes = client.resolve_mailboxes([label])
except ValueError:
    print(f"  Mailbox '{label}' not found in Fastmail.")
    print(f"  Create it, label a test email with it, then re-run.")
    sys.exit(1)

label_id = mailboxes[label]

print(f"  {label} -> {label_id}")
print(f"\nQuerying emails in {label}...")
email_ids = client.query_emails(label_id)
print(f"  Found {len(email_ids)} emails")

if not email_ids:
    print(f"\nNo emails have the {label} label.")
    print(f"Label a test email with {label} in Fastmail, then re-run.")
    print("\n--- SKIP ---")
    sys.exit(0)

target = email_ids[0]
senders = client.get_email_senders([target])
sender = senders.get(target, "unknown")

print(f"\nWill remove '{label}' from email {target[:12]}... (from {sender})")
print("Press Enter to proceed, or Ctrl-C to abort...")
input()

client.remove_label(target, label_id)
print(f"  Label removed!")

# Verify it's gone
remaining = client.query_emails(label_id)
if target in remaining:
    print(f"\n--- FAIL --- Email still has the {label} label")
    sys.exit(1)

print(f"  Verified: email no longer in {label}")
print("\n--- PASS ---")
