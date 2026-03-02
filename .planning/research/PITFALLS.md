# Pitfalls Research

**Domain:** Adding inbox flag separation, additive parent label propagation, label-based scanning (JMAP batched queries), and re-triage (contact group reassignment) to an existing Python email triage system (Fastmail JMAP + CardDAV)
**Researched:** 2026-03-02
**Confidence:** HIGH — codebase directly inspected, RFC 8620/6352 reviewed, v1.1 pitfalls pattern-matched against v1.2 scope, CardDAV group mutation mechanics empirically known from v1.0/v1.1 implementation

---

## Critical Pitfalls

### Pitfall 1: CardDAV Group Reassignment Is Two Unatomic Mutations

**What goes wrong:**
Re-triage moves a sender from one contact group to another. This requires two CardDAV operations: (1) remove the contact UID from the old group's `X-ADDRESSBOOKSERVER-MEMBER` list, and (2) add the contact UID to the new group's `X-ADDRESSBOOKSERVER-MEMBER` list. These are separate PUT requests — there is no CardDAV transaction mechanism. If step 1 succeeds but step 2 fails (network error, 412 ETag conflict, server timeout), the contact ends up in neither group. The next poll finds a contactless sender with no group — the wrong group check passes (no existing group found), so it creates a fresh add-to-new-group, but the remove-from-old-group is already done. The contact lands in the new group. In the good case this happens to be correct. In the bad case (remove fails, add succeeds) the contact is in both groups simultaneously.

**Why it happens:**
CardDAV's Apple-style group model stores membership in the group's vCard, not the contact's vCard. Each group modification is a separate GET+PUT pair with ETag optimistic locking. Two independent group writes cannot be made atomic via the protocol. This is a structural limitation documented by the rcmcarddav project: "For vCard-type groups, only the group's vCard needs to be modified — but each group is a separate resource with its own ETag."

**How to avoid:**
Design the re-triage operation in a safe partial-failure order: **add to new group first, then remove from old group.** A failure after step 1 (add succeeds, remove fails) leaves the contact in both groups. This is detectable and correctable on the next poll via `check_membership()`. A failure before step 1 (nothing done) is safe — retry will re-do the whole thing. Never do remove-first: that leaves a window where the contact is in no group, which is harder to detect.

Log a structured `retriage_partial_failure` event if the remove step fails after a successful add. The next poll's `_check_already_grouped()` will find the contact in the old group (its still there), flag the conflict, and apply `@MailroomError` — which is correct behavior, prompting user inspection. Document this in the re-triage phase: partial failure is expected to surface as `@MailroomError`, not silently succeed.

**Warning signs:**
- Contact appears in two groups simultaneously in Fastmail Contacts
- `@MailroomError` applied to a sender the user intentionally re-triaged
- `check_membership()` returns the old group after a re-triage that appeared to succeed

**Phase to address:** Re-triage phase. The mutation order (add-then-remove) must be specified in the design, not discovered during implementation.

---

### Pitfall 2: `add_to_inbox` Boolean With No Default Breaks Existing config.yaml Files

**What goes wrong:**
Adding a new boolean field `add_to_inbox` (or equivalent) to `TriageCategory` or `ResolvedCategory` without a default value causes pydantic validation to fail for every existing config.yaml that does not include it. The v1.1 Helm ConfigMap renders `config.yaml` without this field. The deployed pod crashes at startup after upgrade because `TriageCategory` requires `add_to_inbox` but it is absent from the mounted ConfigMap.

A subtler version: the field has a default of `None` (not `False`). Existing config.yaml files that omit the field get `None`. Code that then does `if category.add_to_inbox:` works correctly (None is falsy), but code that does `if category.add_to_inbox is False:` does not, producing a silent behavioral difference between users who explicitly set `add_to_inbox: false` and users who omit the field entirely.

**Why it happens:**
pydantic v2 changed `Optional[T]` semantics: an `Optional[bool]` field without a default is now required, not implicitly defaulting to `None`. When adding fields to a sub-model used in YAML config, the distinction between "user omitted this field" (should use default), "user set it to null" (should be treated as default), and "user explicitly set it to false" (should disable inbox) collapses. The safest approach is an explicit `bool` field with a default value, not `Optional[bool]`.

