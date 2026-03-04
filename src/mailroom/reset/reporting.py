"""Output formatting for the reset command with terraform-style sections."""

from __future__ import annotations

import sys

from mailroom.setup.colors import GREEN, YELLOW, RED, DIM, RESET, CYAN, color


def print_reset_report(plan_or_result: object, apply: bool) -> None:
    """Print terraform-style reset report.

    In dry-run mode (apply=False), expects a ResetPlan and shows what would be cleaned.
    In apply mode (apply=True), expects a ResetResult and shows what was cleaned.

    Args:
        plan_or_result: ResetPlan (dry-run) or ResetResult (apply).
        apply: Whether this is an apply result (vs. dry-run plan).
    """
    from mailroom.reset.resetter import ResetPlan, ResetResult

    out = sys.stdout
    print(file=out)

    if apply and isinstance(plan_or_result, ResetResult):
        _print_apply_report(plan_or_result, out)
    elif not apply and isinstance(plan_or_result, ResetPlan):
        _print_plan_report(plan_or_result, out)


def _print_plan_report(plan: object, out: object) -> None:
    """Print dry-run plan report."""
    from mailroom.reset.resetter import ResetPlan

    assert isinstance(plan, ResetPlan)

    # Email Labels section
    if plan.email_labels:
        print("Email Labels to Clean", file=out)
        for label_name, email_ids in plan.email_labels.items():
            symbol = color("\u2717", RED)  # X mark for removal
            count = len(email_ids)
            print(f"  {symbol} {label_name:<30} {color(f'{count} emails', YELLOW)}", file=out)
        print(file=out)

    # Contact Groups section
    if plan.group_members:
        print("Contact Groups to Empty", file=out)
        for group_name, member_uids in plan.group_members.items():
            symbol = color("\u2717", RED)
            count = len(member_uids)
            print(f"  {symbol} {group_name:<30} {color(f'{count} members', YELLOW)}", file=out)
        print(file=out)

    # Contacts to Clean section
    non_likely = [c for c in plan.contacts_to_clean if not c.likely_created]
    if non_likely:
        print("Contacts to Clean (strip note)", file=out)
        for contact in non_likely:
            symbol = color("\u270e", YELLOW)  # pencil
            print(f"  {symbol} {contact.fn:<30} {color('strip note', DIM)}", file=out)
        print(file=out)

    # Likely-created section
    likely = [c for c in plan.contacts_to_clean if c.likely_created]
    if likely:
        print("Likely Mailroom-Created Contacts", file=out)
        print(color("  (Consider manual deletion after reset)", DIM), file=out)
        for contact in likely:
            symbol = color("!", YELLOW)
            print(f"  {symbol} {contact.fn:<30} {color('strip note', DIM)}", file=out)
        print(file=out)

    # Summary
    total_emails = sum(len(ids) for ids in plan.email_labels.values())
    total_groups = len(plan.group_members)
    total_contacts = len(plan.contacts_to_clean)

    parts = [
        f"{total_emails} emails to un-label",
        f"{total_groups} groups to empty",
        f"{total_contacts} contacts to clean",
    ]
    print(" \u00b7 ".join(parts), file=out)

    if likely:
        print(
            color(f"  + {len(likely)} likely Mailroom-created (manual deletion recommended)", YELLOW),
            file=out,
        )


def _print_apply_report(result: object, out: object) -> None:
    """Print apply result report."""
    from mailroom.reset.resetter import ResetResult

    assert isinstance(result, ResetResult)

    print("Reset Complete", file=out)
    print(file=out)

    parts = [
        f"{result.emails_unlabeled} emails un-labeled",
        f"{result.groups_emptied} groups emptied",
        f"{result.contacts_cleaned} contacts cleaned",
    ]
    print(" \u00b7 ".join(parts), file=out)

    if result.errors:
        print(file=out)
        print(color("Errors:", RED), file=out)
        for err in result.errors:
            print(f"  {color('\u2717', RED)} {err}", file=out)
