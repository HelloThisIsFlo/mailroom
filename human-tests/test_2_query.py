"""Human test 2: Email Query + Sender Extraction (read-only, safe).

Queries emails in Screener and extracts sender addresses.
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

mailboxes = client.resolve_mailboxes(["Inbox", "Screener"])
screener_id = mailboxes["Screener"]

print(f"\nQuerying emails in Screener ({screener_id[:12]}...)...")
email_ids = client.query_emails(screener_id)
print(f"  Found {len(email_ids)} emails")

if not email_ids:
    print("\nScreener is empty -- nothing to test sender extraction on.")
    print("Send yourself a test email and move it to Screener, then re-run.")
    print("\n--- SKIP ---")
    sys.exit(0)

sample = email_ids[:10]
print(f"\nExtracting senders for first {len(sample)} emails...")
senders = client.get_email_senders(sample)

for eid, sender in senders.items():
    print(f"  {eid[:12]}... from {sender}")

print(f"\n{len(senders)} senders extracted")
print("\n--- PASS ---")
