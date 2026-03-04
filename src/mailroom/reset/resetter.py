"""Reset module: undoes all Mailroom changes (contacts, labels, groups).

Provenance-aware: contacts created by Mailroom are DELETEd (if unmodified)
or warned (if user-modified). Adopted contacts just get notes stripped.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Literal

import httpx
import vobject

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.core.logging import configure_logging

MAILROOM_HEADER = "\u2014 Mailroom \u2014"

# Fields that Mailroom sets on contacts it creates/manages
MAILROOM_MANAGED_FIELDS = {
    "version", "uid", "fn", "n", "email", "note", "org", "prodid",
}
# x-addressbookserver-* fields are Apple system fields, not user data
_SYSTEM_FIELD_PREFIXES = ("x-addressbookserver-",)


def _is_user_modified(vcard_data: str) -> bool:
    """Detect whether a contact has been modified by the user.

    Compares vCard fields against what Mailroom creates. Extra fields
    (phone, address, photo, etc.) indicate user modification. Multiple
    EMAIL entries also indicate user modification.

    Apple system fields (x-addressbookserver-*) are ignored.

    Args:
        vcard_data: Raw vCard string.

    Returns:
        True if the contact has user-added fields beyond Mailroom's set.
    """
    card = vobject.readOne(vcard_data)
    content_keys = {k.lower() for k in card.contents.keys()}
    # Filter out system fields
    user_fields = {
        k for k in content_keys
        if not any(k.startswith(p) for p in _SYSTEM_FIELD_PREFIXES)
    }
    extra = user_fields - MAILROOM_MANAGED_FIELDS
    if extra:
        return True
    # Multiple EMAIL entries = user added one
    if len(card.contents.get("email", [])) > 1:
        return True
    return False


@dataclass
class ContactCleanup:
    """A contact identified for reset cleanup.

    The provenance field determines the action:
    - created_unmodified: DELETE the contact entirely
    - created_modified: WARN (apply @MailroomWarning to emails) + strip note
    - adopted: strip note only
    """

    href: str
    etag: str
    fn: str
    uid: str
    note: str
    stripped_note: str
    provenance: Literal["created_unmodified", "created_modified", "adopted"]
    email: str | None  # sender email for warning application
    vcard_data: str


@dataclass
class ResetPlan:
    """What the reset will do, built by plan_reset()."""

    email_labels: dict[str, list[str]]  # mailbox_name -> email_ids
    group_members: dict[str, list[str]]  # group_name -> contact_uids
    contacts_to_delete: list[ContactCleanup]  # provenance + unmodified
    contacts_to_warn: list[ContactCleanup]  # provenance + user-modified
    contacts_to_strip: list[ContactCleanup]  # adopted (no provenance, has note)


@dataclass
class ResetResult:
    """Outcome of apply_reset()."""

    emails_unlabeled: int = 0
    groups_emptied: int = 0
    contacts_deleted: int = 0
    contacts_warned: int = 0
    contacts_cleaned: int = 0  # strip-only (adopted)
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


def _extract_email_from_vcard(vcard_data: str) -> str | None:
    """Extract the first email address from a vCard string."""
    try:
        card = vobject.readOne(vcard_data)
        emails = card.contents.get("email", [])
        if emails:
            return emails[0].value.lower()
    except Exception:
        pass
    return None


def plan_reset(
    settings: MailroomSettings,
    jmap: JMAPClient,
    carddav: CardDAVClient,
) -> ResetPlan:
    """Build a provenance-aware plan of what to clean.

    Queries all managed mailboxes for emails, fetches all contacts,
    identifies those with Mailroom notes, and classifies them by provenance:
    - In provenance group + unmodified -> contacts_to_delete
    - In provenance group + user-modified -> contacts_to_warn
    - Not in provenance group + has note -> contacts_to_strip

    Args:
        settings: Mailroom configuration.
        jmap: Connected JMAP client.
        carddav: Connected CardDAV client.

    Returns:
        ResetPlan with email_labels, group_members, and three contact lists.
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

    # Determine group memberships for category groups
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

    # Get provenance group members
    provenance_group = settings.mailroom.provenance_group
    provenance_uids: set[str] = set()
    try:
        provenance_uids = set(carddav.get_group_members(provenance_group))
    except Exception:
        pass

    # Classify contacts by provenance
    contacts_to_delete: list[ContactCleanup] = []
    contacts_to_warn: list[ContactCleanup] = []
    contacts_to_strip: list[ContactCleanup] = []

    for contact in annotated:
        note = contact["note"]
        stripped = _strip_mailroom_note(note)
        sender_email = _extract_email_from_vcard(contact["vcard_data"])
        # Fallback: try emails list from list_all_contacts
        if not sender_email and contact.get("emails"):
            sender_email = contact["emails"][0]

        cleanup = ContactCleanup(
            href=contact["href"],
            etag=contact["etag"],
            fn=contact["fn"],
            uid=contact["uid"],
            note=note,
            stripped_note=stripped,
            provenance="adopted",  # default, overridden below
            email=sender_email,
            vcard_data=contact["vcard_data"],
        )

        if contact["uid"] in provenance_uids:
            # In provenance group -- check if user-modified
            if _is_user_modified(contact["vcard_data"]):
                cleanup.provenance = "created_modified"
                contacts_to_warn.append(cleanup)
            else:
                cleanup.provenance = "created_unmodified"
                contacts_to_delete.append(cleanup)
        else:
            # Not in provenance group -- adopted
            cleanup.provenance = "adopted"
            contacts_to_strip.append(cleanup)

    return ResetPlan(
        email_labels=email_labels,
        group_members=group_members,
        contacts_to_delete=contacts_to_delete,
        contacts_to_warn=contacts_to_warn,
        contacts_to_strip=contacts_to_strip,
    )


