#!/usr/bin/env python3
"""Find and recover orphaned emails from a failed reset operation.

Orphaned emails have empty mailboxIds -- they exist in Fastmail's store
but are invisible in the UI because they belong to no mailbox.

Usage:
    python find_and_recover.py                  # dry-run (default)
    python find_and_recover.py --apply          # actually recover emails
    python find_and_recover.py --scan-all       # also scan recent emails broadly
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings


# Known affected senders from the failed reset
KNOWN_AFFECTED_SENDERS = [
    "doppler",
]


def connect() -> tuple[JMAPClient, MailroomSettings]:
    """Connect to Fastmail and return (client, settings)."""
    settings = MailroomSettings()
    client = JMAPClient(token=settings.jmap_token)
    print("Connecting to Fastmail...")
    client.connect()
    print(f"  Account ID: {client.account_id}")
    return client, settings


def get_all_mailboxes(client: JMAPClient) -> dict[str, str]:
    """Fetch all mailboxes and return {id: name} map."""
    responses = client.call(
        [["Mailbox/get", {"accountId": client.account_id, "ids": None}, "m0"]]
    )
    mailbox_list = responses[0][1]["list"]
    return {mb["id"]: mb["name"] for mb in mailbox_list}


def get_email_details(
    client: JMAPClient, email_ids: list[str]
) -> list[dict]:
    """Fetch full details for a batch of email IDs."""
    if not email_ids:
        return []

    all_emails = []
    batch_size = 50

    for i in range(0, len(email_ids), batch_size):
        chunk = email_ids[i : i + batch_size]
        responses = client.call(
            [
                [
                    "Email/get",
                    {
                        "accountId": client.account_id,
                        "ids": chunk,
                        "properties": [
                            "id",
                            "from",
                            "subject",
                            "receivedAt",
                            "mailboxIds",
                        ],
                    },
                    "g0",
                ]
            ]
        )
        all_emails.extend(responses[0][1]["list"])

    return all_emails


def find_orphans_by_sender(
    client: JMAPClient, sender: str
) -> list[dict]:
    """Search for emails from a sender and return any with empty mailboxIds."""
    print(f"\n  Searching for emails from '{sender}'...")

    # Email/query with just a from filter -- no inMailbox constraint
    # This should search across all emails including orphans
    all_ids: list[str] = []
    position = 0

    while True:
        responses = client.call(
            [
                [
                    "Email/query",
                    {
                        "accountId": client.account_id,
                        "filter": {"from": sender},
                        "limit": 100,
                        "position": position,
                    },
                    "q0",
                ]
            ]
        )
        data = responses[0][1]
        ids = data["ids"]
        all_ids.extend(ids)
        if len(ids) < 100:
            break
        position = len(all_ids)

    print(f"    Found {len(all_ids)} total emails from '{sender}'")

    if not all_ids:
        return []

    # Get details including mailboxIds
    emails = get_email_details(client, all_ids)

    orphans = []
    for email in emails:
        mailbox_ids = email.get("mailboxIds", {})
        if not mailbox_ids:
            orphans.append(email)

    return orphans


def find_orphans_by_text_search(
    client: JMAPClient, text: str
) -> list[dict]:
    """Search by text content (catches subject/body matches too)."""
    print(f"\n  Text-searching for '{text}'...")

    all_ids: list[str] = []
    position = 0

    while True:
        responses = client.call(
            [
                [
                    "Email/query",
                    {
                        "accountId": client.account_id,
                        "filter": {"text": text},
                        "limit": 100,
                        "position": position,
                    },
                    "q0",
                ]
            ]
        )
        data = responses[0][1]
        ids = data["ids"]
        all_ids.extend(ids)
        if len(ids) < 100:
            break
        position = len(all_ids)

    print(f"    Found {len(all_ids)} emails matching '{text}'")

    if not all_ids:
        return []

    emails = get_email_details(client, all_ids)

    orphans = []
    for email in emails:
        mailbox_ids = email.get("mailboxIds", {})
        if not mailbox_ids:
            orphans.append(email)

    return orphans


def scan_recent_emails(client: JMAPClient, days: int = 30) -> list[dict]:
    """Scan recent emails broadly to find any orphans regardless of sender.

    Uses receivedAt filter to limit scope.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"\n  Scanning all emails received since {since_str}...")

    all_ids: list[str] = []
    position = 0

    while True:
        responses = client.call(
            [
                [
                    "Email/query",
                    {
                        "accountId": client.account_id,
                        "filter": {"after": since_str},
                        "sort": [{"property": "receivedAt", "isAscending": False}],
                        "limit": 100,
                        "position": position,
                    },
                    "q0",
                ]
            ]
        )
        data = responses[0][1]
        ids = data["ids"]
        all_ids.extend(ids)
        print(f"    ... fetched {len(all_ids)} IDs so far")
        if len(ids) < 100:
            break
        position = len(all_ids)

    print(f"    Total: {len(all_ids)} emails in last {days} days")

    if not all_ids:
        return []

    # Check mailboxIds in batches
    emails = get_email_details(client, all_ids)

    orphans = []
    for email in emails:
        mailbox_ids = email.get("mailboxIds", {})
        if not mailbox_ids:
            orphans.append(email)

    return orphans


