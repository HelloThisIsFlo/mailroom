"""Batched vs sequential JMAP queries — performance comparison (read-only, safe).

Compares two approaches for querying all triage label mailboxes:
  1. Batched: all Email/query calls in a single JMAP HTTP request
  2. Sequential: one HTTP request per label

Usage:
    python .research/triage-label-scan/batched_vs_sequential.py
    python .research/triage-label-scan/batched_vs_sequential.py --include-senders
    python .research/triage-label-scan/batched_vs_sequential.py --include-subjects
"""

import argparse
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings, resolve_categories


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan triage label mailboxes and measure query performance"
    )
    parser.add_argument(
        "--include-senders",
        action="store_true",
        help="Also fetch sender info for emails in each label (extra API call)",
    )
    parser.add_argument(
        "--include-subjects",
        action="store_true",
        help="Also fetch subjects for emails in each label (extra API call)",
    )
    args = parser.parse_args()

    settings = MailroomSettings()
    categories = resolve_categories(settings.triage.categories)

    # Collect all label names + system labels
    label_names = [c.label for c in categories]
    system_labels = [settings.labels.mailroom_error]
    if settings.labels.warnings_enabled:
        system_labels.append(settings.labels.mailroom_warning)

    all_labels = label_names + system_labels

    print("Connecting to Fastmail JMAP...")
    client = JMAPClient(token=settings.jmap_token)
    client.connect()
    print(f"  Connected! Account ID: {client.account_id}\n")

    # ──────────────────────────────────────────────
    # Strategy 1: Batched — resolve + query all labels in one JMAP call
    # ──────────────────────────────────────────────
    print("=" * 65)
    print("Strategy 1: BATCHED — single JMAP call for all labels")
    print("=" * 65)

    t0 = time.perf_counter()

    # Build a single JMAP request that resolves mailboxes and queries
    # each label mailbox in one round-trip
    resolve_t0 = time.perf_counter()
    mailbox_ids = client.resolve_mailboxes(all_labels)
    resolve_elapsed = time.perf_counter() - resolve_t0
    print(f"\n  Mailbox resolution: {resolve_elapsed:.3f}s ({len(mailbox_ids)} mailboxes)")

    # Build batched Email/query calls — one per label
    method_calls = []
    for i, label in enumerate(all_labels):
        mb_id = mailbox_ids[label]
        method_calls.append([
            "Email/query",
            {
                "accountId": client.account_id,
                "filter": {"inMailbox": mb_id},
                "limit": 0,  # We only need the total count
            },
            f"q{i}",
        ])

    query_t0 = time.perf_counter()
    responses = client.call(method_calls)
    query_elapsed = time.perf_counter() - query_t0

    total_elapsed = time.perf_counter() - t0

    print(f"  Batched query:      {query_elapsed:.3f}s ({len(all_labels)} labels in 1 call)")
    print(f"  Total (resolve+query): {total_elapsed:.3f}s\n")

    label_counts: dict[str, int] = {}
    for i, label in enumerate(all_labels):
        data = responses[i][1]
        total = data.get("total", 0)
        label_counts[label] = total

    # Print results table
    print(f"  {'Label':<25} {'Emails':>8}")
    print(f"  {'─' * 25} {'─' * 8}")
    grand_total = 0
    for label in all_labels:
        count = label_counts[label]
        grand_total += count
        marker = " ←" if count > 0 else ""
        tag = " (system)" if label in system_labels else ""
        print(f"  {label + tag:<25} {count:>8}{marker}")
    print(f"  {'─' * 25} {'─' * 8}")
    print(f"  {'TOTAL':<25} {grand_total:>8}")

    # ──────────────────────────────────────────────
    # Strategy 2: Sequential — one JMAP call per label (baseline)
    # ──────────────────────────────────────────────
    print(f"\n{'=' * 65}")
    print("Strategy 2: SEQUENTIAL — one JMAP call per label")
    print("=" * 65)
    print()

    seq_t0 = time.perf_counter()
    seq_timings: list[tuple[str, float, int]] = []

    for label in all_labels:
        mb_id = mailbox_ids[label]
        lt0 = time.perf_counter()
        resp = client.call([
            [
                "Email/query",
                {
                    "accountId": client.account_id,
                    "filter": {"inMailbox": mb_id},
                    "limit": 0,
                },
                "q0",
            ]
        ])
        elapsed = time.perf_counter() - lt0
        total = resp[0][1].get("total", 0)
        seq_timings.append((label, elapsed, total))

    seq_total = time.perf_counter() - seq_t0

    print(f"  {'Label':<25} {'Time':>8} {'Emails':>8}")
    print(f"  {'─' * 25} {'─' * 8} {'─' * 8}")
    for label, elapsed, count in seq_timings:
        tag = " (sys)" if label in system_labels else ""
        print(f"  {label + tag:<25} {elapsed:>7.3f}s {count:>8}")
    print(f"  {'─' * 25} {'─' * 8} {'─' * 8}")
    print(f"  {'TOTAL':<25} {seq_total:>7.3f}s {grand_total:>8}")

    # ──────────────────────────────────────────────
    # Optional: fetch sender details for non-empty labels
    # ──────────────────────────────────────────────
    if args.include_senders or args.include_subjects:
        non_empty = [l for l in all_labels if label_counts[l] > 0]
        if non_empty:
            print(f"\n{'=' * 65}")
            print("Email details for non-empty labels")
            print("=" * 65)

            props = ["id", "from"]
            if args.include_subjects:
                props.append("subject")

            for label in non_empty:
                mb_id = mailbox_ids[label]
                dt0 = time.perf_counter()

                # Query email IDs (paginated, up to 500)
                email_ids = client.query_emails(mb_id, limit=100)
                if not email_ids:
                    continue

                # Fetch details
                resp = client.call([
                    [
                        "Email/get",
                        {
                            "accountId": client.account_id,
                            "ids": email_ids[:200],  # Cap at 200 for safety
                            "properties": props,
                        },
                        "g0",
                    ]
                ])
                emails = resp[0][1]["list"]
                detail_elapsed = time.perf_counter() - dt0

                tag = " (system)" if label in system_labels else ""
                print(f"\n  {label}{tag} — {len(emails)} email(s), fetched in {detail_elapsed:.3f}s:")
                for email in emails[:20]:  # Show up to 20
                    from_list = email.get("from", [])
                    sender = from_list[0]["email"] if from_list else "(unknown)"
                    name = from_list[0].get("name", "") if from_list else ""
                    display = f"{name} <{sender}>" if name else sender
                    if args.include_subjects:
                        subj = email.get("subject", "(no subject)")
                        print(f"    {display}")
                        print(f"      └─ {subj}")
                    else:
                        print(f"    {display}")
                if len(emails) > 20:
                    print(f"    ... and {len(emails) - 20} more")

    # ──────────────────────────────────────────────
    # Summary / verdict
    # ──────────────────────────────────────────────
    print(f"\n{'=' * 65}")
    print("Summary")
    print("=" * 65)
    print(f"  Labels scanned:      {len(all_labels)}")
    print(f"  Total emails found:  {grand_total}")
    print(f"  Batched approach:    {total_elapsed:.3f}s (1 resolve + 1 batched query)")
    print(f"  Sequential approach: {seq_total:.3f}s + {resolve_elapsed:.3f}s resolve")
    print(f"  Speedup:             {(seq_total + resolve_elapsed) / total_elapsed:.1f}x")
    print()

    if total_elapsed < 1.0:
        print("  ✓ FAST — scanning all labels is well within poll budget")
    elif total_elapsed < 3.0:
        print("  ~ OK — scanning all labels is acceptable but not instant")
    else:
        print("  ✗ SLOW — consider scanning only specific labels or caching")

    print()


if __name__ == "__main__":
    main()
