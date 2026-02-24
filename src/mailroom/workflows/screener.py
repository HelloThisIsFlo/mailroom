"""ScreenerWorkflow: poll cycle orchestration with conflict detection and error labeling."""

from __future__ import annotations

import structlog

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
    5. Process each clean sender (stub in this plan, filled by Plan 02)
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
        triaged = self._collect_triaged()

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
                self._process_sender(sender, emails)
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

    def _collect_triaged(self) -> dict[str, list[tuple[str, str]]]:
        """Collect all triaged emails across all labels, grouped by sender.

        Returns:
            Dict mapping sender email -> list of (email_id, label_name) tuples.
            Emails already marked with @MailroomError are filtered out.
        """
        # Collect emails from all triage labels
        raw: dict[str, list[tuple[str, str]]] = {}
        all_email_ids: list[str] = []
        email_id_to_label: dict[str, str] = {}

        for label_name in self._settings.triage_labels:
            label_id = self._mailbox_ids[label_name]
            email_ids = self._jmap.query_emails(label_id)
            if not email_ids:
                continue

            # Get sender addresses for these emails
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

                sender = senders[email_id]
                raw.setdefault(sender, []).append((email_id, label_name))
                all_email_ids.append(email_id)
                email_id_to_label[email_id] = label_name

        if not all_email_ids:
            return {}

        # Filter out emails that already have @MailroomError
        error_id = self._mailbox_ids[self._settings.label_mailroom_error]
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
            return raw

        # Rebuild the dict without errored emails
        filtered: dict[str, list[tuple[str, str]]] = {}
        for sender, emails in raw.items():
            clean_emails = [
                (eid, label) for eid, label in emails if eid not in errored_ids
            ]
            if clean_emails:
                filtered[sender] = clean_emails

        return filtered

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
        error_id = self._mailbox_ids[self._settings.label_mailroom_error]

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

    def _process_sender(
        self,
        sender: str,
        emails: list[tuple[str, str]],
    ) -> None:
        """Process a single sender's triage.

        Stub in this plan -- Plan 02 implements per-sender processing.
        """
        raise NotImplementedError("Plan 02 implements per-sender processing")
