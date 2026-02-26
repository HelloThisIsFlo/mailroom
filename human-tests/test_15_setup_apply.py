"""Human test 15: Setup Apply + Idempotency (CREATES resources on real Fastmail).

Validates the setup command in apply mode:
  - Creates missing mailboxes and contact groups on Fastmail
  - Reports created/existing statuses
  - Shows sieve rule guidance
  - Idempotent: second run shows all "exists"
  - Exit code 0 on both runs

Prerequisites:
  - Test 14 passes (dry-run works)
  - .env file with Fastmail credentials

WARNING: This test creates REAL resources on your Fastmail account.
The resources created are the standard triage infrastructure (mailboxes
and contact groups) that Mailroom needs to operate. They are safe to
keep -- you will want them for normal Mailroom usage.
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


# === Step 1: First apply run ===
print("=== Step 1: First apply run (setup --apply) ===\n")

captured_1 = io.StringIO()
with redirect_stdout(captured_1):
    exit_code_1 = run_setup(apply=True, ui_guide=False)

output_1 = captured_1.getvalue()
print("  Captured output:")
print("  " + "-" * 60)
for line in output_1.split("\n"):
    print(f"  {line}")
print("  " + "-" * 60)

print(f"\n  Exit code: {exit_code_1}")

print("\n  --- STEP 1 PASS ---\n")


# === Step 2: Verify resources created ===
print("=== Step 2: Verify resources exist on Fastmail ===\n")

settings = MailroomSettings()

jmap = JMAPClient(token=settings.jmap_token)
jmap.connect()
print(f"  JMAP connected. Account ID: {jmap.account_id}")

carddav = CardDAVClient(
    username=settings.carddav_username,
    password=settings.carddav_password,
)
carddav.connect()
print(f"  CardDAV connected.")

# Verify all required mailboxes exist
step2_pass = True
try:
    mailbox_ids = jmap.resolve_mailboxes(settings.required_mailboxes)
    print(f"\n  All {len(mailbox_ids)} required mailboxes exist:")
    for name, mid in mailbox_ids.items():
        print(f"    {name} -> {mid[:12]}...")
except ValueError as e:
    print(f"\n  --- STEP 2 FAIL ---")
    print(f"  Missing mailboxes after apply: {e}")
    step2_pass = False

# Verify all required contact groups exist
try:
    carddav.validate_groups(settings.contact_groups)
    print(f"\n  All {len(settings.contact_groups)} required contact groups exist:")
    for name in settings.contact_groups:
        print(f"    {name}")
except ValueError as e:
    print(f"\n  --- STEP 2 FAIL ---")
    print(f"  Missing contact groups after apply: {e}")
    step2_pass = False

if not step2_pass:
    sys.exit(1)

print(f"\n  --- STEP 2 PASS ---\n")


# === Step 3: Verify first run output ===
print("=== Step 3: Verify first run output format ===\n")

checks = {
    "Has status indicators": any(s in output_1 for s in ["created", "exists"]),
    "Sieve Rules section": "Sieve Rules" in output_1,
    "Summary line present": any(s in output_1 for s in ["created", "to create", "existing"]),
}

step3_pass = True
for check_name, passed in checks.items():
    status = "PASS" if passed else "FAIL"
    print(f"  {check_name}: {status}")
    if not passed:
        step3_pass = False

if not step3_pass:
    print(f"\n  --- STEP 3 FAIL ---")
    sys.exit(1)

print(f"\n  --- STEP 3 PASS ---\n")


# === Step 4: Idempotency test ===
print("=== Step 4: Idempotency test (second apply run) ===\n")

captured_2 = io.StringIO()
with redirect_stdout(captured_2):
    exit_code_2 = run_setup(apply=True, ui_guide=False)

output_2 = captured_2.getvalue()
print("  Captured output:")
print("  " + "-" * 60)
for line in output_2.split("\n"):
    print(f"  {line}")
print("  " + "-" * 60)

print(f"\n  Exit code: {exit_code_2}")

print("\n  --- STEP 4 PASS ---\n")


# === Step 5: Verify second run all exists ===
print("=== Step 5: Verify second run shows all existing ===\n")

# The second run should NOT create anything new
has_created_status = "created" in output_2 and "0 created" not in output_2
has_no_creates = "0 created" in output_2 or "created" not in output_2

# Check that no "create" actions were needed (only "exists")
# The summary line should show "0 created" or similar
step5_pass = True

if has_created_status and not has_no_creates:
    print(f"  WARNING: Second run still shows 'created' resources.")
    print(f"  This may indicate non-idempotent behavior.")
    step5_pass = False
else:
    print(f"  Second run shows no new creates (idempotent).")

if "Sieve Rules" not in output_2:
    print(f"  Missing Sieve Rules section in second run.")
    step5_pass = False
else:
    print(f"  Sieve Rules section present in second run.")

if not step5_pass:
    print(f"\n  --- STEP 5 FAIL ---")
    sys.exit(1)

print(f"\n  --- STEP 5 PASS ---\n")


# === Step 6: Verify exit codes ===
print("=== Step 6: Verify exit codes ===\n")

step6_pass = True

print(f"  First run exit code:  {exit_code_1} (expected 0)")
if exit_code_1 != 0:
    step6_pass = False

print(f"  Second run exit code: {exit_code_2} (expected 0)")
if exit_code_2 != 0:
    step6_pass = False

if not step6_pass:
    print(f"\n  --- STEP 6 FAIL ---")
    sys.exit(1)

print(f"\n  --- STEP 6 PASS ---\n")


# === Report ===
print("--- PASS ---")
print("Setup apply + idempotency verification complete:")
print("  - First apply run created resources and reported status")
print("  - All required mailboxes and contact groups verified on Fastmail")
print("  - Sieve rule guidance displayed after resource provisioning")
print("  - Second apply run idempotent (all existing, no new creates)")
print("  - Both runs returned exit code 0")
