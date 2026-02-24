"""Human test 1: Auth + Mailbox Resolution (read-only, safe).

Connects to Fastmail with your token and resolves all mailboxes
the triage workflow needs.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings

settings = MailroomSettings()
client = JMAPClient(token=settings.jmap_token)

print("Connecting to Fastmail...")
client.connect()
print(f"  Connected! Account ID: {client.account_id}")

required = ["Inbox", "Screener", *settings.triage_labels]
print(f"\nResolving {len(required)} mailboxes: {', '.join(required)}")

try:
    mailboxes = client.resolve_mailboxes(required)
    print("\nAll mailboxes resolved:")
    for name, mid in mailboxes.items():
        print(f"  {name} -> {mid}")
    print("\n--- PASS ---")
except ValueError as e:
    print(f"\n--- FAIL ---\n{e}")
    print("Create the missing mailboxes in Fastmail, then re-run.")
    sys.exit(1)
