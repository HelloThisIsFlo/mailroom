# Mailroom — Project Brief

## Context

Migrating from HEY Mail to Fastmail. The goal is to replicate HEY's Screener workflow — where unknown senders are triaged before reaching the inbox — using Fastmail's rules, labels, and contact groups. The main UX friction is that assigning a contact to a contact group on iOS is tedious (multiple taps into the Contacts UI). This project automates that step.

## Fastmail Screener Workflow (Already Set Up)

The base workflow uses **labels** (not folders):

1. **Rule:** "Sender is not a contact" → add label `Screener`, archive (remove Inbox label)
2. **Rule:** "Sender is a member of group Feed" → add label `Feed`, archive
3. **Rule:** "Sender is a member of group Paper Trail" → add label `Paper Trail`, archive
4. **Rule:** "Sender is a member of group Jail" → add label `Jail`, archive
5. **Rule:** Contacts not in any of the above groups → emails land in Imbox (Inbox)

Sidebar config:
- Screener → hide when empty
- Imbox, Feed, Paper Trail → always show

Additional config:
- VIP-only notifications (only VIP contacts trigger push notifications)
- _Future idea (not part of this project):_ Consider using `List-Unsubscribe` header to auto-classify newsletters into Feed without needing per-sender contact group assignment

## What This Project Builds

A background Python service that bridges the gap between "slap a label on an email" (quick, one tap on mobile) and "add sender to the right contact group" (tedious on mobile).

### User Flow

1. Email arrives from unknown sender → lands in `Screener` label (via existing Fastmail rule)
2. User reviews email on phone, applies a **triage label** to any one email from that sender:
   - `@ToImbox` — I want this sender in my Imbox going forward
   - `@ToFeed` — route this sender to Feed
   - `@ToPaperTrail` — route this sender to Paper Trail
   - `@ToJail` — soft-reject this sender (not a hard block — Jail is reviewed periodically, e.g. every 3 weeks)
3. Background script picks up emails with triage labels
4. Script extracts the sender's email address
5. Script adds the sender to contacts and to the appropriate contact group:
   - `@ToImbox` → add sender to `Imbox` contact group
   - `@ToFeed` → add sender to `Feed` contact group
   - `@ToPaperTrail` → add sender to `Paper Trail` contact group
   - `@ToJail` → add sender to `Jail` contact group
6. Script removes the triage label from the original email
7. **Script sweeps `Screener` for ALL emails from that same sender** and moves them to the correct destination:
   - Removes `Screener` label from all of them
   - Adds the destination label (`Feed`, `Paper Trail`, `Jail`, or nothing for Imbox)
8. Future emails from that sender are automatically routed by the existing Fastmail rules (because the sender is now in the correct contact group)

This mirrors HEY's behaviour: one triage decision on one email clears the entire backlog from that sender.

**Important: Jail ≠ Block.** Jail is just another contact group with its own label, like Feed or Paper Trail. We never use Fastmail's "block sender" feature. Jailed senders can be reviewed periodically and moved to another group if needed.

### Technical Architecture

> **Note:** The tech stack below is a starting suggestion. Discuss with the user during implementation to determine the best libraries and approach.

**Polling-based** (Fastmail does not support webhooks).

- **JMAP API** for email operations:
  - Query emails by label/mailbox
  - Read sender addresses
  - Modify labels (remove triage label after processing)
  - Auth: API token from Settings → Privacy & Security → Manage API tokens
  - Endpoint: `https://api.fastmail.com/jmap/session`
  - Auth header: `Authorization: Bearer {token}`
  - Julia Evans wrote a good quickstart: https://jvns.ca/blog/2020/08/18/implementing--focus-and-reply--for-fastmail/
  - Fastmail's own samples: https://github.com/fastmail/JMAP-Samples

