# Feature Research

**Domain:** Email triage / screener automation (HEY Mail Screener replication on Fastmail)
**Researched:** 2026-02-23
**Confidence:** MEDIUM (based on training data knowledge of HEY Mail, SaneBox, Fastmail; no live source verification available)

## Competitor Feature Analysis

Understanding what exists in the market establishes what "table stakes" means for this domain.

### HEY Mail Screener (Primary Inspiration)

| Feature | How It Works | Relevance to Mailroom |
|---------|-------------|----------------------|
| First-time sender gating | New senders are held in Screener until you decide | Direct — this is the core concept |
| One-tap triage (Yes/No) | Thumbs up = Imbox, Thumbs down = Screener Out | Mailroom has 4 destinations instead of 2, richer |
| Imbox / Feed / Paper Trail routing | Three distinct destinations with different UX (Feed = newsletters, Paper Trail = receipts/transactional) | Direct — same model, same names |
| Backlog sweep on triage | Triaging one email from a sender moves ALL their emails | Direct — core requirement |
| Future email auto-routing | Once triaged, future emails go to the assigned destination | Handled by Fastmail rules + contact groups |
| Screening Out (block-lite) | "Screen Out" hides future emails without hard blocking | Equivalent to Jail in Mailroom |
| Previously Seen badge | Shows if you've seen emails from this sender before | Not in scope — nice UX but not essential |
| Bulk screening | Triage multiple senders at once from the Screener view | Not in v1 — one-at-a-time via labels is fine |
| Reply-to auto-approve | Replying to a screened email auto-approves the sender | Not applicable — Mailroom is label-driven, not reply-driven |

### SaneBox

| Feature | How It Works | Relevance to Mailroom |
|---------|-------------|----------------------|
| AI-powered sorting | ML classifies emails into SaneLater, SaneNews, etc. | NOT relevant — Mailroom is manual-triage, not AI |
| SaneBlackHole | Drag email to folder to never hear from sender again | Similar concept to Jail, but permanent |
| SaneNoReplies | Follow up on emails that didn't get replies | Out of scope |
| Snooze | Snooze emails to reappear later | Out of scope |
| Do Not Disturb | Batch delivery at scheduled times | Out of scope |
| One-click unsubscribe | Unsubscribe from mailing lists | Out of scope for v1 |
| Digest emails | Summary of filtered emails | Could be useful for Jail review, but out of scope |
| Training via drag-and-drop | Move email to folder = train the filter | Analogous to label-based triage in Mailroom |

### Other Tools (Clean Email, Unroll.me, Leave Me Alone)

These focus on bulk unsubscribe and newsletter management, not sender gating. They confirm that the "screen unknown senders" niche is primarily HEY's domain — most tools assume emails are already in the inbox and help you clean up after the fact.

## Feature Landscape

### Table Stakes (Users Expect These)

Features the project must have to deliver on its core promise. Without these, the tool is broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Poll for triage labels | Core trigger mechanism — nothing works without detecting `@ToImbox`, `@ToFeed`, `@ToPaperTrail`, `@ToJail` labels | LOW | JMAP query by label/mailbox. Poll every 5 min. |
| Extract sender from triaged email | Must know WHO to triage — extract the `From` address | LOW | JMAP `Email/get` with `from` property |
| Create/update contact via CardDAV | Must add sender to contacts to make Fastmail rules work | MEDIUM | CardDAV vCard creation. Handle existing contacts without duplicates. |
| Assign contact to correct group | The entire routing mechanism depends on contact group membership | MEDIUM | CardDAV group membership update. Different contact servers handle groups differently (vCard `X-ADDRESSBOOKSERVER-MEMBER` for Apple-style, `CATEGORIES` for others). Fastmail uses its own group model. |
| Remove triage label after processing | Prevent re-processing the same email on next poll cycle | LOW | JMAP `Email/set` to remove keyword/label |
| Sweep Screener for same sender | Core HEY behavior — triage one email, all emails from that sender move | MEDIUM | JMAP query Screener by sender address, then batch-update labels. Must handle pagination if sender has many emails. |
| Re-add Inbox label on Imbox sweep | Swept-to-Imbox emails must appear in the Inbox, not stay archived | LOW | JMAP `Email/set` to add Inbox mailbox |
| Retry on failure | Leave triage label in place if processing fails, retry next cycle | LOW | Simple error handling — catch exceptions, log, continue. The triage label IS the retry mechanism. |
| Idempotent processing | Re-processing the same email must not create duplicate contacts or corrupt state | MEDIUM | Check for existing contact before creating. Use sender email as dedup key. |
| Structured logging | Running headless on k8s — must be able to diagnose issues from logs | LOW | JSON logs with action, sender, timestamp, success/failure |

