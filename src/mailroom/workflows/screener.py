"""ScreenerWorkflow: poll cycle orchestration with conflict detection, error labeling, re-triage, and per-sender triage processing."""

from __future__ import annotations

import structlog
import vobject

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import BATCH_SIZE, JMAPClient
from mailroom.core.config import MailroomSettings, ResolvedCategory, get_parent_chain


class ScreenerWorkflow:
    """Orchestrates the screener triage pipeline.

    Calls JMAPClient and CardDAVClient methods in sequence.
    Contains business logic only -- no protocol details.

    The poll() method executes one poll cycle:
    1. Collect all triaged emails across all labels, grouped by sender
    2. Filter out emails already marked with @MailroomError
    3. Detect conflicting triage labels (same sender, different labels)
    4. Apply @MailroomError to conflicted senders
    5. Process each clean sender: upsert contact, reconcile email labels
       across all mailboxes, remove triage label (last step)
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
        self._label_failure_counts: dict[str, int] = {}

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

        Uses a single batched JMAP request to query all triage label mailboxes
        at once (SCAN-01, SCAN-02), with per-method error detection (SCAN-03).

        Returns:
            Tuple of (triaged, sender_names):
            - triaged: Dict mapping sender email -> list of (email_id, label_name) tuples.
              Emails already marked with @MailroomError are filtered out.
            - sender_names: Dict mapping sender email -> display name (or None).
              Stores the first non-None display name seen across a sender's emails.
        """
        triage_labels = self._settings.triage_labels

        # Build batched Email/query method calls -- one per triage label
        method_calls = []
        for i, label_name in enumerate(triage_labels):
            label_id = self._mailbox_ids[label_name]
            method_calls.append([
                "Email/query",
                {
                    "accountId": self._jmap.account_id,
                    "filter": {"inMailbox": label_id},
                    "limit": 100,
                },
                f"q{i}",
            ])

        # Single JMAP round-trip for all label queries (SCAN-02)
        responses = self._jmap.call(method_calls)

        # Parse responses with per-method error detection (SCAN-03)
        label_email_ids: dict[str, list[str]] = {}
        for i, label_name in enumerate(triage_labels):
            response = responses[i]

            if response[0] == "error":
                self._handle_label_query_failure(label_name, response[1])
                continue

            # Success: reset failure counter
            self._label_failure_counts.pop(label_name, None)

            data = response[1]
            email_ids = data["ids"]
            total = data.get("total", len(email_ids))

            # Pagination: if total > len(ids), follow up with paginated query
            if total > len(email_ids):
                label_id = self._mailbox_ids[label_name]
                self._log.warning(
                    "label_query_pagination_needed",
                    label=label_name,
                    returned=len(email_ids),
                    total=total,
                )
                email_ids = self._jmap.query_emails(label_id)

            if email_ids:
                label_email_ids[label_name] = email_ids

        # Collect all email IDs across successful labels
        all_email_ids: list[str] = []
        for ids in label_email_ids.values():
            all_email_ids.extend(ids)

        if not all_email_ids:
            return {}, {}

        # Single sender-fetch call for ALL emails across ALL labels
        senders = self._jmap.get_email_senders(all_email_ids)

        # Build the triaged dict (same structure as before)
        raw: dict[str, list[tuple[str, str]]] = {}
        sender_names: dict[str, str | None] = {}
        for label_name, email_ids in label_email_ids.items():
            for email_id in email_ids:
                if email_id not in senders:
                    self._log.warning(
                        "email_missing_sender",
                        email_id=email_id,
                        label=label_name,
                    )
                    continue
                sender_email, sender_name = senders[email_id]
                raw.setdefault(sender_email, []).append((email_id, label_name))
                if sender_email not in sender_names or (
                    sender_names[sender_email] is None and sender_name is not None
                ):
                    sender_names[sender_email] = sender_name

        # Filter out emails that already have @MailroomError (separate call)
        error_id = self._mailbox_ids[self._settings.mailroom.label_error]
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

    def _handle_label_query_failure(self, label_name: str, error_data: dict) -> None:
        """Handle a per-method error for a label query in the batch.

        Increments consecutive failure counter and logs with escalating severity:
        - Count < 3: WARNING
        - Count >= 3: ERROR

        Counter resets when the label succeeds again (in _collect_triaged).
        """
        count = self._label_failure_counts.get(label_name, 0) + 1
        self._label_failure_counts[label_name] = count
        error_type = error_data.get("type", "unknown")
        description = error_data.get("description", "")

        if count >= 3:
            self._log.error(
                "label_query_persistent_failure",
                label=label_name,
                error_type=error_type,
                description=description,
                consecutive_failures=count,
            )
        else:
            self._log.warning(
                "label_query_failed",
                label=label_name,
                error_type=error_type,
                description=description,
                consecutive_failures=count,
            )

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
        error_id = self._mailbox_ids[self._settings.mailroom.label_error]

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
        try:
            warning_id = self._mailbox_ids[self._settings.mailroom.label_warning]
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
        """Process a single sender's triage (initial or re-triage).

        Steps execute in strict order. If any step fails, the exception
        propagates and the triage label is NOT removed (retry on next poll
        per TRIAGE-06).

        1. Extract label and group from emails
        2. Detect re-triage via _detect_retriage
        3. Upsert contact into group (CardDAV)
        4. Contact group management (re-triage: chain diff; initial: ancestor groups)
        5. Email label management: full reconciliation for ALL sender emails
           across all mailboxes (both initial triage and re-triage)
        6. Structured logging
        7. Remove triage label from triggering emails -- LAST STEP
        """
        label_name = emails[0][1]  # All emails have the same label (conflict-free)
        email_ids = [eid for eid, _ in emails]
        category = self._settings.label_to_category_mapping[label_name]
        group_name = category.contact_group
        contact_type = category.contact_type

        log = self._log.bind(sender=sender, label=label_name, group=group_name)

        # Step 1: Detect re-triage
        contact_uid, old_group = self._detect_retriage(sender)
        is_retriage = contact_uid is not None and old_group is not None

        # Step 2: Upsert contact into group (CardDAV)
        display_name = (sender_names or {}).get(sender)
        result = self._carddav.upsert_contact(
            sender, display_name, group_name, contact_type=contact_type
        )
        log.info("contact_upserted", action=result["action"], uid=result["uid"])

        # Step 3: Contact group management
        resolved_map = {c.name: c for c in self._settings.resolved_categories}

        if is_retriage:
            # Find the old category from old_group
            old_category = next(
                c for c in self._settings.resolved_categories
                if c.contact_group == old_group
            )
            uid = contact_uid or result["uid"]
            self._reassign_contact_groups(uid, old_category, category)
        else:
            # Initial triage: add to ancestor groups
            chain = get_parent_chain(category.name, resolved_map)
            if len(chain) > 1 and "uid" in result:
                uid = result["uid"]
                for ancestor in chain[1:]:
                    self._carddav.add_to_group(ancestor.contact_group, uid)
                    log.info("ancestor_group_added", group=ancestor.contact_group)

        # Step 3a: Apply warning label if name mismatch detected
        if result.get("name_mismatch", False) and self._settings.mailroom.warnings_enabled:
            self._apply_warning_label(sender, email_ids)

        # Step 4: Email label management
        # Both initial triage and re-triage use _reconcile_email_labels to sweep
        # ALL emails from the sender across all mailboxes (not just Screener).
        emails_reconciled = self._reconcile_email_labels(
            sender, category, category.add_to_inbox
        )

        # Step 5: Structured logging
        if is_retriage:
            same_group = old_group == group_name
            log.info(
                "group_reassigned",
                old_group=old_group,
                new_group=group_name,
                same_group=same_group,
                emails_reconciled=emails_reconciled,
            )
        else:
            log.info(
                "triage_complete",
                sender=sender,
                emails_moved=emails_reconciled,
            )

        # Step 6: Remove triage label from triggering emails -- LAST STEP
        label_id = self._mailbox_ids[label_name]
        for email_id in email_ids:
            self._jmap.remove_label(email_id, label_id)

    def _get_destination_mailbox_ids(self, label_name: str) -> list[str]:
        """Return mailbox IDs for additive filing (child + all ancestors).

        Walks the parent chain and collects destination mailbox IDs.
        If the triaged category (NOT ancestors) has add_to_inbox=True,
        Inbox is also added.
        """
        category = self._settings.label_to_category_mapping[label_name]
        resolved_map = {c.name: c for c in self._settings.resolved_categories}
        chain = get_parent_chain(category.name, resolved_map)

        ids = [self._mailbox_ids[c.destination_mailbox] for c in chain]

        # add_to_inbox: per-category only (never inherited), Screener-only
        if category.add_to_inbox:
            inbox_id = self._mailbox_ids["Inbox"]
            if inbox_id not in ids:
                ids.append(inbox_id)

        return ids

    def _detect_retriage(
        self,
        sender: str,
    ) -> tuple[str | None, str | None]:
        """Detect if sender is already in a contact group (re-triage scenario).

        - Searches CardDAV for the sender's contact.
        - If no contact found: returns (None, None) -- new sender.
        - If contact found but not in any group: returns (contact_uid, None).
        - If contact found and in a group: returns (contact_uid, group_name).

        Transient CardDAV failures propagate up to _process_sender's try/except
        boundary (retry on next poll per TRIAGE-06).
        """
        results = self._carddav.search_by_email(sender)
        if not results:
            return None, None

        # Extract contact UID from vCard
        card = vobject.readOne(results[0]["vcard_data"])
        contact_uid = card.uid.value

        # Check if this contact is in ANY group (no exclude_group)
        group_name = self._carddav.check_membership(contact_uid)
        return contact_uid, group_name

    def _reassign_contact_groups(
        self,
        contact_uid: str,
        old_category: ResolvedCategory,
        new_category: ResolvedCategory,
    ) -> None:
        """Reassign contact groups using chain diff.

        Computes old and new parent chains, then:
        1. Add to new-only groups FIRST (safe partial-failure order)
        2. Remove from old-only groups
        Shared groups are left untouched.
        """
        resolved_map = {c.name: c for c in self._settings.resolved_categories}
        old_chain = get_parent_chain(old_category.name, resolved_map)
        new_chain = get_parent_chain(new_category.name, resolved_map)
        old_groups = {c.contact_group for c in old_chain}
        new_groups = {c.contact_group for c in new_chain}

        # Add to new-only groups FIRST
        for group in new_groups - old_groups:
            self._carddav.add_to_group(group, contact_uid)

        # Then remove from old-only groups
        for group in old_groups - new_groups:
            self._carddav.remove_from_group(group, contact_uid)

    def _reconcile_email_labels(
        self,
        sender: str,
        category: ResolvedCategory,
        add_to_inbox: bool,
    ) -> int:
        """Reconcile all email labels for a re-triaged sender.

        Strips ALL managed destination labels + Screener label from every email,
        then applies new additive labels (child + parent chain destinations).
        Inbox is NEVER removed. Inbox is added ONLY to emails currently in
        Screener when add_to_inbox is True.

        Returns count of emails reconciled.
        """
        # Compute managed mailbox IDs (all destination_mailbox from every category)
        managed_mailbox_names = {
            c.destination_mailbox for c in self._settings.resolved_categories
        }
        managed_mailbox_ids = {
            self._mailbox_ids[name] for name in managed_mailbox_names
        }
        screener_id = self._mailbox_ids[self._settings.triage.screener_mailbox]
        inbox_id = self._mailbox_ids["Inbox"]

        # Fetch all sender emails across all mailboxes
        all_email_ids = self._jmap.query_emails_by_sender(sender)
        if not all_email_ids:
            return 0

        # Get per-email mailbox membership for Screener presence check
        email_mailboxes = self._jmap.get_email_mailbox_ids(all_email_ids)

        # Compute new destination IDs using parent chain
        resolved_map = {c.name: c for c in self._settings.resolved_categories}
        chain = get_parent_chain(category.name, resolved_map)
        new_dest_ids = [self._mailbox_ids[c.destination_mailbox] for c in chain]

        # Build per-email patches and execute in BATCH_SIZE chunks
        for chunk_start in range(0, len(all_email_ids), BATCH_SIZE):
            chunk = all_email_ids[chunk_start : chunk_start + BATCH_SIZE]

            update: dict = {}
            for email_id in chunk:
                patch: dict = {}

                # Remove all managed labels + Screener (but NEVER Inbox)
                for managed_id in managed_mailbox_ids:
                    if managed_id != inbox_id:
                        patch[f"mailboxIds/{managed_id}"] = None
                patch[f"mailboxIds/{screener_id}"] = None

                # Add new destination labels
                for dest_id in new_dest_ids:
                    patch[f"mailboxIds/{dest_id}"] = True

                # Inbox handling: add ONLY if email is in Screener AND add_to_inbox
                current_mailboxes = email_mailboxes.get(email_id, set())
                if add_to_inbox and screener_id in current_mailboxes:
                    patch[f"mailboxIds/{inbox_id}"] = True

                update[email_id] = patch

            responses = self._jmap.call(
                [
                    [
                        "Email/set",
                        {
                            "accountId": self._jmap.account_id,
                            "update": update,
                        },
                        "r0",
                    ]
                ]
            )
            data = responses[0][1]
            not_updated = data.get("notUpdated")
            if not_updated:
                errors = [
                    f"{eid}: {err.get('description', 'unknown error')}"
                    for eid, err in not_updated.items()
                ]
                raise RuntimeError(
                    f"Failed to reconcile email labels: {', '.join(errors)}"
                )

        return len(all_email_ids)
