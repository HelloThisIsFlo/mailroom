"""Reset module: undoes all Mailroom changes (contacts, labels, groups)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import httpx
import vobject

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.core.logging import configure_logging

MAILROOM_HEADER = "\u2014 Mailroom \u2014"


@dataclass
class ContactCleanup:
    """A contact that needs its Mailroom note section stripped."""

    href: str
    etag: str
    fn: str
    uid: str
    note: str
    stripped_note: str
    likely_created: bool
    vcard_data: str


@dataclass
class ResetPlan:
    """What the reset will do, built by plan_reset()."""

    email_labels: dict[str, list[str]]  # mailbox_name -> email_ids
    group_members: dict[str, list[str]]  # group_name -> contact_uids
    contacts_to_clean: list[ContactCleanup]


@dataclass
class ResetResult:
    """Outcome of apply_reset()."""

    emails_unlabeled: int = 0
    groups_emptied: int = 0
    contacts_cleaned: int = 0
    errors: list[str] = field(default_factory=list)


def _strip_mailroom_note(note: str) -> str:
    """Remove the Mailroom section from a contact note.

    If the note is only the Mailroom section, returns empty string.
    If the note has pre-existing content before the Mailroom header,
    preserves it (stripped of trailing whitespace/newlines).
    """
    if MAILROOM_HEADER not in note:
        return note

    before = note.split(MAILROOM_HEADER)[0].rstrip()
    return before


def _get_managed_mailbox_names(settings: MailroomSettings) -> list[str]:
    """Get all managed mailbox names, excluding Inbox and Screener."""
    excluded = {"Inbox", settings.triage.screener_mailbox}
    return [name for name in settings.required_mailboxes if name not in excluded]


def plan_reset(
    settings: MailroomSettings,
    jmap: JMAPClient,
    carddav: CardDAVClient,
) -> ResetPlan:
    """Build a plan of what to clean.

    Queries all managed mailboxes for emails, fetches all contacts,
    identifies those with Mailroom notes, and determines group memberships.

    Args:
        settings: Mailroom configuration.
        jmap: Connected JMAP client.
        carddav: Connected CardDAV client.

    Returns:
        ResetPlan with email_labels, group_members, and contacts_to_clean.
    """
    managed_names = _get_managed_mailbox_names(settings)
    managed_group_names = set(settings.contact_groups)

    # Resolve managed mailbox IDs
    mailbox_ids = jmap.resolve_mailboxes(managed_names)

    # Query emails per managed mailbox
    email_labels: dict[str, list[str]] = {}
    for name in managed_names:
        mb_id = mailbox_ids[name]
        ids = jmap.query_emails(mb_id)
        if ids:
            email_labels[name] = ids

    # Fetch all contacts
    all_contacts = carddav.list_all_contacts()

    # Filter to contacts with Mailroom note
    annotated = [c for c in all_contacts if MAILROOM_HEADER in c["note"]]

    # Determine group memberships
    group_members: dict[str, list[str]] = {}
    for group_name in managed_group_names:
        if group_name not in carddav._groups:
            continue
        try:
            member_uids = carddav.get_group_members(group_name)
            if member_uids:
                group_members[group_name] = member_uids
        except Exception:
            pass  # Group may not be accessible

    # Build contact cleanup list
    contacts_to_clean: list[ContactCleanup] = []
    for contact in annotated:
        note = contact["note"]
        stripped = _strip_mailroom_note(note)

        # Determine likely_created:
        # (a) note is mailroom-only (stripped is empty)
        # (b) all group memberships are managed groups
        note_is_mailroom_only = stripped == ""

        # Check group memberships — use the group_members we built
        contact_groups_set: set[str] = set()
        for gname, uids in group_members.items():
            if contact["uid"] in uids:
                contact_groups_set.add(gname)

        all_managed = len(contact_groups_set) > 0 and contact_groups_set.issubset(managed_group_names)

        likely_created = note_is_mailroom_only and all_managed

        contacts_to_clean.append(ContactCleanup(
            href=contact["href"],
            etag=contact["etag"],
            fn=contact["fn"],
            uid=contact["uid"],
            note=note,
            stripped_note=stripped,
            likely_created=likely_created,
            vcard_data=contact["vcard_data"],
        ))

    return ResetPlan(
        email_labels=email_labels,
        group_members=group_members,
        contacts_to_clean=contacts_to_clean,
    )


def apply_reset(
    plan: ResetPlan,
    jmap: JMAPClient,
    carddav: CardDAVClient,
    settings: MailroomSettings,
) -> ResetResult:
    """Execute the reset plan.

    Operation order:
    1. Remove labels from emails
    2. Remove contacts from groups
    3. Strip Mailroom notes from contacts

    Args:
        plan: The reset plan from plan_reset().
        jmap: Connected JMAP client.
        carddav: Connected CardDAV client.
        settings: Mailroom configuration.

    Returns:
        ResetResult with counts and any errors.
    """
    result = ResetResult()

    # Resolve mailbox IDs for label removal
    label_names = list(plan.email_labels.keys())
    if label_names:
        mailbox_ids = jmap.resolve_mailboxes(label_names)
    else:
        mailbox_ids = {}

    # Step 1: Remove labels from emails
    for label_name, email_ids in plan.email_labels.items():
        mb_id = mailbox_ids[label_name]
        try:
            jmap.batch_remove_labels(email_ids, [mb_id])
            result.emails_unlabeled += len(email_ids)
        except RuntimeError as exc:
            result.errors.append(f"Label removal ({label_name}): {exc}")

    # Step 2: Remove contacts from groups
    groups_emptied: set[str] = set()
    for group_name, member_uids in plan.group_members.items():
        for uid in member_uids:
            try:
                carddav.remove_from_group(group_name, uid)
            except RuntimeError as exc:
                result.errors.append(f"Group removal ({group_name}/{uid}): {exc}")
        groups_emptied.add(group_name)
    result.groups_emptied = len(groups_emptied)

    # Step 3: Strip Mailroom notes from contacts
    for contact in plan.contacts_to_clean:
        try:
            # Parse the vCard, update the NOTE field
            card = vobject.readOne(contact.vcard_data)
            note_entries = card.contents.get("note", [])

            if contact.stripped_note:
                # Has pre-existing content — keep it
                if note_entries:
                    note_entries[0].value = contact.stripped_note
                else:
                    card.add("note").value = contact.stripped_note
            else:
                # Mailroom-only note — clear it
                if note_entries:
                    note_entries[0].value = ""

            vcard_bytes = card.serialize().encode("utf-8")
            carddav.update_contact_vcard(contact.href, contact.etag, vcard_bytes)
            result.contacts_cleaned += 1
        except Exception as exc:
            result.errors.append(f"Note cleanup ({contact.fn}): {exc}")

    return result


def run_reset(apply: bool = False) -> int:
    """Top-level entry point for the reset command.

    Loads config, connects clients, plans reset, and optionally
    applies changes. Returns exit code 0 on success, 1 on failure.

    Args:
        apply: If True, execute cleanup. If False, dry-run only.

    Returns:
        Exit code: 0 if no errors, 1 if any errors.
    """
    from mailroom.reset.reporting import print_reset_report

    # Load config
    try:
        settings = MailroomSettings()
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    configure_logging(settings.logging.level)

    # Connect JMAP
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

    # Connect CardDAV
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

    # Validate groups + provenance group (needed for group operations)
    carddav.validate_groups(settings.contact_groups + [settings.mailroom.provenance_group])

    # Build plan
    reset_plan = plan_reset(settings, jmap, carddav)

    if not apply:
        print_reset_report(reset_plan, apply=False)
        return 0

    # Apply
    reset_result = apply_reset(reset_plan, jmap, carddav, settings)
    print_reset_report(reset_result, apply=True)

    return 1 if reset_result.errors else 0