def paginate_query(client: JMAPClient, filter_obj: dict) -> list[str]:
    """Paginate through an Email/query and return all IDs."""
    all_ids: list[str] = []
    position = 0
    while True:
        responses = client.call(
            [
                [
                    "Email/query",
                    {
                        "accountId": client.account_id,
                        "filter": filter_obj,
                        "sort": [{"property": "receivedAt", "isAscending": False}],
                        "limit": 100,
                        "position": position,
                    },
                    "q0",
                ]
            ]
        )
        data = responses[0][1]
        ids = data["ids"]
        all_ids.extend(ids)
        if position == 0:
            total = data.get("total", "?")
            print(f"    Server reports total={total}")
        if len(ids) < 100:
            break
        position = len(all_ids)
        if position % 500 == 0:
            print(f"    ... {position} IDs fetched")
    return all_ids


def find_orphans_by_set_difference(
    client: JMAPClient, mailbox_map: dict[str, str]
) -> list[str]:
    """Find orphan IDs by computing: (all email IDs) - (union of per-mailbox IDs).

    This is expensive but catches emails invisible to query filters.
    """
    print("\n  Step 1: Fetching ALL email IDs (filterless query)...")
    all_ids = set(paginate_query(client, {}))
    print(f"    Total unique IDs: {len(all_ids)}")

    print("\n  Step 2: Fetching IDs per mailbox...")
    mailbox_ids: set[str] = set()
    for mid, name in sorted(mailbox_map.items(), key=lambda x: x[1]):
        ids = paginate_query(client, {"inMailbox": mid})
        if ids:
            print(f"    {name:30s} {len(ids):>6d} emails")
            mailbox_ids.update(ids)

    print(f"\n    Union of per-mailbox IDs: {len(mailbox_ids)}")

    orphan_ids = all_ids - mailbox_ids
    print(f"    Orphan IDs (in all but no mailbox): {len(orphan_ids)}")

    return list(orphan_ids)


def print_email(email: dict, mailbox_map: dict[str, str]) -> None:
    """Pretty-print an email's details."""
    from_list = email.get("from", [])
    sender = from_list[0] if from_list else {}
    sender_str = f"{sender.get('name', '?')} <{sender.get('email', '?')}>"
    subject = email.get("subject", "(no subject)")
    received = email.get("receivedAt", "?")
    mailbox_ids = email.get("mailboxIds", {})

    print(f"    ID:       {email['id']}")
    print(f"    From:     {sender_str}")
    print(f"    Subject:  {subject}")
    print(f"    Received: {received}")

    if mailbox_ids:
        names = [mailbox_map.get(mid, mid) for mid in mailbox_ids]
        print(f"    Mailboxes: {', '.join(names)}")
    else:
        print(f"    Mailboxes: ** NONE (ORPHANED) **")

    print()


