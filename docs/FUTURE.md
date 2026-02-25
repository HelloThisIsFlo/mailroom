# Future Vision

Strategic notes on the direction of Mailroom. This is the author's thinking, not a public roadmap commitment.

## Open-Core Strategy

Mailroom follows an open-core model inspired by [Plausible](https://plausible.io/), [Cal.com](https://cal.com/), and [Supabase](https://supabase.com/):

- **Public engine (this repo):** The triage pipeline, JMAP/CardDAV clients, and polling service remain open source under AGPL-3.0. Anyone can self-host, fork, or contribute.
- **Closed SaaS layer (future, separate repo):** A hosted service built on top of the open-source engine. Adds OAuth-based Fastmail login, managed infrastructure, a rule builder UI, and billing. This layer is proprietary.

The engine is the product. The SaaS layer is convenience.

## Hosted Service

The biggest barrier to adoption is deployment complexity. A hosted version would eliminate that:

- **OAuth Fastmail login:** Users connect their Fastmail account with a single click. No API tokens, no app passwords, no manual setup.
- **Managed infrastructure:** No Docker, no Kubernetes, no server to maintain. Mailroom runs in the cloud, polling on behalf of the user.
- **Dashboard:** View triage history, manage contact groups, see error/warning status.

## Rule Builder UI

The current triage model is four fixed destinations (Imbox, Feed, Paper Trail, Jail) plus person contacts. A visual rule builder would allow:

- Custom destination mailboxes beyond the four defaults
- Conditional rules (e.g., "if subject contains 'invoice', route to Paper Trail")
- Per-sender overrides and exceptions
- Bulk operations (re-triage all emails from a sender)

## Multi-Provider

Mailroom is currently Fastmail-specific. The JMAP and CardDAV protocols are standards, but the implementation makes Fastmail-specific assumptions (session discovery URL, contact group model, mailbox structure). Abstracting the protocol layer could enable support for other providers:

- **Fastmail** (current) -- JMAP + CardDAV
- **Google Workspace** -- Gmail API + Google People API
- **Microsoft 365** -- Microsoft Graph API
- **Any JMAP provider** -- as the JMAP ecosystem grows

This would require a provider abstraction layer and per-provider adapters.

---

*These are directions, not promises. The open-source engine is the priority.*
