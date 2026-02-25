# Roadmap: Mailroom

## Overview

Mailroom delivers a single capability: one label tap triages an entire sender. The build order is driven by protocol risk. JMAP (mature library, well-documented) comes first to establish the email query and move layer. CardDAV (bespoke client, unverified group model) comes second as a validation gate -- the KIND:group contact model must be proven against live Fastmail before the triage pipeline is built on top of it. The triage workflow wires both clients into the end-to-end sequence. Deployment wraps the polling loop, container, and k8s manifests into a running service.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation and JMAP Client** - Config, logging, and a working JMAP client that can query, extract, move, and relabel emails (completed 2026-02-24)
- [x] **Phase 2: CardDAV Client (Validation Gate)** - A verified CardDAV client that can manage contacts and group membership, validated against live Fastmail (completed 2026-02-24)
- [x] **Phase 3: Triage Pipeline** - End-to-end screener workflow wiring both clients into the poll-triage-sweep sequence (completed 2026-02-24)
- [x] **Phase 3.1: Person Contact Type with @ToPerson Label** - Default contacts to company (ORG field); @ToPerson sublabel of @ToImbox populates first/last name for real people (INSERTED) (completed 2026-02-25)
- [ ] **Phase 4: Packaging and Deployment** - Main polling loop, Docker image, k8s manifests, running service in the home cluster

## Phase Details

### Phase 1: Foundation and JMAP Client
**Goal**: The service can authenticate with Fastmail, resolve mailboxes, query emails by label, extract senders, move emails between mailboxes, and produce structured JSON logs -- all driven by configuration
**Depends on**: Nothing (first phase)
**Requirements**: JMAP-01, JMAP-02, JMAP-03, JMAP-04, JMAP-05, JMAP-06, JMAP-07, JMAP-08, CONF-01, CONF-02, CONF-03, LOG-01, LOG-02
**Success Criteria** (what must be TRUE):
  1. Running the JMAP client against live Fastmail with a Bearer token returns emails from a specified mailbox (e.g., Screener)
  2. The service resolves human-readable mailbox names (Screener, @ToImbox, etc.) to Fastmail mailbox IDs at startup without hardcoded IDs
  3. Given an email in a triage mailbox, the service extracts the sender address and can remove the triage label using JMAP patch syntax
  4. The service can query all Screener emails from a specific sender and batch-move them to a destination mailbox, adding Inbox label when the destination is Imbox
  5. All operations produce structured JSON log output with action, sender, timestamp, and success/failure
**Plans:** 3/3 plans complete

Plans:
- [ ] 01-01-PLAN.md -- Project scaffold, configuration module, and structured logging
- [ ] 01-02-PLAN.md -- JMAP client: session discovery and mailbox resolution (TDD)
- [ ] 01-03-PLAN.md -- JMAP client: email query, extraction, and move operations (TDD)

### Phase 2: CardDAV Client (Validation Gate)
**Goal**: The service can search, create, and update contacts via CardDAV, and reliably assign contacts to Fastmail contact groups using the KIND:group model -- verified against live Fastmail before proceeding
**Depends on**: Phase 1
**Requirements**: CDAV-01, CDAV-02, CDAV-03, CDAV-04, CDAV-05
**Success Criteria** (what must be TRUE):
  1. A contact created via the CardDAV client appears correctly in the Fastmail web UI and iOS Contacts with proper vCard 3.0 format
  2. Adding a contact to a group (e.g., Imbox) via KIND:group MEMBER entry causes Fastmail rules targeting that group to fire correctly on new email from that sender
  3. Searching for an existing contact by email address finds the contact without creating a duplicate -- verified by running the same sender through twice
  4. Concurrent edits are handled safely: the client sends If-Match ETags on PUT and retries on 412 Precondition Failed
**Plans:** 3/3 plans complete

Plans:
- [x] 02-01-PLAN.md -- Config update, CardDAV client core (auth, PROPFIND discovery, group validation) (TDD)
- [x] 02-02-PLAN.md -- Contact operations: search, create, group membership, upsert with merge-cautious logic (TDD)
- [x] 02-03-PLAN.md -- Human test scripts for live Fastmail validation (validation gate checkpoint)