def recover_emails(
    client: JMAPClient,
    orphans: list[dict],
    screener_id: str,
    dry_run: bool = True,
) -> None:
    """Move orphaned emails to Screener mailbox."""
    if not orphans:
        print("\nNo orphaned emails to recover.")
        return

    if dry_run:
        print(f"\n[DRY RUN] Would recover {len(orphans)} email(s) to Screener.")
        print("  Run with --apply to actually recover them.")
        return

    print(f"\nRecovering {len(orphans)} email(s) to Screener...")

    email_ids = [e["id"] for e in orphans]
    batch_size = 50

    for i in range(0, len(email_ids), batch_size):
        chunk = email_ids[i : i + batch_size]

        update = {}
        for eid in chunk:
            # Set mailboxIds to ONLY Screener (replace, don't patch)
            # Since these emails have empty mailboxIds, we need to set the whole object
            update[eid] = {"mailboxIds": {screener_id: True}}

        responses = client.call(
            [
                [
                    "Email/set",
                    {
                        "accountId": client.account_id,
                        "update": update,
                    },
                    "s0",
                ]
            ]
        )
        data = responses[0][1]

        updated = data.get("updated", {})
        not_updated = data.get("notUpdated", {})

        for eid in chunk:
            if eid in not_updated:
                err = not_updated[eid]
                print(f"  FAILED {eid}: {err.get('type', '?')} - {err.get('description', '?')}")
            else:
                print(f"  OK     {eid}")

    print("\nRecovery complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find and recover orphaned emails from failed reset"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually recover emails (default is dry-run)",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Also scan all recent emails (last 30 days) for orphans",
    )
    parser.add_argument(
        "--scan-days",
        type=int,
        default=30,
        help="Number of days to scan back when using --scan-all (default: 30)",
    )
    parser.add_argument(
        "--set-diff",
        action="store_true",
        help="Nuclear option: enumerate ALL email IDs, compare against per-mailbox IDs, find the gap",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    client, settings = connect()

    # Get all mailboxes for display
    print("\nFetching all mailboxes...")
    mailbox_map = get_all_mailboxes(client)
    print(f"  Found {len(mailbox_map)} mailboxes:")
    for mid, name in sorted(mailbox_map.items(), key=lambda x: x[1]):
        print(f"    {name:30s} {mid}")

    # Resolve Screener for recovery target
    screener_name = settings.triage.screener_mailbox
    screener_id = None
    for mid, name in mailbox_map.items():
        if name == screener_name:
            screener_id = mid
            break

    if screener_id is None:
        print(f"\nERROR: Screener mailbox '{screener_name}' not found!")
        sys.exit(1)

    print(f"\n  Recovery target: {screener_name} ({screener_id})")

    # === PHASE 1: Search by known affected senders ===
    print("\n" + "=" * 60)
    print("PHASE 1: Searching by known affected senders")
    print("=" * 60)

    all_orphans: dict[str, dict] = {}  # dedup by email ID

    for sender in KNOWN_AFFECTED_SENDERS:
        # Try both from-filter and text search
        orphans_from = find_orphans_by_sender(client, sender)
        orphans_text = find_orphans_by_text_search(client, sender)

        for o in orphans_from + orphans_text:
            all_orphans[o["id"]] = o

    if all_orphans:
        print(f"\nFound {len(all_orphans)} orphaned email(s) from known senders:")
        for email in all_orphans.values():
            print_email(email, mailbox_map)
    else:
        print("\nNo orphaned emails found from known senders.")
        print("  (They may not appear in query results if truly invisible)")

    # === PHASE 2: Broad scan (optional) ===
    if args.scan_all:
        print("\n" + "=" * 60)
        print(f"PHASE 2: Broad scan of last {args.scan_days} days")
        print("=" * 60)

        broad_orphans = scan_recent_emails(client, days=args.scan_days)
        for o in broad_orphans:
            all_orphans[o["id"]] = o

        if broad_orphans:
            new_finds = [o for o in broad_orphans if o["id"] not in {
                e["id"] for e in all_orphans.values()
            }]
            print(f"\nBroad scan found {len(broad_orphans)} additional orphan(s):")
            for email in broad_orphans:
                print_email(email, mailbox_map)
        else:
            print("\nNo additional orphans found in broad scan.")

    # === PHASE 3: Set-difference approach (optional, expensive) ===
    if args.set_diff:
        print("\n" + "=" * 60)
        print("PHASE 3: Set-difference (all IDs minus per-mailbox IDs)")
        print("=" * 60)

        orphan_ids = find_orphans_by_set_difference(client, mailbox_map)

        if orphan_ids:
            print(f"\n  Fetching details for {len(orphan_ids)} orphan(s)...")
            orphan_emails = get_email_details(client, orphan_ids)
            for email in orphan_emails:
                all_orphans[email["id"]] = email
                print_email(email, mailbox_map)
        else:
            print("\n  No orphans found via set-difference.")
            print("  The filterless query may also exclude orphaned emails.")
    else:
        # Quick discrepancy check (lightweight)
        print("\n" + "=" * 60)
        print("PHASE 3: Quick discrepancy check")
        print("=" * 60)

        responses = client.call(
            [
                [
                    "Email/query",
                    {
                        "accountId": client.account_id,
                        "filter": {},
                        "sort": [{"property": "receivedAt", "isAscending": False}],
                        "limit": 0,
                        "position": 0,
                    },
                    "q_probe",
                ]
            ]
        )
        total = responses[0][1].get("total", "?")

        total_in_mailboxes = 0
        for mid, name in sorted(mailbox_map.items(), key=lambda x: x[1]):
            responses = client.call(
                [
                    [
                        "Email/query",
                        {
                            "accountId": client.account_id,
                            "filter": {"inMailbox": mid},
                            "limit": 0,
                        },
                        "c0",
                    ]
                ]
            )
            count = responses[0][1].get("total", 0)
            if count > 0:
                print(f"    {name:30s} {count:>6d} emails")
            total_in_mailboxes += count

        print(f"\n  Total across all mailboxes:  {total_in_mailboxes}")
        print(f"  Total from filterless query: {total}")

        if isinstance(total, int) and total > total_in_mailboxes:
            diff = total - total_in_mailboxes
            print(f"\n  *** DISCREPANCY: {diff} email(s) not in any mailbox! ***")
            print(f"  Run with --set-diff to enumerate and recover them.")
        elif isinstance(total, int):
            print(f"\n  No discrepancy (sum >= total is normal due to multi-label emails).")
        else:
            print(f"\n  Could not determine total.")

    # === SUMMARY ===
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nOrphaned emails found: {len(all_orphans)}")

    if all_orphans:
        print("\nAll orphaned emails:")
        for email in all_orphans.values():
            print_email(email, mailbox_map)

        # Recover
        recover_emails(
            client,
            list(all_orphans.values()),
            screener_id,
            dry_run=dry_run,
        )
    else:
        print("\nNo orphaned emails were found via query-based search.")
        print("\nPossible explanations:")
        print("  1. Fastmail's Email/query index excludes emails with no mailboxIds")
        print("     (they're truly invisible to JMAP queries too)")
        print("  2. The emails were already garbage-collected by Fastmail")
        print("  3. The emails were recovered by another means")
        print("\nIf the discrepancy count above shows missing emails,")
        print("they exist but can't be found via standard JMAP queries.")
        print("Contact Fastmail support with the discrepancy details.")

    if dry_run and all_orphans:
        print("\n*** DRY RUN -- no changes made. Use --apply to recover. ***")


if __name__ == "__main__":
    main()