- **CardDAV** for contact operations:
  - Add/update contacts
  - Assign contacts to contact groups
  - Server: `carddav.fastmail.com`
  - Auth: app password (generate at Settings → Privacy & Security)
  - Fastmail stores contacts in vCard 3.0 format
  - JMAP for contacts is not yet available (spec not finalized)

- **Polling frequency:** Every 5 minutes is sufficient

### Labels in Fastmail (Already Created)

| Label | Purpose |
|-------|---------|
| `Screener` | Unknown senders land here (set by Fastmail rule) |
| `@ToImbox` | Triage label: user wants sender in Imbox |
| `@ToFeed` | Triage label: user wants sender in Feed |
| `@ToPaperTrail` | Triage label: user wants sender in Paper Trail |
| `@ToJail` | Triage label: user wants sender in Jail (soft-reject, reviewed periodically) |

### Contact Groups in Fastmail

All four destinations have a corresponding contact group. This makes it easy to batch-review or batch-clean contacts later — every screened sender belongs to exactly one of these groups.

- `Imbox` — senders whose emails go to the Imbox (default inbox)
- `Feed` — senders whose emails go to the Feed label
- `Paper Trail` — senders whose emails go to the Paper Trail label
- `Jail` — senders whose emails go to the Jail label (reviewed periodically)

## Deployment

### Container Image

- **Dockerfile:** Slim Python base image, pip install deps, copy script, run
- **Registry:** GitHub Container Registry (ghcr.io) — free, works with GitHub repos

### Kubernetes

Deploying to an existing home Kubernetes cluster. Cluster is already set up and accessible via kubectl.

Manifests needed:
- **Deployment** (1 replica) — the Python script running in a loop with sleep
- **Secret** — Fastmail API token + CardDAV app password
- **ConfigMap** — Fastmail username, polling interval, label names, contact group names

Always set resource limits:
```yaml
resources:
  requests:
    memory: "64Mi"
    cpu: "50m"
  limits:
    memory: "256Mi"
```

### Deploy Process

Manual, one command:

```bash
# Build and push image
docker build -t ghcr.io/<username>/mailroom:latest .
docker push ghcr.io/<username>/mailroom:latest

# Deploy (first time)
kubectl apply -f k8s/

# Update after code changes
docker build -t ghcr.io/<username>/mailroom:latest .
docker push ghcr.io/<username>/mailroom:latest
kubectl rollout restart deployment/mailroom
```

That's it. No CI/CD pipeline needed. Build locally, push, restart.

## Key Gotcha from Other Migrants

The screener approach **pollutes your contact list** with no-reply addresses. When you screen in a sender, you're adding them as a contact — including things like `noreply@apple.com`. One migrant had to write a regex script to clean these out. Not a blocker for now — can be cleaned up later. Having all contacts in one of the four groups (Imbox, Feed, Paper Trail, Jail) makes future cleanup easier since you can identify every screened contact by group membership.

## Files to Create

1. `src/main.py` — main script (JMAP polling + CardDAV contact updates)
2. `Dockerfile`
3. `requirements.txt`
4. `k8s/deployment.yaml` — Deployment + containers with resource limits
5. `k8s/secret.yaml` — template (actual values not committed)
6. `k8s/configmap.yaml`
7. `README.md`

## Future: Extensibility (Not In Scope Now)

The Screener workflow is the first use case, but the underlying pattern — "poll Fastmail for emails matching a condition, then take an action on them and/or on the sender's contact" — is generic and reusable.

Future direction: the project could evolve into a **pluggable workflow engine** for Fastmail, where each workflow is a self-contained config (or plugin) that defines its trigger (label, mailbox, header condition) and its actions (move email, update contact group, apply label, etc.). The Screener would be one such workflow. Others could be added and enabled/disabled independently.

This would also make the project useful as an open-source tool — other Fastmail users could pick the workflows they want or write their own.

For now, just build the Screener. But keep the code structured so that the "detect trigger → extract data → take action" loop isn't hardcoded to the screener-specific logic.
