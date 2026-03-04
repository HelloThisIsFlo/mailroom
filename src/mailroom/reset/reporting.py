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
    """Print dry-run plan report with provenance-aware sections."""
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

    # Contacts to DELETE section (provenance + unmodified)
    if plan.contacts_to_delete:
        print("Contacts to DELETE", file=out)
        for contact in plan.contacts_to_delete:
            symbol = color("\u2717", RED)  # X mark
            print(f"  {symbol} {contact.fn:<30} {color('delete', RED)}", file=out)
        print(file=out)

    # Contacts to WARN section (provenance + user-modified)
    if plan.contacts_to_warn:
        print("Contacts to WARN", file=out)
        for contact in plan.contacts_to_warn:
            symbol = color("!", YELLOW)
            print(f"  {symbol} {contact.fn:<30} {color('warn + strip', YELLOW)}", file=out)
        print(file=out)

    # Contacts to strip section (adopted)
    if plan.contacts_to_strip:
        print("Contacts to strip (adopted)", file=out)
        for contact in plan.contacts_to_strip:
            symbol = color("\u270e", YELLOW)  # pencil
            print(f"  {symbol} {contact.fn:<30} {color('strip note', DIM)}", file=out)
        print(file=out)

    # Summary
    total_emails = sum(len(ids) for ids in plan.email_labels.values())
    total_groups = len(plan.group_members)
    total_delete = len(plan.contacts_to_delete)
    total_warn = len(plan.contacts_to_warn)
    total_strip = len(plan.contacts_to_strip)

    parts = [
        f"{total_emails} emails to un-label",
        f"{total_groups} groups to empty",
    ]
    if total_delete:
        parts.append(f"{total_delete} contacts to delete")
    if total_warn:
        parts.append(f"{total_warn} contacts to warn")
    if total_strip:
        parts.append(f"{total_strip} contacts to strip")

    print(" \u00b7 ".join(parts), file=out)


def _print_apply_report(result: object, out: object) -> None:
    """Print apply result report with provenance-aware counts."""
    from mailroom.reset.resetter import ResetResult

    assert isinstance(result, ResetResult)

    print("Reset Complete", file=out)
    print(file=out)

    parts = [
        f"{result.emails_unlabeled} emails un-labeled",
        f"{result.groups_emptied} groups emptied",
    ]
    if result.contacts_deleted:
        parts.append(f"{result.contacts_deleted} contacts deleted")
    if result.contacts_warned:
        parts.append(f"{result.contacts_warned} contacts warned")
    if result.contacts_cleaned:
        parts.append(f"{result.contacts_cleaned} contacts cleaned")

    print(" \u00b7 ".join(parts), file=out)

    if result.errors:
        print(file=out)
        print(color("Errors:", RED), file=out)
        for err in result.errors:
            print(f"  {color('\u2717', RED)} {err}", file=out)