### Phase 3: Triage Pipeline
**Goal**: The complete screener workflow runs end-to-end: poll for triaged emails, process each sender (upsert contact into group, sweep Screener emails, relabel for Imbox, remove triage label), with retry safety on failure
**Depends on**: Phase 2
**Requirements**: TRIAGE-01, TRIAGE-02, TRIAGE-03, TRIAGE-04, TRIAGE-05, TRIAGE-06
**Success Criteria** (what must be TRUE):
  1. Applying a triage label (@ToImbox) to an email in Screener and running the service causes the sender to appear in the Imbox contact group, all their Screener emails to move to the Imbox destination, and the triage label to be removed
  2. The same flow works for all four destinations: Imbox (with Inbox re-label), Feed, Paper Trail, and Jail
  3. Processing the same email twice does not create duplicate contacts or duplicate email moves (idempotent)
  4. If the CardDAV call fails mid-processing, the triage label remains on the email and the next poll cycle retries successfully
**Plans:** 3/3 plans complete

Plans:
- [x] 03-01-PLAN.md -- ScreenerWorkflow poll cycle with conflict detection and error labeling (TDD)
- [x] 03-02-PLAN.md -- Per-sender triage processing: upsert, sweep, relabel, already-grouped check (TDD)
- [x] 03-03-PLAN.md -- Gap closure: sender display name propagation from JMAP From header to contact creation (TDD)

### Phase 3.1: Person Contact Type with @ToPerson Label (INSERTED)

**Goal:** Default new contacts to company type (ORG field, empty N). Add @ToPerson triage label that creates person-type contacts (FN + N with first/last name) routed to Imbox group. Introduce @MailroomWarning label for non-blocking alerts (name mismatch on existing contacts).
**Depends on:** Phase 3
**Requirements:** CDAV-03 (extended), TRIAGE-02 (extended)
**Success Criteria** (what must be TRUE):
  1. Triaging with @ToImbox creates a company-type contact (FN + ORG, empty N) — not a person-type contact
  2. Triaging with @ToPerson creates a person-type contact (FN + N with first/last name, no ORG) routed to Imbox group
  3. @ToPerson conflicts with @ToImbox and other triage labels (flagged as @MailroomError)
  4. When @ToPerson encounters an existing contact with a different name, processing continues but @MailroomWarning is applied
  5. @MailroomWarning label is validated at startup (fail fast if missing and warnings enabled)
**Plans:** 3/3 plans complete

Plans:
- [x] 03.1-01-PLAN.md -- Config extensions + CardDAV company/person contact creation with nameparser (TDD)
- [x] 03.1-02-PLAN.md -- Workflow contact_type routing, @MailroomWarning application, name mismatch handling (TDD)
- [x] 03.1-03-PLAN.md -- Human integration tests for person and company contact types (checkpoint)

### Phase 4: Packaging and Deployment
**Goal**: Mailroom runs as a long-lived polling service in a Docker container on the home Kubernetes cluster, with all configuration externalized and credentials securely managed
**Depends on**: Phase 3
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05
**Success Criteria** (what must be TRUE):
  1. `docker build` produces a slim image that starts the polling loop and processes triage labels end-to-end without errors
  2. `kubectl apply -f k8s/` deploys the service with ConfigMap-driven label/group names and Secret-managed credentials -- no credentials in the git repository
  3. The service runs continuously in the cluster, polling every 5 minutes, and correctly triages a test email applied from the Fastmail iOS app
  4. After a pod restart (simulated kill), the service resumes polling and processes any triage labels that accumulated during downtime
**Plans:** 3 plans

Plans:
- [ ] 04-01-PLAN.md -- Entry point (__main__.py) with polling loop, health endpoint, signal handling + Dockerfile
- [ ] 04-02-PLAN.md -- Kubernetes manifests (namespace, configmap, secret template, deployment) + GitHub Actions CI
- [ ] 04-03-PLAN.md -- Human integration test for Docker container end-to-end verification (checkpoint)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 3.1 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and JMAP Client | 3/3 | Complete    | 2026-02-24 |
| 2. CardDAV Client (Validation Gate) | 3/3 | Complete    | 2026-02-24 |
| 3. Triage Pipeline | 3/3 | Complete    | 2026-02-24 |
| 3.1. Person Contact Type with @ToPerson Label | 3/3 | Complete    | 2026-02-25 |
| 4. Packaging and Deployment | 0/3 | Not started | - |