**How to avoid:**
Define `add_to_inbox: bool = False` (not `Optional[bool]`). This means: if absent from config.yaml, the default is `False`. No existing config breaks. The Imbox category's default category definition in `_default_categories()` must be updated to explicitly set `add_to_inbox=True` for the Imbox entry. Test that omitting the field in a YAML fixture produces `False`, not a validation error. Test that an old config.yaml (no `add_to_inbox` key anywhere) loads successfully after adding the field.

For the parent inheritance semantics of `add_to_inbox` (open question in PROJECT.md): decide before implementing whether children inherit `add_to_inbox=True` from parent or use their own default. The safest default: do not inherit. Only the category that explicitly sets `add_to_inbox: true` gets inbox behavior. This avoids surprising implicit behavior in deep inheritance chains.

**Warning signs:**
- Pod CrashLoopBackOff after deploying new version with existing config.yaml
- pydantic `ValidationError: field required` for `add_to_inbox`
- Existing tests that construct `MailroomSettings()` from fixture YAML fail without touching test files

**Phase to address:** Inbox flag separation phase. Define the field with a safe default before writing any resolution logic. Add a regression test that loads a minimal v1.1-era config.yaml fixture and verifies it parses without error.

---

### Pitfall 3: Additive Label Propagation Breaks the Existing Validation Rule "Shared contact_group Without Parent Relationship Is An Error"

