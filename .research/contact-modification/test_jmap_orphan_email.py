"""
Research: Does Fastmail enforce RFC 8621's "email must belong to at least one mailbox"?

RFC 8621 Section 4.1 says:
    "An Email in the mail store MUST belong to one or more Mailboxes
     at all times (until it is destroyed)."

This script tests what actually happens when you try to remove the LAST
mailbox from an email via Email/set patch. Specifically:

  1. Does Fastmail reject the update? If so, what error?
  2. Does it silently succeed and create an orphan email?
  3. Does it auto-move the email to Archive or Trash?
  4. Is "Archive" a real mailbox with role="archive"?

The test is SAFE: it creates a temporary email via Email/set create,
runs the experiment, then cleans up (destroys the test email).

Usage:
    python .research/contact-modification/test_jmap_orphan_email.py

Requires:
    - MAILROOM_JMAP_TOKEN in .env
    - pip install python-dotenv requests
"""

import json
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["MAILROOM_JMAP_TOKEN"]
API_URL = "https://api.fastmail.com/jmap/api/"
SESSION_URL = "https://api.fastmail.com/jmap/session"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

USING = [
    "urn:ietf:params:jmap:core",
    "urn:ietf:params:jmap:mail",
]


def jmap_call(method_calls: list) -> list:
    """Make a JMAP API call and return methodResponses."""
    payload = {"using": USING, "methodCalls": method_calls}
    resp = requests.post(API_URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()["methodResponses"]


def get_session() -> dict:
    """Fetch full JMAP session."""
    resp = requests.get(SESSION_URL, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def pp(label: str, obj) -> None:
    """Pretty-print a labeled JSON object."""
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")
    print(json.dumps(obj, indent=2))


def section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'#' * 70}")
    print(f"# {title}")
    print(f"{'#' * 70}")


def main():
    # ------------------------------------------------------------------
    # STEP 0: Connect and discover account
    # ------------------------------------------------------------------
    section("STEP 0: Connect to Fastmail JMAP")

    session = get_session()
    account_id = session["primaryAccounts"]["urn:ietf:params:jmap:mail"]
    print(f"  Account ID: {account_id}")

    # ------------------------------------------------------------------
    # STEP 1: List all mailboxes — find roles, look for Archive
    # ------------------------------------------------------------------
    section("STEP 1: List all mailboxes (look for Archive, roles)")

    responses = jmap_call([
        ["Mailbox/get", {"accountId": account_id, "ids": None}, "mb0"],
    ])
    mailbox_list = responses[0][1]["list"]

    # Build lookup maps
    mailbox_by_role: dict[str, dict] = {}
    mailbox_by_name: dict[str, dict] = {}
    mailbox_by_id: dict[str, dict] = {}

    print(f"\n  {'Name':<30} {'Role':<15} {'ID'}")
    print(f"  {'-'*30} {'-'*15} {'-'*40}")

    for mb in mailbox_list:
        name = mb["name"]
        role = mb.get("role", "")
        mb_id = mb["id"]
        parent_id = mb.get("parentId")

        indent = "  " if parent_id else ""
        print(f"  {indent}{name:<28} {role or '(none)':<15} {mb_id}")

        if role:
            mailbox_by_role[role] = mb
        mailbox_by_name[name] = mb
        mailbox_by_id[mb_id] = mb

    # Specifically check for Archive
    archive_mb = mailbox_by_role.get("archive")
    if archive_mb:
        print(f"\n  >>> ARCHIVE IS A REAL MAILBOX with role='archive'")
        print(f"      ID: {archive_mb['id']}, Name: {archive_mb['name']}")
    else:
        archive_mb = mailbox_by_name.get("Archive")
        if archive_mb:
            print(f"\n  >>> 'Archive' exists as a named mailbox (no 'archive' role)")
            print(f"      ID: {archive_mb['id']}, Role: {archive_mb.get('role', 'none')}")
        else:
            print(f"\n  >>> No 'Archive' mailbox found at all!")

    # Get Drafts mailbox (we'll create our test email there)
    drafts_mb = mailbox_by_role.get("drafts")
    if not drafts_mb:
        print("\n  ERROR: No Drafts mailbox found. Cannot proceed.")
        sys.exit(1)
    drafts_id = drafts_mb["id"]
    print(f"\n  Using Drafts mailbox for test: {drafts_id}")

    # ------------------------------------------------------------------
    # STEP 2: Create a test email (draft) in a single mailbox
    # ------------------------------------------------------------------
    section("STEP 2: Create test email in Drafts only")

    create_resp = jmap_call([
        ["Email/set", {
            "accountId": account_id,
            "create": {
                "test1": {
                    "mailboxIds": {drafts_id: True},
                    "subject": "[MAILROOM-RESEARCH] Orphan email test - safe to delete",
                    "from": [{"name": "Mailroom Research", "email": "test@example.com"}],
                    "to": [{"name": "Test", "email": "test@example.com"}],
                    "bodyStructure": {
                        "type": "text/plain",
                        "partId": "body",
                    },
                    "bodyValues": {
                        "body": {
                            "value": "This is a test email created by Mailroom research script.\n"
                                     "It tests RFC 8621 orphan email behavior.\n"
                                     "Safe to delete.",
                            "isEncodingProblem": False,
                            "isTruncated": False,
                        },
                    },
                    "keywords": {"$draft": True},
                },
            },
        }, "c0"],
    ])

    create_data = create_resp[0][1]
    created = create_data.get("created", {})
    not_created = create_data.get("notCreated", {})

    if "test1" not in created:
        pp("FAILED to create test email", not_created)
        sys.exit(1)

    test_email_id = created["test1"]["id"]
    print(f"  Created test email: {test_email_id}")

    # Verify it's in exactly one mailbox
    verify_resp = jmap_call([
        ["Email/get", {
            "accountId": account_id,
            "ids": [test_email_id],
            "properties": ["id", "mailboxIds", "subject"],
        }, "v0"],
    ])
    email_data = verify_resp[0][1]["list"][0]
    pp("Test email state BEFORE experiment", email_data)

    current_mailboxes = email_data.get("mailboxIds", {})
    print(f"\n  Mailbox count: {len(current_mailboxes)}")
    for mb_id in current_mailboxes:
        mb_info = mailbox_by_id.get(mb_id, {})
        print(f"    - {mb_info.get('name', '???')} ({mb_id})")

    # ------------------------------------------------------------------
    # STEP 3: THE EXPERIMENT - Try to remove the ONLY mailbox
    # ------------------------------------------------------------------
    section("STEP 3: THE EXPERIMENT - Remove the ONLY mailbox via patch")

    print(f"  Attempting: Email/set update")
    print(f"    email_id: {test_email_id}")
    print(f"    patch: {{\"mailboxIds/{drafts_id}\": null}}")
    print(f"  This should leave the email in ZERO mailboxes...")

    experiment_resp = jmap_call([
        ["Email/set", {
            "accountId": account_id,
            "update": {
                test_email_id: {
                    f"mailboxIds/{drafts_id}": None,
                },
            },
        }, "exp0"],
    ])

    exp_data = experiment_resp[0][1]
    updated = exp_data.get("updated")
    not_updated = exp_data.get("notUpdated")

    pp("Raw Email/set response", exp_data)

    if not_updated and test_email_id in not_updated:
        error = not_updated[test_email_id]
        print(f"\n  >>> UPDATE REJECTED!")
        print(f"      Error type: {error.get('type', '???')}")
        print(f"      Description: {error.get('description', '???')}")
        print(f"      Properties: {error.get('properties', '???')}")
        print(f"\n  CONCLUSION: Fastmail ENFORCES the RFC 8621 constraint.")
        print(f"  You cannot create an orphan email.")
    elif updated and test_email_id in updated:
        print(f"\n  >>> UPDATE ACCEPTED! The server allowed removing the last mailbox.")
        print(f"  Now checking what happened to the email...")

        # Check the email's state after the update
        post_resp = jmap_call([
            ["Email/get", {
                "accountId": account_id,
                "ids": [test_email_id],
                "properties": ["id", "mailboxIds", "subject"],
            }, "post0"],
        ])

        post_data = post_resp[0][1]
        post_list = post_data.get("list", [])
        not_found = post_data.get("notFound", [])

        if test_email_id in not_found:
            print(f"\n  >>> Email NOT FOUND after removing last mailbox!")
            print(f"  CONCLUSION: Fastmail may have auto-destroyed the email.")
            test_email_id = None  # Already gone, skip cleanup
        elif post_list:
            post_email = post_list[0]
            pp("Email state AFTER removing last mailbox", post_email)
            post_mailboxes = post_email.get("mailboxIds", {})

            if not post_mailboxes:
                print(f"\n  >>> Email exists with ZERO mailboxes (true orphan)!")
                print(f"  CONCLUSION: Fastmail allows orphan emails.")
            else:
                print(f"\n  >>> Email was auto-assigned to mailbox(es):")
                for mb_id in post_mailboxes:
                    mb_info = mailbox_by_id.get(mb_id, {})
                    role = mb_info.get("role", "none")
                    print(f"      - {mb_info.get('name', '???')} (role={role}, id={mb_id})")

                if archive_mb and archive_mb["id"] in post_mailboxes:
                    print(f"\n  CONCLUSION: Fastmail auto-moves to Archive when "
                          f"last mailbox removed.")
                else:
                    print(f"\n  CONCLUSION: Fastmail auto-moves to some other mailbox.")
    else:
        pp("UNEXPECTED response (neither updated nor notUpdated)", exp_data)

    # ------------------------------------------------------------------
    # STEP 4: BONUS - Try setting mailboxIds to empty object directly
    # ------------------------------------------------------------------
    if test_email_id:
        section("STEP 4: BONUS - Try setting mailboxIds to empty object {}")

        # First, restore the email to Drafts if needed
        restore_resp = jmap_call([
            ["Email/set", {
                "accountId": account_id,
                "update": {
                    test_email_id: {
                        "mailboxIds": {drafts_id: True},
                    },
                },
            }, "restore0"],
        ])

        restore_data = restore_resp[0][1]
        if restore_data.get("notUpdated"):
            print(f"  Could not restore to Drafts, trying with current state...")
        else:
            print(f"  Restored email to Drafts.")

        # Now try the direct empty-object approach
        print(f"\n  Attempting: Email/set update")
        print(f"    email_id: {test_email_id}")
        print(f"    patch: {{\"mailboxIds\": {{}}}}")

        empty_resp = jmap_call([
            ["Email/set", {
                "accountId": account_id,
                "update": {
                    test_email_id: {
                        "mailboxIds": {},
                    },
                },
            }, "empty0"],
        ])

        empty_data = empty_resp[0][1]
        pp("Response to mailboxIds={}", empty_data)

        not_updated_empty = empty_data.get("notUpdated")
        if not_updated_empty and test_email_id in not_updated_empty:
            error = not_updated_empty[test_email_id]
            print(f"\n  >>> REJECTED!")
            print(f"      Error type: {error.get('type', '???')}")
            print(f"      Description: {error.get('description', '???')}")
        elif empty_data.get("updated") and test_email_id in empty_data["updated"]:
            print(f"\n  >>> ACCEPTED! Checking post-state...")

            check_resp = jmap_call([
                ["Email/get", {
                    "accountId": account_id,
                    "ids": [test_email_id],
                    "properties": ["id", "mailboxIds", "subject"],
                }, "check0"],
            ])
            check_data = check_resp[0][1]
            check_list = check_data.get("list", [])
            if check_list:
                pp("Email state after mailboxIds={}", check_list[0])
                remaining = check_list[0].get("mailboxIds", {})
                if remaining:
                    for mb_id in remaining:
                        mb_info = mailbox_by_id.get(mb_id, {})
                        print(f"  Auto-assigned to: {mb_info.get('name', '???')} "
                              f"(role={mb_info.get('role', 'none')})")
                else:
                    print(f"  Email has zero mailboxes!")
            elif test_email_id in check_data.get("notFound", []):
                print(f"  Email was destroyed!")
                test_email_id = None

    # ------------------------------------------------------------------
    # STEP 5: Cleanup - destroy the test email
    # ------------------------------------------------------------------
    section("STEP 5: Cleanup")

    if test_email_id:
        cleanup_resp = jmap_call([
            ["Email/set", {
                "accountId": account_id,
                "destroy": [test_email_id],
            }, "cleanup0"],
        ])

        cleanup_data = cleanup_resp[0][1]
        destroyed = cleanup_data.get("destroyed", [])
        not_destroyed = cleanup_data.get("notDestroyed", {})

        if test_email_id in destroyed:
            print(f"  Test email destroyed successfully.")
        elif test_email_id in not_destroyed:
            print(f"  Failed to destroy: {not_destroyed[test_email_id]}")
        else:
            print(f"  Unexpected cleanup response:")
            print(json.dumps(cleanup_data, indent=2))
    else:
        print(f"  No cleanup needed (email already gone).")

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    section("SUMMARY")

    print("""
  RFC 8621 Section 4.1 (Email object, mailboxIds property):

    "An Email in the mail store MUST belong to one or more Mailboxes
     at all times (until it is destroyed)."

    The mailboxIds property is Id[Boolean] and represents the set of
    Mailbox ids this Email belongs to. The server MUST reject an update
    that would leave an Email in zero mailboxes.

  FINDINGS (from live Fastmail test, 2026-03-04):

    Q1: Does Fastmail enforce this constraint?
        -> YES. Both approaches are REJECTED with:
           {"type": "invalidProperties", "properties": ["mailboxIds"]}
           No description field is included in the error.

    Q2: Is "Archive" a real mailbox in Fastmail?
        -> YES. Archive is a real mailbox with role="archive", ID="P6-".
           It is NOT "the absence of mailboxes" (that's a Gmail mental
           model). In Fastmail, "archiving" means moving FROM Inbox TO
           the Archive mailbox. An email in Archive is in exactly one
           mailbox, just like any other.

    Q3: What error does Fastmail return when the constraint is violated?
        -> Error type: "invalidProperties"
           Properties: ["mailboxIds"]
           No description text. No special error type — it's the same
           generic "invalidProperties" used for any bad property value.

    Q4: What does "mailboxIds/{id}: null" (patch to remove) vs
        "mailboxIds: {}" (replace with empty) do?
        -> Both are rejected identically. Fastmail checks the final
           state would have zero mailboxes and refuses both approaches.

    IMPLICATIONS FOR MAILROOM:
        - batch_remove_labels() is SAFE when emails have other labels,
          but will FAIL if you try to remove an email's ONLY label.
        - "Reset" operations that remove all triage labels must ensure
          emails end up somewhere (e.g., back in @Screen or Archive).
        - You CANNOT "un-label" an email — you can only MOVE it.
""")


if __name__ == "__main__":
    main()
