"""Human test 14: Setup Dry Run (reads real Fastmail, makes NO changes).

Validates the setup command in dry-run mode:
  - Connects to JMAP and CardDAV (pre-flight check)
  - Shows resource plan with Mailboxes, Action Labels, Contact Groups
  - Shows sieve rule guidance for all categories
  - Makes NO changes to Fastmail (verify state unchanged)
  - Exit code 0

Prerequisites:
  - Tests 1-12 pass
  - .env file with Fastmail credentials
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.setup.provisioner import run_setup


# === Step 1: Pre-flight connectivity ===
print("=== Step 1: Pre-flight connectivity ===\n")

try:
    settings = MailroomSettings()
except Exception as e:
    print(f"  --- STEP 1 FAIL ---")
    print(f"  Configuration error: {e}")
    sys.exit(1)

jmap = JMAPClient(token=settings.jmap_token)
try:
    jmap.connect()
    print(f"  JMAP connected. Account ID: {jmap.account_id}")
except Exception as e:
    print(f"  --- STEP 1 FAIL ---")
    print(f"  JMAP connection failed: {e}")
    sys.exit(1)

carddav = CardDAVClient(
    username=settings.carddav_username,
    password=settings.carddav_password,
)
try:
    carddav.connect()
    print(f"  CardDAV connected.")
except Exception as e:
    print(f"  --- STEP 1 FAIL ---")
    print(f"  CardDAV connection failed: {e}")
    sys.exit(1)

print("\n  --- STEP 1 PASS ---\n")


# === Step 2: Record initial state ===
print("=== Step 2: Record initial state ===\n")

# Record existing mailboxes
try:
    existing_mailbox_ids = jmap.resolve_mailboxes(settings.required_mailboxes)
    existing_mailbox_names = set(existing_mailbox_ids.keys())
    print(f"  Existing mailboxes: {len(existing_mailbox_names)}")
except ValueError as e:
    # Some mailboxes may not exist yet -- that's OK, record what we can
    existing_mailbox_names = set()
    print(f"  Some mailboxes missing (expected for first run): {e}")

# Record existing contact groups
existing_groups = carddav.list_groups()
existing_group_names = set(existing_groups.keys())
print(f"  Existing contact groups: {len(existing_group_names)}")

print("\n  --- STEP 2 PASS ---\n")


# === Step 3: Run dry-run ===
print("=== Step 3: Run dry-run (setup without --apply) ===\n")

captured = io.StringIO()
with redirect_stdout(captured):
    exit_code = run_setup(apply=False, ui_guide=False)

output = captured.getvalue()
print("  Captured output:")
print("  " + "-" * 60)
for line in output.split("\n"):
    print(f"  {line}")
print("  " + "-" * 60)

print(f"\n  Exit code: {exit_code}")

print("\n  --- STEP 3 PASS ---\n")


# === Step 4: Verify output format ===
print("=== Step 4: Verify output format ===\n")

checks = {
    "Mailboxes section": "Mailboxes" in output,
    "Action Labels section": "Action Labels" in output,
    "Contact Groups section": "Contact Groups" in output,
    "Sieve Rules section": "Sieve Rules" in output,
    "Status indicator": any(s in output for s in ["exists", "create"]),
}

step4_pass = True
for check_name, passed in checks.items():
    status = "PASS" if passed else "FAIL"
    print(f"  {check_name}: {status}")
    if not passed:
        step4_pass = False

if not step4_pass:
    print(f"\n  --- STEP 4 FAIL ---")
    sys.exit(1)

print(f"\n  --- STEP 4 PASS ---\n")


# === Step 5: Verify no changes ===
print("=== Step 5: Verify no changes (state unchanged) ===\n")

# Re-check mailboxes
try:
    post_mailbox_ids = jmap.resolve_mailboxes(settings.required_mailboxes)
    post_mailbox_names = set(post_mailbox_ids.keys())
except ValueError:
    post_mailbox_names = set()

# Re-check contact groups
post_groups = carddav.list_groups()
post_group_names = set(post_groups.keys())

mailboxes_unchanged = existing_mailbox_names == post_mailbox_names
groups_unchanged = existing_group_names == post_group_names

print(f"  Mailboxes unchanged: {mailboxes_unchanged}")
print(f"  Contact groups unchanged: {groups_unchanged}")

if not mailboxes_unchanged:
    added = post_mailbox_names - existing_mailbox_names
    removed = existing_mailbox_names - post_mailbox_names
    if added:
        print(f"    Added mailboxes: {added}")
    if removed:
        print(f"    Removed mailboxes: {removed}")

if not groups_unchanged:
    added = post_group_names - existing_group_names
    removed = existing_group_names - post_group_names
    if added:
        print(f"    Added groups: {added}")
    if removed:
        print(f"    Removed groups: {removed}")

if not (mailboxes_unchanged and groups_unchanged):
    print(f"\n  --- STEP 5 FAIL ---")
    print("  Dry-run modified resources! This should not happen.")
    sys.exit(1)

print(f"\n  --- STEP 5 PASS ---\n")


# === Step 6: Verify exit code ===
print("=== Step 6: Verify exit code ===\n")

if exit_code != 0:
    print(f"  Exit code: {exit_code} (expected 0)")
    print(f"\n  --- STEP 6 FAIL ---")
    sys.exit(1)

print(f"  Exit code: {exit_code} (expected 0)")
print(f"\n  --- STEP 6 PASS ---\n")


# === Report ===
print("--- PASS ---")
print("Setup dry-run verification complete:")
print("  - JMAP and CardDAV connectivity confirmed")
print("  - Output contains Mailboxes, Action Labels, Contact Groups sections")
print("  - Output contains Sieve Rules guidance section")
print("  - No resources were created or modified")
print("  - Exit code 0")