def apply_reset(
    plan: ResetPlan,
    jmap: JMAPClient,
    carddav: CardDAVClient,
    settings: MailroomSettings,
) -> ResetResult:
    """Execute the reset plan with provenance-aware 7-step order.

    Operation order (from CONTEXT.md):
    1. Remove managed labels from emails (Feed, Imbox, etc.)
    2. Remove @MailroomWarning + @MailroomError from ALL emails (clean slate)
    3. Remove contacts from category groups
    4. For provenance + user-modified contacts: apply @MailroomWarning to emails
    5. Remove warned contacts from provenance group
    6. Strip Mailroom notes from ALL annotated contacts
    7. DELETE unmodified provenance contacts

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
    # Always resolve warning + error mailboxes for step 2
    resolve_names = list(set(label_names + [
        settings.mailroom.label_warning,
        settings.mailroom.label_error,
    ]))
    if resolve_names:
        mailbox_ids = jmap.resolve_mailboxes(resolve_names)
    else:
        mailbox_ids = {}

    # === Step 1: Remove managed labels from emails ===
    for label_name, email_ids in plan.email_labels.items():
        mb_id = mailbox_ids[label_name]
        try:
            jmap.batch_remove_labels(email_ids, [mb_id])
            result.emails_unlabeled += len(email_ids)
        except RuntimeError as exc:
            result.errors.append(f"Label removal ({label_name}): {exc}")

    # === Step 2: Remove @MailroomWarning + @MailroomError from ALL emails ===
    for system_label in [settings.mailroom.label_warning, settings.mailroom.label_error]:
        if system_label in mailbox_ids:
            mb_id = mailbox_ids[system_label]
            try:
                system_emails = jmap.query_emails(mb_id)
                if system_emails:
                    jmap.batch_remove_labels(system_emails, [mb_id])
            except RuntimeError as exc:
                result.errors.append(f"System label cleanup ({system_label}): {exc}")

    # === Step 3: Remove contacts from category groups ===
    groups_emptied: set[str] = set()
    for group_name, member_uids in plan.group_members.items():
        for uid in member_uids:
            try:
                carddav.remove_from_group(group_name, uid)
            except RuntimeError as exc:
                result.errors.append(f"Group removal ({group_name}/{uid}): {exc}")
        groups_emptied.add(group_name)
    result.groups_emptied = len(groups_emptied)

    # === Step 4: Apply @MailroomWarning to user-modified provenance contacts' emails ===
    warning_mb_id = mailbox_ids.get(settings.mailroom.label_warning)
    for contact in plan.contacts_to_warn:
        if contact.email and warning_mb_id:
            try:
                sender_emails = jmap.query_emails_by_sender(contact.email)
                if sender_emails:
                    jmap.batch_add_labels(sender_emails, [warning_mb_id])
                result.contacts_warned += 1
            except RuntimeError as exc:
                result.errors.append(f"Warning application ({contact.fn}): {exc}")
        else:
            result.contacts_warned += 1

    # === Step 5: Remove warned contacts from provenance group ===
    provenance_group = settings.mailroom.provenance_group
    for contact in plan.contacts_to_warn:
        try:
            carddav.remove_from_group(provenance_group, contact.uid)
        except RuntimeError as exc:
            result.errors.append(f"Provenance removal ({contact.fn}): {exc}")

    # === Step 6: Strip Mailroom notes from ALL annotated contacts ===
    all_contacts = plan.contacts_to_delete + plan.contacts_to_warn + plan.contacts_to_strip
    for contact in all_contacts:
        try:
            card = vobject.readOne(contact.vcard_data)
            note_entries = card.contents.get("note", [])

            if contact.stripped_note:
                # Has pre-existing content -- keep it
                if note_entries:
                    note_entries[0].value = contact.stripped_note
                else:
                    card.add("note").value = contact.stripped_note
            else:
                # Mailroom-only note -- clear it
                if note_entries:
                    note_entries[0].value = ""

            vcard_bytes = card.serialize().encode("utf-8")
            carddav.update_contact_vcard(contact.href, contact.etag, vcard_bytes)
        except Exception as exc:
            result.errors.append(f"Note cleanup ({contact.fn}): {exc}")

    # Count strip-only (adopted) contacts
    result.contacts_cleaned = len(plan.contacts_to_strip)

    # === Step 7: DELETE unmodified provenance contacts ===
    for contact in plan.contacts_to_delete:
        try:
            carddav.delete_contact(contact.href, contact.etag)
            result.contacts_deleted += 1
        except Exception as exc:
            result.errors.append(f"Contact deletion ({contact.fn}): {exc}")

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