### Differentiators (Competitive Advantage)

Features that go beyond basic functionality and provide meaningful value. Not required for v1 launch, but should be considered.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Handle existing contacts (no duplicates) | Prevents contact list pollution — many triage tools create duplicates, degrading the address book | MEDIUM | Search CardDAV by email before creating. If found, just add to group. Critical for a clean address book. Promote to table stakes. |
| Configurable label and group names | Decouples the tool from hardcoded names — user can customize their Fastmail setup | LOW | ConfigMap-driven. Already in requirements. Makes the tool adaptable. |
| Graceful handling of multi-sender emails | Some emails have multiple From addresses or use different reply-to vs from | LOW | Use the primary `From` header. Log warnings for edge cases. Don't over-engineer. |
| Health endpoint or liveness signal | k8s can restart the pod if it hangs | LOW | Simple liveness probe — write timestamp to file or expose HTTP health check |
| Dry-run mode | Test the tool without making changes — see what WOULD happen | LOW | Log intended actions without executing CardDAV/JMAP writes. Invaluable for initial setup and debugging. |
| Metrics / counters | Track how many senders triaged, emails swept, errors encountered | LOW | Log-based metrics or simple counters in structured logs. Enough for a single-user tool. |
| Sender display name preservation | When creating contacts, preserve the sender's display name (not just email) | LOW | Extract display name from `From` header. Makes the contact list more useful. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem appealing but should NOT be built, especially not in v1.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| AI/ML auto-classification | "Automatically sort emails like SaneBox" | Massive complexity, needs training data, gets things wrong. The entire point of the Screener model is HUMAN triage — the user decides, not an algorithm. Building AI defeats the product philosophy. | Keep manual triage via labels. The one-tap UX is fast enough. |
| Webhook/push-based triggers | "React instantly instead of polling" | Fastmail does not support webhooks. Period. Building a workaround (IMAP IDLE, etc.) adds complexity for marginal gain — 5-minute polling is fast enough for triage. | Poll every 5 minutes. Triaging is not time-sensitive. |
| Plugin/workflow engine | "Make it extensible for other workflows" | Over-engineering v1. The plugin architecture is a v2+ concern. Building it now delays shipping and adds abstraction before you understand real usage patterns. | Clean module separation (already planned). Refactor to plugins later if needed. |
| Web UI / dashboard | "See triage history, manage contacts from a browser" | Single-user tool running on a home k8s cluster. The UI is Fastmail itself. Building a dashboard is a separate product. | Use Fastmail's UI + structured logs for visibility. |
| Auto-unsubscribe for Jailed senders | "If I jail them, unsubscribe me too" | `List-Unsubscribe` is unreliable (some senders don't support it, some require HTTP POST, some require mailto). Sending unsubscribe requests is an active action with side effects. Jail is soft-reject, not permanent. | Jail hides emails. User can manually unsubscribe for persistent offenders. |
| Multi-account support | "Support multiple Fastmail accounts" | Single-user tool. Multi-account adds config complexity, state management, auth management. | Deploy separate instances if needed. |
| noreply address cleanup | "Don't pollute contacts with noreply@..." | Detecting noreply addresses is heuristic (regex). False positives would skip legitimate senders. The project brief explicitly defers this. | All screened contacts are in groups, making future batch cleanup easy. Address later with a separate script. |
| Real-time notification on triage | "Notify me when a sender is triaged" | Over-engineering. The user initiated the triage — they know it happened. Notification adds nothing. | Structured logs capture all actions if review is needed. |
| Undo / re-triage | "Move a sender from Jail to Imbox" | This is just applying a different triage label to an email from that sender. The tool already handles it — on next poll, it updates the contact group. No special "undo" feature needed. | Apply the new triage label. Mailroom processes it naturally. But note: moving between groups requires removing from old group — this IS a table stakes concern (see dependencies). |

## Feature Dependencies

```
[Poll for triage labels]
    |
    v
[Extract sender from triaged email]
    |
    +---> [Create/update contact via CardDAV]
    |         |
    |         v
    |     [Assign contact to correct group]
    |
    +---> [Remove triage label after processing]
    |
    +---> [Sweep Screener for same sender]
              |
              v
          [Re-add Inbox label on Imbox sweep]

[Retry on failure] --enhances--> [All of the above]

[Idempotent processing] --required-by--> [Create/update contact via CardDAV]

[Structured logging] --enhances--> [All of the above]

[Configurable names] --required-by--> [Poll for triage labels] (needs to know label names)
                     --required-by--> [Assign contact to correct group] (needs group names)

[Dry-run mode] --enhances--> [Create/update contact via CardDAV]
               --enhances--> [Sweep Screener for same sender]
```

### Dependency Notes

- **Contact creation requires dedup check (idempotency):** You cannot safely create contacts without first checking if the sender already exists. This MUST be part of the contact creation flow, not a separate feature.
- **Sweep requires sender extraction:** You need the sender email to query the Screener for all their emails.
- **Inbox re-labeling requires sweep:** Only applies during the sweep phase for Imbox-destined emails.
- **Configuration must be loaded before polling:** Label names and group names drive the entire pipeline.
- **Re-triage (moving between groups) depends on group removal:** If a sender was previously triaged to Feed and is now re-triaged to Imbox, the tool must remove them from the Feed group AND add them to the Imbox group. This is a critical edge case in the contact update flow.

## MVP Definition

### Launch With (v1)

Minimum viable product -- what's needed to validate the concept works.

- [ ] **JMAP polling loop** -- detect triage labels every 5 minutes
- [ ] **Sender extraction** -- get email address from triaged message
- [ ] **CardDAV contact create/update** -- add sender to contacts, assign to group, handle duplicates
- [ ] **Triage label removal** -- clean up after processing
- [ ] **Screener sweep** -- move all emails from triaged sender to correct destination
- [ ] **Inbox re-labeling for Imbox** -- swept Imbox emails appear in Inbox
- [ ] **Retry via label persistence** -- failed processing retries on next cycle
- [ ] **Structured JSON logging** -- visibility into what the service is doing
- [ ] **ConfigMap-driven configuration** -- label names, group names, polling interval
- [ ] **Docker + k8s manifests** -- deployable to home cluster

### Add After Validation (v1.x)

Features to add once core triage loop is working reliably.

- [ ] **Dry-run mode** -- trigger: before first real deployment, for testing
- [ ] **Health/liveness probe** -- trigger: after first production deployment, for reliability
- [ ] **Re-triage support (group transfer)** -- trigger: when user wants to move senders between groups
- [ ] **Sender display name preservation** -- trigger: when contact list review reveals names are missing
- [ ] **Metrics/counters in logs** -- trigger: when operational visibility needs improvement

### Future Consideration (v2+)

Features to defer until the tool has proven itself.

- [ ] **List-Unsubscribe auto-classification** -- auto-route newsletters to Feed without manual triage
- [ ] **Pluggable workflow engine** -- generalize the trigger-action pattern for other Fastmail automations
- [ ] **noreply address detection/cleanup** -- skip or flag noreply senders during triage
- [ ] **Batch triage review** -- periodic Jail review reminder or digest

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| JMAP polling loop | HIGH | LOW | P1 |
| Sender extraction | HIGH | LOW | P1 |
| CardDAV contact create/update | HIGH | MEDIUM | P1 |
| Contact group assignment | HIGH | MEDIUM | P1 |
| Triage label removal | HIGH | LOW | P1 |
| Screener sweep | HIGH | MEDIUM | P1 |
| Inbox re-labeling (Imbox) | HIGH | LOW | P1 |
| Retry on failure | HIGH | LOW | P1 |
| Idempotent contact handling | HIGH | MEDIUM | P1 |
| Structured JSON logging | MEDIUM | LOW | P1 |
| ConfigMap configuration | MEDIUM | LOW | P1 |
| Docker + k8s manifests | HIGH | LOW | P1 |
| Dry-run mode | MEDIUM | LOW | P2 |
| Health/liveness probe | MEDIUM | LOW | P2 |
| Re-triage (group transfer) | MEDIUM | MEDIUM | P2 |
| Display name preservation | LOW | LOW | P2 |
| Log-based metrics | LOW | LOW | P3 |
| List-Unsubscribe classification | MEDIUM | HIGH | P3 |
| Pluggable workflow engine | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Comparison

| Feature | HEY Mail | SaneBox | Clean Email | Mailroom (Ours) |
|---------|----------|---------|-------------|-----------------|
| Unknown sender gating | Yes (Screener) | No (sorts after delivery) | No | Yes (via Fastmail rules + triage labels) |
| Manual triage | Yes (Thumbs up/down) | No (AI-driven) | No (bulk actions) | Yes (label-based, 4 destinations) |
| Backlog sweep on triage | Yes | N/A | No | Yes |
| Imbox / Feed / Paper Trail | Yes (built-in) | Similar (SaneLater, SaneNews) | No | Yes (via contact groups + Fastmail rules) |
| Soft-reject (not block) | Yes (Screen Out) | Yes (SaneBlackHole) | Yes (Block) | Yes (Jail group) |
| AI classification | No | Yes (core feature) | Yes | No (deliberate) |
| Works with existing email | No (HEY-only) | Yes (any IMAP) | Yes (any IMAP) | Fastmail-specific (JMAP + CardDAV) |
| Self-hosted | No | No | No | Yes (k8s) |
| Open source | No | No | No | Yes (planned) |
| Cost | $99/yr | $7-36/mo | $10-30/mo | Free (self-hosted) |

## Key Insight: What Makes This Project Different

Mailroom is NOT competing with SaneBox or Clean Email. Those are AI-driven tools that sort email automatically. Mailroom replicates HEY's philosophy: **the human decides, the tool executes**. The differentiator is:

1. **No AI, no magic** -- the user explicitly triages every unknown sender
2. **Works on Fastmail** -- HEY's Screener only works on HEY
3. **Self-hosted** -- no SaaS dependency, no privacy concerns
4. **Leverages existing Fastmail infrastructure** -- rules, labels, contact groups are already set up

The "feature" is the workflow automation itself, not a rich feature set. Keep it simple.

## Sources

- HEY Mail feature documentation and product philosophy (training data, MEDIUM confidence)
- SaneBox feature pages (training data, MEDIUM confidence)
- Fastmail JMAP and CardDAV documentation (training data, MEDIUM confidence -- verify against live docs during implementation)
- PROJECT_BRIEF.md and PROJECT.md for project-specific requirements (HIGH confidence)
- Note: WebSearch and WebFetch were unavailable during research. All competitor analysis is from training data. Feature claims about HEY and SaneBox should be verified if any seem surprising.

---
*Feature research for: Email triage / screener automation*
*Researched: 2026-02-23*
