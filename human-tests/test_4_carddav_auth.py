"""Human test 4: CardDAV Authentication and Discovery (read-only, safe).

Connects to Fastmail via CardDAV, discovers the addressbook,
and validates that all required contact groups exist.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mailroom.clients.carddav import CardDAVClient
from mailroom.core.config import MailroomSettings

settings = MailroomSettings()

if not settings.carddav_username or not settings.carddav_password:
    print("--- FAIL ---")
    print("MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD must be set.")
    print("Set them in human-tests/.env (see .env.example).")
    sys.exit(1)

client = CardDAVClient(
    username=settings.carddav_username,
    password=settings.carddav_password,
)

print("Connecting to Fastmail CardDAV...")
try:
    client.connect()
except Exception as e:
    print(f"\n--- FAIL ---\nConnection failed: {e}")
    print("Check your MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD.")
    print("You need a Fastmail app password with CardDAV access.")
    sys.exit(1)

print(f"  Addressbook URL: {client._addressbook_url}")

print(f"\nValidating contact groups: {', '.join(settings.contact_groups)}")
try:
    groups = client.validate_groups(settings.contact_groups)
    print("\nAll groups found:")
    for name, info in groups.items():
        print(f"  {name}")
        print(f"    href: {info['href']}")
        print(f"    uid:  {info['uid']}")
    print("\n--- PASS ---")
except ValueError as e:
    print(f"\n--- FAIL ---\n{e}")
    print("Create the missing groups in Fastmail Contacts, then re-run.")
    sys.exit(1)
except Exception as e:
    print(f"\n--- FAIL ---\nUnexpected error: {e}")
    sys.exit(1)