**What goes wrong:**
The current `_validate_categories()` rejects configurations where two categories share the same `contact_group` unless one is the parent of the other. This was correct for the old inheritance model (child inherits parent's group, so they share it legitimately). With additive label propagation, children have their own independent `contact_group` by default. But if the new validation allows parent/child to share contact_groups again (for backward compat with Person→Imbox pairing), it re-opens the exact bug the validation was designed to prevent.

Specifically: the default Person category (`parent="Imbox"`) inherits Imbox's contact group under the old model but should have its own group under the additive model. If the validation logic is not updated alongside the resolution logic, these two can drift. The validator says "OK, they share a group because they're parent/child." The resolver gives them different groups. The validator is now checking the wrong thing.

**Why it happens:**
Resolution logic and validation logic are developed separately but must remain consistent. The current validation was written to match the current (override-based) resolution. When resolution semantics change, validation preconditions must change in lockstep.

**How to avoid:**
Update `_validate_categories()` in the same commit as the resolution logic change. After resolution, run a post-resolution consistency check: verify that no two resolved categories have the same contact_group unless it is semantically valid for the new model. Write a unit test that exercises the exact Person/Imbox default configuration under the new additive model and verifies both the resolved categories and the validation outcome.

**Warning signs:**
- Validation passes but resolved categories have unexpected shared groups
- The default config (Person inheriting from Imbox) validates without error but resolves to the wrong group configuration
- Tests for `resolve_categories()` pass but human integration tests show wrong contact group assignment

**Phase to address:** Additive label propagation phase. The validator and resolver must be updated together; a test must confirm they are consistent for all default and custom configurations.

---

### Pitfall 4: JMAP Batch Scan Errors Are Per-Method, Not Per-Request — Swallowing Individual Failures

**What goes wrong:**
The label-based scanning feature replaces N sequential `query_emails()` calls (one per label mailbox) with a single batched JMAP request containing N `Email/query` method calls. RFC 8620 specifies that method-level errors do not propagate — if `Email/query` for label mailbox 3 fails (e.g., that mailbox ID has become invalid), the server returns an error object for that method call only, and the remaining method calls succeed. If the batch response parser treats the entire response as a flat list and only checks the first method's result, it silently drops all emails in the failed mailbox for that poll cycle.

The current `JMAPClient.call()` returns `resp.json()["methodResponses"]` as a raw list. Code that iterates `responses[i][1]` without checking `responses[i][0]` for `"error"` will silently skip failed method calls. With a single-mailbox scan, a failure raises immediately. With a 10-mailbox batched scan, failures become invisible.

**Why it happens:**
The existing codebase processes single-method JMAP calls and checks `responses[0][1]` directly. Scaling to multi-method batch calls requires per-result error checking that the current pattern does not enforce. The natural extension of `responses[0]` to `responses[i]` in a loop accidentally skips the error check.

**How to avoid:**
Add a `check_method_response(response)` helper that accepts one method response triple and raises if the method name is `"error"`. Apply it to every element of a batch response before accessing result data. For the scan batch specifically: if any individual `Email/query` fails, log a warning with the label name and continue processing the successful ones. Do not fail the entire poll cycle because one label mailbox lookup failed — fail gracefully per label.

The JMAP spec also specifies that result references (`#`) fail with `invalidResultReference` if a prior method failed. Do not use result references that chain off potentially-failing methods in the batch. Keep the scan batch as independent parallel queries, not chained.

**Warning signs:**
- Some triage labels never get processed, with no error logged
- Emails in label X accumulate without being triaged across poll cycles
- The poll cycle succeeds (no exception) but `triaged_senders` count is lower than expected

**Phase to address:** Label-based scanning phase. The batch response iterator must include per-method error handling from the first implementation. Add a unit test with a mock response that includes one `"error"` method response among successful ones, and verify the failure is logged and the successful results are still processed.

---

### Pitfall 5: Re-triage Sweep Re-files Emails Already In the Right Destination

**What goes wrong:**
Re-triage must sweep all of the sender's emails to the new destination, just like initial triage. But some of those emails may already be in the new destination mailbox (the user moved them there manually before re-triaging). The current `batch_move_emails()` issues `JMAP Email/set` with `mailboxIds/{screener_id}: null`. For emails not in Screener, this patch has no effect for the remove, but the add patch (`mailboxIds/{dest_id}: true`) still fires. Setting `mailboxIds/{dest_id}: true` on an email already in that mailbox is idempotent per the JMAP patch semantics (it is a JSON merge patch — setting a key to `true` when it is already `true` is a no-op). However, the email may not be in Screener at all — it may be in an entirely different mailbox (e.g., Paper Trail). Removing Paper Trail from its mailboxIds when the re-triage adds it to Feed would be wrong if the sweep query was scoped only to Screener.

The deeper issue: the existing sweep logic only moves emails from Screener (`query_emails(screener_id, sender=sender)`). A re-triage sweep must find sender emails across all label mailboxes (Paper Trail, Feed, Jail, etc.), not just Screener. If re-triage uses the same Screener-only sweep, it leaves all the sender's existing emails in their old locations — only future emails will route to the new group. This makes re-triage feel broken ("I moved them to Feed but all their old emails are still in Paper Trail").

**Why it happens:**
The existing `_process_sender()` workflow is designed for first-time triage from Screener. Re-triage is a different operation with a different email source (all label mailboxes, not just Screener). Reusing `_process_sender()` unchanged for re-triage is wrong.

**How to avoid:**
Re-triage sweep must: (1) query emails from ALL label destination mailboxes for this sender, not just Screener; (2) for each found email, remove the current destination mailbox and add the new destination. The sweep source changes from `screener_id` to "any managed mailbox" — which is all `destination_mailbox` values from the resolved categories. This is a distinct method from `_process_sender()` and should not be an accidental shared code path.

For the `@MailroomWarning` signal: consider applying a warning when re-triage moves emails that were already in a non-Screener location, to surface the re-triage event in the user's view.

**Warning signs:**
- Re-triage moves the contact to the new group but old emails remain in the old mailbox
- No log entries for email moves during a re-triage cycle
- `emails_swept: 0` in the re-triage log when the sender has many existing emails

**Phase to address:** Re-triage phase. The sweep scope must be explicitly specified as "all managed destination mailboxes" in the design, not inherited from the initial-triage sweep logic.

---

## Moderate Pitfalls

### Pitfall 6: `ResolvedCategory` Is a Frozen Dataclass — New Fields Require Constructor Updates Everywhere

**What goes wrong:**
`ResolvedCategory` is a `@dataclass(frozen=True)`. Adding `add_to_inbox: bool` to it requires updating every construction site: the first-pass resolution in `resolve_categories()`, the second-pass parent inheritance block, and any tests that construct `ResolvedCategory` directly. If any construction site is missed, Python raises `TypeError: __init__() missing required keyword argument 'add_to_inbox'` at runtime. Because `ResolvedCategory` objects are only constructed inside `resolve_categories()`, the error only surfaces when the settings are loaded, not when the module is imported. Missed test construction sites silently hide under tests that mock the whole settings object.

**Why it happens:**
Frozen dataclasses require explicit field values at construction — there are no defaults unless declared in the dataclass. The multi-pass resolution in `resolve_categories()` constructs `ResolvedCategory` twice per category (first pass, then optionally a second time in the parent inheritance block). Both construction sites must be updated.

**How to avoid:**
Add a default value to the `ResolvedCategory` field: `add_to_inbox: bool = False`. This prevents construction breakage at existing sites. Only the Imbox category's construction site needs to pass `add_to_inbox=True`. Run the full test suite after adding the field — any missed construction site will raise immediately. Grep for `ResolvedCategory(` to find all construction sites before modifying the dataclass.

**Warning signs:**
- `TypeError: __init__() missing required keyword argument` in any test
- Settings load fails at startup with unexpected `TypeError`
- Coverage shows `resolve_categories()` tested but new field is never exercised

**Phase to address:** Inbox flag separation phase. Update the dataclass before updating any construction site; the default prevents cascading breakage.

---

### Pitfall 7: Label-Based Scan Returns the Same Email Twice (Multi-Label Emails)

**What goes wrong:**
An email can have multiple JMAP labels (mailboxIds). The new label-based scan queries each label mailbox independently and collects email IDs. If an email has both `@ToFeed` and `@ToImbox` applied (a conflict scenario), it will appear in both query results. The existing conflict detection in `_detect_conflicts()` groups emails by sender and detects multiple labels for the same sender. But if the email ID is listed once per label in the raw collection (from separate mailbox queries), the same `email_id` appears twice in the accumulated list — once with label "Feed", once with label "Imbox". The conflict detection works correctly because it checks the set of labels per sender. However, if the deduplication happens before the conflict check, you lose the "both labels present" signal and one label silently wins.

Additionally, if the batch query returns the same email ID twice (from two label mailboxes), and downstream code fetches sender details using `Email/get` with the deduplicated ID list, the lookup is safe. But if the code does not deduplicate IDs before the `Email/get` call, it passes duplicate IDs, which is wasteful and may trigger JMAP server-side validation warnings.

**How to avoid:**
Keep email IDs associated with their source label (the existing `(email_id, label_name)` tuple pattern already does this). Do not deduplicate email IDs before building the `raw` dict. The conflict detection naturally handles the same email appearing under multiple labels because it groups by sender and checks the label set. For the `Email/get` calls that follow, deduplicate the ID list before the API call: `list(set(all_email_ids))`.

**Warning signs:**
- Conflicted senders silently processed under one label instead of receiving `@MailroomError`
- Same email ID appears in the log twice with different labels
- `email_missing_sender` warning for IDs that should have sender data (because the ID was fetched once but referenced twice)

**Phase to address:** Label-based scanning phase. Deduplication strategy must be explicitly tested with a fixture that includes a multi-label email.

---

### Pitfall 8: Parent Chain Traversal for Additive Labels Does Not Terminate on Invalid Config

**What goes wrong:**
Additive label propagation walks the parent chain to collect all ancestor labels. If a bug in `_validate_categories()` fails to catch a circular parent reference (e.g., A→B→A), the traversal enters an infinite loop. The existing circular detection in `_validate_categories()` is correct for the current model, but if it is refactored or extended during the additive-labels change without updating the termination condition, the loop silently hangs the settings load.

A related issue: if the parent chain is valid but very deep (e.g., A→B→C→D→E), each level's labels are accumulated. If the accumulation is done by fetching parent's resolved labels (which themselves recursively walk the chain), without memoization, the traversal is O(n²) in the chain depth. For the single-user tool with 5-10 categories this is irrelevant, but if the traversal is also called during validation (before resolution completes), the unresolved state causes confusing `KeyError` failures.

**How to avoid:**
Walk the parent chain iteratively (not recursively) using the same visited-set pattern already in `_validate_categories()`. The existing circular detection remains the gate — trust it, don't bypass it. For additive label collection during resolution: after validation passes, the chain is guaranteed cycle-free. Walk it with a `while current:` loop and an explicit visited set as a safety backstop. Memoize parent chain results if needed (not critical for 10-category config, but avoids O(n²)).

**Warning signs:**
- Settings load hangs indefinitely on startup
- High CPU usage during startup with no HTTP calls in flight
- `KeyError` on category name during resolution with a message referencing a parent

**Phase to address:** Additive label propagation phase. The existing circular detection test suite must be run against the new resolution path with no modifications to the test.

---

### Pitfall 9: `check_membership()` Fetches Every Group vCard on Every Re-triage Check

**What goes wrong:**
The existing `check_membership()` iterates all validated groups, fetches each group's vCard via HTTP GET, and scans for the contact UID. With 5 groups this is 5 GET requests per sender per poll cycle. For initial triage this is acceptable — it runs once per new sender. For re-triage this is also fine at low frequency. But if re-triage is triggered via a label scan (not just from Screener), every sender with a triage label in any mailbox will trigger a `check_membership()` call. The membership check's cost scales linearly with group count.

The deeper issue: after a successful re-triage, the contact is in the new group. On the next poll cycle (before the triage label is removed — which is the last step), the same sender is found again. `check_membership()` now returns the *new* group (where the contact was just placed), not the old group. This is not a conflict — it is correct. But if the re-triage logic doesn't correctly distinguish "already in the target group" from "already in a different group," it will re-process a successfully re-triaged sender on every poll until the label is removed.

**How to avoid:**
The existing `_check_already_grouped()` logic already handles "already in target group" (returns `None`, proceeds to add contact — which is idempotent). The re-triage path should follow the same pattern: if `check_membership()` returns the target group, it means the add step already completed (from a previous partial execution); skip the add, proceed to the email sweep, then remove the label. This is the existing retry-safety design — trust it.

For the fetch cost: cache group membership per poll cycle, not across polls. A single `list_groups()` call at the start of the cycle to refresh the in-memory group state is more efficient than N individual GET requests during processing.

**Warning signs:**
- Each poll cycle makes N×G CardDAV GET requests (N senders × G groups) instead of one amortized fetch
- Re-triaged senders are processed on every poll until the label is finally removed
- CardDAV 429 rate-limiting responses during a poll with many pending senders

**Phase to address:** Re-triage phase. Document the "already in target group" path explicitly and add a unit test that exercises it.

---

### Pitfall 10: The `add_to_inbox` Flag for Non-Imbox Destinations Is Ambiguous

**What goes wrong:**
The v1.1 codebase has a single implicit rule: if `destination_mailbox == "Inbox"`, also add the Inbox label (for immediate visibility). This is currently derived from `destination_mailbox` identity, not from a flag. When `add_to_inbox` becomes an explicit boolean, a category could set `destination_mailbox: "Feed"` AND `add_to_inbox: true` — meaning "file in Feed but also appear in Inbox simultaneously." This is technically valid in JMAP (emails can be in multiple mailboxes), but it produces a confusing user experience: an email appears in both Feed and Inbox. If the user reads it in Inbox and it disappears from there (via some other rule), it still shows in Feed. If they archive from Feed, it removes the Feed label and it reappears in Inbox.

Additionally, the current `_get_destination_mailbox_ids()` method checks for Inbox implicitly by checking if `destination_mailbox == "Inbox"`. If `add_to_inbox` becomes a flag, this check must be refactored — but the old implicit check may still exist in other code paths, creating two conflicting mechanisms for the same behavior.

**How to avoid:**
Define `add_to_inbox` as strictly replacing the implicit "destination is Inbox" check. The rule becomes: if `add_to_inbox=True`, include the Inbox mailbox ID in the `add_ids` list during sweep (regardless of `destination_mailbox`). Remove the `destination_mailbox == "Inbox"` check entirely. The default Imbox category gets `destination_mailbox="Inbox"` AND `add_to_inbox=True` for clarity (both fields set). Validate in startup: if `add_to_inbox=True` and `destination_mailbox="Inbox"`, that is fine (redundant but clear). If `add_to_inbox=True` and `destination_mailbox != "Inbox"`, emit a warning log: "Category X files to Feed but also adds Inbox — this is unusual."

**Warning signs:**
- Emails appear in both Inbox and Feed simultaneously after re-triage
- The implicit `destination_mailbox == "Inbox"` check and the `add_to_inbox` flag both exist in the codebase
- Tests pass for Imbox triage but emails are not added to Inbox (the check was refactored away without update)

**Phase to address:** Inbox flag separation phase. The refactor from implicit check to explicit flag must be a single atomic commit with tests updated to cover both the old behavior (via default Imbox category) and the new explicit flag path.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reuse `_process_sender()` for re-triage with a flag parameter | Avoids new method | Business logic for initial triage and re-triage diverges, flag hell accumulates | Never — re-triage is a separate operation; create a separate method |
| Skip additive label traversal, just use the existing single-pass resolution | Faster to implement | Old inheritance behavior silently continues, v1.2 goal not achieved | Never |
| Hard-code "scan these 5 label mailboxes" for batch scan | No JMAP ID lookup needed | Config changes require code changes | Acceptable only as temporary measure if label-to-ID mapping is available at scan time |
| Omit per-method error check in batch scan loop | Cleaner code | Silent data loss when one mailbox query fails | Never — the check is a 3-line addition |
| Use `Optional[bool] = None` for `add_to_inbox` | Avoids false/None ambiguity | Pydantic behavior differs between "field omitted" and "field = null", complicates logic | Never — use `bool = False` with explicit default |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| CardDAV group re-membership | Fetch group, mutate, PUT — but forget to re-GET before the remove step | Always GET-then-PUT for both add and remove; each is a separate optimistic-lock cycle |
| JMAP batched scan | Check `responses[0][1]` pattern copied N times in a loop | Write a per-method response validator; apply it before accessing `[1]` on any response element |
| CardDAV group membership check during re-triage | `check_membership()` finds old group and treats it as a conflict even post-successful-add | Check if the found group is the one we just tried to remove; if so, the add succeeded and remove failed — log and continue |
| JMAP `Email/set` remove-mailbox patch | Setting `mailboxIds/{id}: null` on an email not in that mailbox | JMAP patch semantics are safe here (JSON merge patch ignores null on absent key), but verify against live Fastmail |
| `TriageSettings.screener_mailbox` in re-triage | Scanning only Screener for sender emails during a re-triage sweep | Re-triage sweep must query all destination mailboxes; `screener_mailbox` scan is only for initial triage |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Sequential label mailbox queries (one JMAP call per label) | Polling latency scales with category count; N=10 labels = 10+ API round-trips | Batch all `Email/query` calls into a single JMAP request | Noticeable at 5+ categories; painful at 20+ |
| `check_membership()` fetches all group vCards per sender | N senders × G groups = N×G CardDAV GETs per cycle | Fetch/cache group state once per poll cycle; re-use in-memory state for all senders in that cycle | Painful at 5+ pending senders simultaneously (rare but possible after a push reconnect) |
| Additive label chain traversal without memoization | Settings load time increases quadratically with parent chain depth | Walk iteratively, not recursively; memoize if needed | Irrelevant at 5-10 categories; present at 50+ (hypothetical) |
| Re-triage sweep queries all destination mailboxes per sender | K categories × sender query = K API calls per re-triaged sender | Batch the sweep queries; or perform a single filtered query on all sender emails | Painful at 10+ categories being re-swept simultaneously |

---

## "Looks Done But Isn't" Checklist

- [ ] **`add_to_inbox` backward compat:** Does an old v1.1 config.yaml (no `add_to_inbox` key) load successfully without validation error? Verify before writing any config logic.
- [ ] **Additive labels for default categories:** Does the Person category (child of Imbox) correctly get Imbox's triage label *in addition to* `@ToPerson`? Verify the resolved label list, not just contact_group.
- [ ] **Validation/resolver consistency:** Does `_validate_categories()` accept a config that `resolve_categories()` would assign conflicting groups to? If yes, the two are out of sync.
- [ ] **Batch scan per-method error handling:** Is there a unit test that provides a mock batch response with one `"error"` method result and verifies the error is logged and other results are processed?
- [ ] **Re-triage sweep scope:** Does the re-triage code query all destination mailboxes (not just Screener) for sender emails? Check the query source explicitly.
- [ ] **CardDAV re-group order:** Is the re-triage code doing add-then-remove (safe order) or remove-then-add (risky order)? Check the code, not the docs.
- [ ] **Re-triage label removal last:** Does the re-triage flow preserve the "remove triage label last" invariant from initial triage? A failed re-triage must leave the triage label for retry.
- [ ] **Human test for re-triage:** Is there a `human-tests/test_N_retriage.py` that applies a triage label to an already-grouped sender and verifies group reassignment and email re-filing?
- [ ] **`@MailroomWarning` on re-triage:** Does a successful re-triage produce a `@MailroomWarning` on the triggering email so the user can confirm the action in their inbox?

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Contact in both groups after partial re-triage | LOW | Re-apply triage label manually; next poll detects "already in wrong group" (old group) and applies `@MailroomError`; user resolves manually by removing contact from old group via Fastmail Contacts |
| Contact in no group after remove-then-add failure | MEDIUM | Contact exists but is ungrouped; apply triage label again; next poll will add to target group (no membership conflict detected) |
| config.yaml breaks after field addition | LOW | Add the field with a default to the model; redeploy; existing config files instantly work |
| Batch scan silently drops a label mailbox | MEDIUM | Check logs for per-method error warnings; re-scan is automatic next poll; missed emails will be processed next cycle |
| Re-triage sweeps wrong mailboxes | HIGH | Emails left in old destination; user must manually move them or re-triage again after fix is deployed |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| CardDAV group reassignment non-atomicity (Pitfall 1) | Re-triage phase | Human test simulates add-succeeds-remove-fails and verifies `@MailroomError` signal; unit test verifies add-before-remove order |
| `add_to_inbox` field without default breaks config (Pitfall 2) | Inbox flag separation phase | Load v1.1-era fixture YAML; assert no ValidationError; assert `add_to_inbox=False` |
| Validation/resolver inconsistency on additive model (Pitfall 3) | Additive label propagation phase | Unit test: configure default categories, resolve, assert validation passes AND resolved groups are correct; run both old test suite and new additive-model tests |
| Batch scan swallows per-method errors (Pitfall 4) | Label-based scanning phase | Unit test with mock response containing `"error"` method result; assert warning logged and other results processed |
| Re-triage sweep uses wrong source mailbox (Pitfall 5) | Re-triage phase | Human test: re-triage sender who has emails in Paper Trail; verify those emails move to new destination |
| `ResolvedCategory` construction sites missed (Pitfall 6) | Inbox flag separation phase | `grep -r 'ResolvedCategory(' src/` before modifying; run full test suite after field addition |
| Multi-label email appears twice in scan (Pitfall 7) | Label-based scanning phase | Unit test: fixture with email having two label mailboxes; assert conflict detection fires, not silent single-label processing |
| Parent chain traversal hangs on circular config (Pitfall 8) | Additive label propagation phase | Existing circular detection test suite must pass unchanged; add test for chain traversal with visited-set safety |
| `check_membership()` fetches on every sender (Pitfall 9) | Re-triage phase | Verify group state is cached per poll cycle, not per sender |
| `add_to_inbox` flag and implicit check coexist (Pitfall 10) | Inbox flag separation phase | Grep for `destination_mailbox == "Inbox"` pattern after refactor; it must not appear |

---

## Sources

- Mailroom codebase: `src/mailroom/core/config.py`, `src/mailroom/clients/carddav.py`, `src/mailroom/clients/jmap.py`, `src/mailroom/workflows/screener.py` — directly inspected (HIGH confidence)
- [RFC 8620 — JMAP Core: Section 3.4 Method-level error isolation](https://www.rfc-editor.org/rfc/rfc8620.html) — method errors do not cascade; each method in a batch is independent (HIGH confidence)
- [RFC 8620 — JMAP Core: Result References and error propagation](https://jmap.io/spec-core.html) — `invalidResultReference` on failed result reference; use independent queries, not chained references, for fault isolation (HIGH confidence)
- [RFC 6352 — CardDAV spec](https://www.rfc-editor.org/rfc/rfc6352) — no transaction semantics for multi-resource operations (HIGH confidence)
- [rcmcarddav CardDAV group documentation](https://github.com/mstilkerich/rcmcarddav/blob/master/doc/GROUPS.md) — VCard-type groups require separate vCard PUT per group modified; no atomicity across two group vCards (MEDIUM confidence)
- [pydantic-settings documentation — Optional field semantics](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — `Optional[T]` without default is required in Pydantic v2; use `T = default` for backward-compatible new fields (HIGH confidence)
- v1.1 PITFALLS.md — Pitfall 2 (config migration), Pitfall 9 (derived properties) pattern-matched against v1.2 scope (HIGH confidence, derived from past project experience)
- v1.1 MILESTONE-AUDIT.md — tech debt items #2–4 carried into v1.2 scope (HIGH confidence)

---
*Pitfalls research for: v1.2 Triage Pipeline v2 — inbox flag, additive labels, label-based scan, re-triage*
*Researched: 2026-03-02*
