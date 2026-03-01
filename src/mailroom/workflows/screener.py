"""ScreenerWorkflow: poll cycle orchestration with conflict detection, error labeling, and per-sender triage processing."""

from __future__ import annotations

import structlog
import vobject

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings


class ScreenerWorkflow:
    """Orchestrates the screener triage pipeline.

    Calls JMAPClient and CardDAVClient methods in sequence.
    Contains business logic only -- no protocol details.

    The poll() method executes one poll cycle:
    1. Collect all triaged emails across all labels, grouped by sender
    2. Filter out emails already marked with @MailroomError
    3. Detect conflicting triage labels (same sender, different labels)
    4. Apply @MailroomError to conflicted senders
    5. Process each clean sender: check already-grouped, upsert contact,
       sweep Screener emails, remove triage label (last step)
    """

    def __init__(
        self,
        jmap: JMAPClient,
        carddav: CardDAVClient,
        settings: MailroomSettings,
        mailbox_ids: dict[str, str],
    ) -> None:
        self._jmap = jmap
        self._carddav = carddav
        self._settings = settings
        self._mailbox_ids = mailbox_ids
        self._log = structlog.get_logger(component="screener")

    def poll(self) -> int:
        """Execute one poll cycle. Returns count of successfully processed senders."""
        # Step 1: Collect all triaged emails grouped by sender
        triaged, sender_names = self._collect_triaged()

        # Step 2: If empty, log and return
        if not triaged:
            self._log.debug("poll_complete", triaged_senders=0)
            return 0

        # Step 3: Detect conflicts
        clean, conflicted = self._detect_conflicts(triaged)

        # Step 4: Apply @MailroomError to conflicted senders
        for sender, emails in conflicted.items():
            self._apply_error_label(sender, emails)

        # Step 5: Process each clean sender with try/except for retry safety
        processed = 0
        for sender, emails in clean.items():
            try:
                self._process_sender(sender, emails, sender_names)
                processed += 1
            except Exception:
                self._log.warning(
                    "sender_processing_failed",
                    sender=sender,
                    exc_info=True,
                )
                # Leave triage labels in place for retry on next poll (TRIAGE-06)

        # Step 6: Log summary
        self._log.info(
            "poll_complete",
            triaged_senders=len(triaged),
            processed=processed,
            conflicts=len(conflicted),
        )

        return processed

    def _collect_triaged(
        self,
    ) -> tuple[dict[str, list[tuple[str, str]]], dict[str, str | None]]:
        """Collect all triaged emails across all labels, grouped by sender.

        Returns:
            Tuple of (triaged, sender_names):
            - triaged: Dict mapping sender email -> list of (email_id, label_name) tuples.
              Emails already marked with @MailroomError are filtered out.
            - sender_names: Dict mapping sender email -> display name (or None).
              Stores the first non-None display name seen across a sender's emails.
        """
        # Collect emails from all triage labels
        raw: dict[str, list[tuple[str, str]]] = {}
        sender_names: dict[str, str | None] = {}
        all_email_ids: list[str] = []

        for label_name in self._settings.triage_labels:
            label_id = self._mailbox_ids[label_name]
            email_ids = self._jmap.query_emails(label_id)
            if not email_ids:
                continue

            # Get sender addresses and names for these emails
            senders = self._jmap.get_email_senders(email_ids)

            for email_id in email_ids:
                if email_id not in senders:
                    # Email has no From header -- skip with warning
                    self._log.warning(
                        "email_missing_sender",
                        email_id=email_id,
                        label=label_name,
                    )
                    continue

                sender_email, sender_name = senders[email_id]
                raw.setdefault(sender_email, []).append((email_id, label_name))
                all_email_ids.append(email_id)

                # Store first non-None name seen for this sender
                if sender_email not in sender_names or (
                    sender_names[sender_email] is None and sender_name is not None
                ):
                    sender_names[sender_email] = sender_name

        if not all_email_ids:
            return {}, {}

        # Filter out emails that already have @MailroomError
        error_id = self._mailbox_ids[self._settings.labels.mailroom_error]
        responses = self._jmap.call(
            [
                [
                    "Email/get",
                    {
                        "accountId": self._jmap.account_id,
                        "ids": all_email_ids,
                        "properties": ["id", "mailboxIds"],
                    },
                    "g0",
                ]
            ]
        )
        email_list = responses[0][1]["list"]

        # Build set of email IDs that have the error label
        errored_ids = {
            e["id"]
            for e in email_list
            if error_id in e.get("mailboxIds", {})
        }

        if not errored_ids:
            return raw, sender_names

        # Rebuild the dict without errored emails
        filtered: dict[str, list[tuple[str, str]]] = {}
        for sender, emails in raw.items():
            clean_emails = [
                (eid, label) for eid, label in emails if eid not in errored_ids
            ]
            if clean_emails:
                filtered[sender] = clean_emails

        return filtered, sender_names

    def _detect_conflicts(
        self,
        triaged: dict[str, list[tuple[str, str]]],
    ) -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[tuple[str, str]]]]:
        """Split senders into clean and conflicted.

        A sender is conflicted if they have emails with different triage labels.

        Returns:
            Tuple of (clean_senders, conflicted_senders).
        """
        clean: dict[str, list[tuple[str, str]]] = {}
        conflicted: dict[str, list[tuple[str, str]]] = {}

        for sender, emails in triaged.items():
            labels = {label for _, label in emails}
            if len(labels) > 1:
                conflicted[sender] = emails
            else:
                clean[sender] = emails

        return clean, conflicted

    def _apply_error_label(
        self,
        sender: str,
        emails: list[tuple[str, str]],
    ) -> None:
        """Apply @MailroomError to all emails for a conflicted sender.

        Keeps triage labels intact. The @MailroomError label is a signal
        to the user to resolve the conflict manually.
        """
        error_id = self._mailbox_ids[self._settings.labels.mailroom_error]

        try:
            for email_id, _ in emails:
                self._jmap.call(
                    [
                        [
                            "Email/set",
                            {
                                "accountId": self._jmap.account_id,
                                "update": {
                                    email_id: {f"mailboxIds/{error_id}": True}
                                },
                            },
                            "err0",
                        ]
                    ]
                )

            labels = {label for _, label in emails}
            self._log.warning(
                "conflict_detected",
                sender=sender,
                labels=sorted(labels),
                affected_emails=len(emails),
            )
        except Exception:
            self._log.error(
                "error_label_failed",
                sender=sender,
                exc_info=True,
            )
            # Transient failure -- do not crash the poll cycle

    def _apply_warning_label(
        self,
        sender: str,
        email_ids: list[str],
    ) -> None:
        """Apply @MailroomWarning to triggering emails for a name-mismatched sender.

        Non-blocking: exceptions are caught and logged. Processing continues
        even if warning label application fails.

        Args:
            sender: Sender email address (for logging).
            email_ids: List of triggering email IDs to apply the warning to.
        """
        warning_id = self._mailbox_ids[self._settings.labels.mailroom_warning]

        try:
            for email_id in email_ids:
                self._jmap.call(
                    [
                        [
                            "Email/set",
                            {
                                "accountId": self._jmap.account_id,
                                "update": {
                                    email_id: {f"mailboxIds/{warning_id}": True}
                                },
                            },
                            "warn0",
                        ]
                    ]
                )

            self._log.warning(
                "name_mismatch_warning",
                sender=sender,
                affected_emails=len(email_ids),
            )
        except Exception:
            self._log.warning(
                "warning_label_failed",
                sender=sender,
                exc_info=True,
            )
            # Non-blocking -- processing continues

    def _process_sender(
        self,
        sender: str,
        emails: list[tuple[str, str]],
        sender_names: dict[str, str | None] | None = None,
    ) -> None:
        """Process a single sender's triage.

        Steps execute in strict order. If any step fails, the exception
        propagates and the triage label is NOT removed (retry on next poll
        per TRIAGE-06).

        1. Extract label and group from emails
        2. Already-grouped check (TRIAGE-05 conflict detection)
        3. Upsert contact into group (TRIAGE-02)
        4. Sweep all Screener emails from sender (TRIAGE-03)
        5. Move swept emails to destination (TRIAGE-03 + TRIAGE-04)
        6. Remove triage label from triggering emails -- LAST STEP
        """
        label_name = emails[0][1]  # All emails have the same label (conflict-free)
        email_ids = [eid for eid, _ in emails]
        category = self._settings.label_to_category_mapping[label_name]
        group_name = category.contact_group
        contact_type = category.contact_type

        log = self._log.bind(sender=sender, label=label_name, group=group_name)

        # Step 1: Already-grouped check
        existing_group = self._check_already_grouped(sender, group_name)
        if existing_group is not None:
            # Sender is in a DIFFERENT group -- apply @MailroomError and return
            log.warning(
                "already_grouped",
                existing_group=existing_group,
                target_group=group_name,
            )
            self._apply_error_label(sender, emails)
            return

        # Step 2: Upsert contact into group (CardDAV)
        display_name = (sender_names or {}).get(sender)
        result = self._carddav.upsert_contact(
            sender, display_name, group_name, contact_type=contact_type
        )
        log.info("contact_upserted", action=result["action"], uid=result["uid"])

        # Step 2b: Apply warning label if name mismatch detected
        if result.get("name_mismatch", False) and self._settings.labels.warnings_enabled:
            self._apply_warning_label(sender, email_ids)

        # Step 3: Sweep all Screener emails from this sender (JMAP)
        screener_id = self._mailbox_ids[self._settings.triage.screener_mailbox]
        sender_emails = self._jmap.query_emails(screener_id, sender=sender)

        # Step 4: Move swept emails to destination
        if sender_emails:
            add_ids = self._get_destination_mailbox_ids(label_name)
            self._jmap.batch_move_emails(sender_emails, screener_id, add_ids)
            log.info("emails_swept", count=len(sender_emails))

        # Step 5: Remove triage label from triggering emails -- LAST STEP
        label_id = self._mailbox_ids[label_name]
        for email_id in email_ids:
            self._jmap.remove_label(email_id, label_id)

        log.info(
            "triage_complete",
            sender=sender,
            emails_moved=len(sender_emails),
        )

    def _get_destination_mailbox_ids(self, label_name: str) -> list[str]:
        """Return the mailbox IDs to add when sweeping for this label's destination.

        Looks up the destination_mailbox from the config mapping and resolves
        it to a mailbox ID.

        - Imbox: destination_mailbox is "Inbox", returns [inbox_id]
        - Feed/Paper Trail/Jail: destination_mailbox matches mailbox name
        """
        category = self._settings.label_to_category_mapping[label_name]
        destination_mailbox = category.destination_mailbox
        return [self._mailbox_ids[destination_mailbox]]

    def _check_already_grouped(
        self,
        sender: str,
        target_group: str,
    ) -> str | None:
        """Check if sender is already a member of a contact group different from the target.

        - Searches CardDAV for the sender's contact.
        - If no contact found: returns None (new sender, safe to proceed).
        - If contact found: checks group membership via CardDAVClient.check_membership.
        - If contact is in a non-target group: returns that group name (conflict).
        - If contact is in the target group or no group: returns None (safe).

        Transient CardDAV failures propagate up to _process_sender's try/except
        boundary (retry on next poll per TRIAGE-06).
        """
        results = self._carddav.search_by_email(sender)
        if not results:
            return None

        # Extract contact UID from vCard
        card = vobject.readOne(results[0]["vcard_data"])
        contact_uid = card.uid.value

        # Check if this contact is in any group other than the target
        return self._carddav.check_membership(contact_uid, exclude_group=target_group)
