"""Provisioner: orchestrates resource creation with dry-run/apply pattern."""

from __future__ import annotations

import sys

import httpx

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.core.logging import configure_logging
from mailroom.setup.reporting import ResourceAction, print_plan
from mailroom.setup.sieve_guidance import generate_sieve_guidance


def plan_resources(
    settings: MailroomSettings,
    jmap: JMAPClient,
    carddav: CardDAVClient,
) -> list[ResourceAction]:
    """Build resource plan: check what exists, what needs creating.

    Fetches all existing mailboxes and contact groups, then compares
    against the config-derived required resources. Returns a list of
    ResourceAction objects with status "exists" or "create".

    Args:
        settings: Mailroom config with required_mailboxes, triage_labels,
            contact_groups properties.
        jmap: Connected JMAP client.
        carddav: Connected CardDAV client.

    Returns:
        List of ResourceAction objects categorized as mailbox, label,
        or contact_group.
    """
    # Fetch all existing mailboxes
    responses = jmap.call(
        [["Mailbox/get", {"accountId": jmap.account_id, "ids": None}, "m0"]]
    )
    mailbox_list = responses[0][1]["list"]

    # Build set of existing mailbox names (with Inbox role handling)
    existing_mailboxes: set[str] = set()
    for mb in mailbox_list:
        if mb.get("role") == "inbox":
            existing_mailboxes.add("Inbox")
        existing_mailboxes.add(mb["name"])

    # Fetch all existing contact groups
    existing_groups = carddav.list_groups()

    # Categorize resources
    triage_label_set = set(settings.triage_labels)
    mailbox_names = [
        name for name in settings.required_mailboxes if name not in triage_label_set
    ]

    actions: list[ResourceAction] = []

    # Mailboxes (destination + system, NOT triage labels)
    for name in mailbox_names:
        status = "exists" if name in existing_mailboxes else "create"
        actions.append(ResourceAction(kind="mailbox", name=name, status=status))

    # Action Labels (triage labels)
    for name in settings.triage_labels:
        status = "exists" if name in existing_mailboxes else "create"
        actions.append(ResourceAction(kind="label", name=name, status=status))

    # Contact Groups
    for name in settings.contact_groups:
        status = "exists" if name in existing_groups else "create"
        actions.append(
            ResourceAction(kind="contact_group", name=name, status=status)
        )

    return actions


def apply_resources(
    plan: list[ResourceAction],
    jmap: JMAPClient,
    carddav: CardDAVClient,
) -> list[ResourceAction]:
    """Execute the plan, creating missing resources.

    Processes resources in order: mailboxes first, then action labels
    (also mailboxes), then contact groups. Tracks parent failures to
    skip dependent children.

    Args:
        plan: List of ResourceAction objects from plan_resources().
        jmap: Connected JMAP client.
        carddav: Connected CardDAV client.

    Returns:
        Updated list of ResourceAction objects with final statuses.
    """
    # Track which resources failed so children can be skipped
    failed_names: set[str] = set()
    result: list[ResourceAction] = []

    # Process in order: mailboxes, labels (also JMAP mailboxes), contact groups
    mailboxes = [a for a in plan if a.kind == "mailbox"]
    labels = [a for a in plan if a.kind == "label"]
    groups = [a for a in plan if a.kind == "contact_group"]

    for action in mailboxes + labels:
        if action.status == "exists":
            result.append(action)
            continue

        # Check if parent failed (for future hierarchy support)
        if action.parent and action.parent in failed_names:
            result.append(
                ResourceAction(
                    kind=action.kind,
                    name=action.name,
                    status="skipped",
                    parent=action.parent,
                    error="parent failed",
                )
            )
            continue

        try:
            jmap.create_mailbox(action.name)
            result.append(
                ResourceAction(
                    kind=action.kind,
                    name=action.name,
                    status="created",
                    parent=action.parent,
                )
            )
        except (RuntimeError, httpx.HTTPStatusError) as exc:
            failed_names.add(action.name)
            result.append(
                ResourceAction(
                    kind=action.kind,
                    name=action.name,
                    status="failed",
                    parent=action.parent,
                    error=str(exc),
                )
            )

    for action in groups:
        if action.status == "exists":
            result.append(action)
            continue

        try:
            carddav.create_group(action.name)
            result.append(
                ResourceAction(
                    kind=action.kind,
                    name=action.name,
                    status="created",
                )
            )
        except (RuntimeError, httpx.HTTPStatusError) as exc:
            result.append(
                ResourceAction(
                    kind=action.kind,
                    name=action.name,
                    status="failed",
                    error=str(exc),
                )
            )

    return result


def run_setup(apply: bool = False, ui_guide: bool = False) -> int:
    """Top-level entry point for the setup command.

    Loads config, connects clients, plans resources, and optionally
    applies changes. Returns exit code 0 on success, 1 on failure.

    Args:
        apply: If True, create missing resources. If False, dry-run only.
        ui_guide: If True, show Fastmail UI instructions (passed through
            for Plan 03 sieve guidance).

    Returns:
        Exit code: 0 if no failures, 1 if any failed.
    """
    # Load config
    try:
        settings = MailroomSettings()
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    configure_logging(settings.log_level)

    # Pre-flight: connect JMAP
    jmap = JMAPClient(token=settings.jmap_token)
    try:
        jmap.connect()
    except httpx.HTTPStatusError as exc:
        print(
            f"JMAP connection failed: {exc.response.status_code} "
            f"{exc.response.reason_phrase}",
            file=sys.stderr,
        )
        return 1
    except httpx.ConnectError as exc:
        print(f"JMAP connection failed: {exc}", file=sys.stderr)
        return 1

    # Pre-flight: connect CardDAV
    carddav = CardDAVClient(
        username=settings.carddav_username,
        password=settings.carddav_password,
    )
    try:
        carddav.connect()
    except httpx.HTTPStatusError as exc:
        print(
            f"CardDAV connection failed: {exc.response.status_code} "
            f"{exc.response.reason_phrase}",
            file=sys.stderr,
        )
        return 1
    except httpx.ConnectError as exc:
        print(f"CardDAV connection failed: {exc}", file=sys.stderr)
        return 1

    # Plan resources
    resource_plan = plan_resources(settings, jmap, carddav)

    if not apply:
        # Dry-run: show plan and exit
        print_plan(resource_plan, apply=False)
        print()
        print(generate_sieve_guidance(settings, ui_guide=ui_guide))
        return 0

    # Apply: create missing resources
    result = apply_resources(resource_plan, jmap, carddav)
    print_plan(result, apply=True)
    print()
    print(generate_sieve_guidance(settings, ui_guide=ui_guide))

    # Exit code: 1 if any failures
    has_failures = any(a.status == "failed" for a in result)
    return 1 if has_failures else 0
