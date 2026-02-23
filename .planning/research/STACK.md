# Technology Stack

**Project:** Mailroom (Fastmail Email Triage Automation)
**Researched:** 2026-02-23
**Overall confidence:** MEDIUM-HIGH

## Recommended Stack

### Runtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.13 | Runtime | Latest stable. All key dependencies support it. Use `python:3.13-slim` Docker image for minimal footprint (~50MB vs ~350MB for full). | HIGH |
| uv | 0.10.x | Package/project manager | Replaces pip, pip-tools, venv, and poetry in one tool. 10-100x faster than pip. Generates lockfiles. Built by Astral (same team as ruff). The standard for new Python projects in 2025+. | HIGH |

### JMAP Email Operations

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| jmapc | 0.2.23 | JMAP client for Fastmail email operations | **The only maintained Python JMAP client.** Supports Email/query, Email/get, Email/set, Mailbox/query, Mailbox/get -- every operation Mailroom needs. Has Fastmail-specific support (MaskedEmail). Beta status (0.x) but actively maintained (last release Jan 2025), 52 GitHub stars. Result references work for batched requests. GPL-3.0 license. | MEDIUM |

**jmapc covers these Mailroom operations:**
- `Email/query` with `in_mailbox` filter -- find emails in triage label folders
- `Email/get` with `mail_from` property -- extract sender addresses
- `Email/set` with `update` -- modify `mailbox_ids` to remove triage labels and add destination labels
- `Mailbox/query` + `Mailbox/get` -- resolve label names to mailbox IDs

**Key jmapc patterns verified from source:**
```python
# Client creation (uses requests internally)
client = Client.create_with_api_token(
    host="jmap.fastmail.com",
    api_token="fmu1-..."
)

# Batched requests with result references
results = client.request([
    MailboxQuery(filter=MailboxQueryFilterCondition(name="@ToImbox")),
    MailboxGet(ids=Ref("/ids")),
])

# Email/set for label changes -- use the update dict
EmailSet(update={
    "email-id-here": {
        "mailbox_ids": {"inbox-id": True, "screener-id": False}
    }
})
```

### CardDAV Contact Management

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| requests | 2.32.x | HTTP client for CardDAV | jmapc already depends on requests internally. CardDAV is just HTTP (PROPFIND, PUT, REPORT) with XML bodies. No dedicated CardDAV client library exists for Python that is both maintained and suitable as an importable library (caldav is CalDAV-only; pyCardDAV last updated 2014; vdirsyncer is a CLI tool, not a library). Raw requests with Basic auth against `carddav.fastmail.com` is the standard approach. | HIGH |
| vobject | 0.9.9 | vCard parsing and serialization | **The standard Python vCard library.** Production/stable status. Parses and creates vCard 3.0 files. Handles `FN`, `EMAIL`, `CATEGORIES`, `X-ADDRESSBOOKSERVER-GROUP` and other properties needed for Fastmail contact groups. Last updated Dec 2024. Note: still depends on `six` (Python 2 compat), but works fine on Python 3. | HIGH |
| lxml | 6.0.x | XML parsing for CardDAV responses | CardDAV uses WebDAV (XML over HTTP). lxml is the fastest and most complete XML parser for Python. Needed to parse PROPFIND/REPORT multistatus responses. | HIGH |

**Fastmail CardDAV endpoints (verified from Fastmail help docs):**
- Auto-discovery: `https://carddav.fastmail.com/`
- Address book: `https://carddav.fastmail.com/dav/addressbooks/user/<username>/Default`
- Auth: HTTP Basic with app password (NOT regular Fastmail password)

**CardDAV operations Mailroom needs:**
1. **Find existing contact by email** -- REPORT with `addressbook-query` + `prop-filter` on `EMAIL`
2. **Create new contact** -- PUT vCard to `<addressbook-url>/<uid>.vcf`
3. **Update contact group membership** -- Modify `X-ADDRESSBOOKSERVER-GROUP` or `CATEGORIES` in vCard, PUT back
4. **List contacts in a group** -- REPORT with filter on group membership property

**Raw CardDAV pattern:**
```python
import requests
from lxml import etree

# Search for contact by email
body = """<?xml version="1.0" encoding="utf-8"?>
<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:gethref/>
    <C:address-data/>
  </D:prop>
  <C:filter>
    <C:prop-filter name="EMAIL">
      <C:text-match collation="i;unicode-casemap" match-type="equals">
        sender@example.com
      </C:text-match>
    </C:prop-filter>
  </C:filter>
</C:addressbook-query>"""

resp = requests.request(
    "REPORT",
    "https://carddav.fastmail.com/dav/addressbooks/user/me@example.com/Default",
    data=body,
    headers={"Content-Type": "application/xml", "Depth": "1"},
    auth=("me@example.com", "app-password"),
)
```

### Configuration

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pydantic-settings | 2.13.x | Configuration management | Reads from environment variables (ConfigMap/Secrets in k8s) with type validation. Supports nested models and field aliases. Auto-reads `.env` files for local dev. Better than raw `os.environ` -- catches misconfigs at startup, not at runtime. | HIGH |
| pydantic | 2.12.x | Data validation (dependency of pydantic-settings) | Used for validating API responses and internal data models. Standard Python data validation library. | HIGH |

### Logging

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| structlog | 25.5.0 | Structured JSON logging | **The standard for structured logging in Python.** 4,584 GitHub stars, actively maintained (5 releases in 2025 alone, latest Oct 2025). Outputs JSON natively for k8s log aggregation. Processor pipeline architecture. Integrates with stdlib `logging`. Zero external dependencies. ConsoleRenderer for local dev, JSONRenderer for production. | HIGH |

**structlog pattern for Mailroom:**
```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),  # for k8s
    ],
)

log = structlog.get_logger()
log.info("email_triaged", sender="foo@bar.com", action="imbox", email_count=3)
# {"event": "email_triaged", "sender": "foo@bar.com", "action": "imbox", "email_count": 3, "level": "info", "timestamp": "2026-02-23T..."}
```

### Retry / Resilience

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| tenacity | 9.1.x | Retry with exponential backoff | Standard Python retry library. Decorator-based. Configurable stop conditions, wait strategies, retry conditions. Perfect for retrying failed JMAP/CardDAV calls. Widely used (50M+ monthly downloads). | HIGH |

**tenacity pattern:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def call_carddav(url, body):
    ...
```

### Infrastructure

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Docker | -- | Container runtime | `python:3.13-slim` base. Multi-stage build not needed (no compilation step if lxml wheels are available). | HIGH |
| ghcr.io | -- | Container registry | Free for GitHub repos, no extra infra, already decided in PROJECT.md. | HIGH |
| Kubernetes | -- | Deployment target | Existing home cluster. Deployment + ConfigMap + Secret. No Helm needed for a single service. | HIGH |

### Dev Tooling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| uv | 0.10.x | Package management, virtual env, lockfile | See Runtime section above. Use `uv init`, `uv add`, `uv lock`, `uv run`. | HIGH |
| ruff | 0.15.x | Linting + formatting | Replaces flake8, isort, black, and pylint. Single tool, blazingly fast (Rust). The standard for new Python projects. | HIGH |
| pytest | 9.0.x | Testing | Standard Python test framework. | HIGH |
| responses | 0.26.x | Mock requests library in tests | Mocks HTTP calls made by `requests` (used by both jmapc and our CardDAV code). More mature and widely used than alternatives. | HIGH |
| mypy | 1.19.x | Type checking | Standard Python type checker. jmapc has py.typed marker. | MEDIUM |
| pytest-cov | 7.0.x | Test coverage | Standard coverage plugin for pytest. | HIGH |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| JMAP client | jmapc | Raw requests + manual JSON | jmapc provides typed models, result references, session handling, and error handling. Building this from scratch would be significant effort for no benefit. |
| JMAP client | jmapc | jmap-client 0.0.1 | Last updated Oct 2019, v0.0.1, abandoned. |
| CardDAV client | requests + vobject + lxml | caldav library | caldav is CalDAV-only (RFC 4791). No CardDAV (RFC 6352) support whatsoever. Zero search results for "carddav" in its codebase. |
| CardDAV client | requests + vobject + lxml | pyCardDAV | Last updated Feb 2014. Completely abandoned. |
| CardDAV client | requests + vobject + lxml | vdirsyncer | CLI sync tool, not an importable library. Designed for filesystem sync, not programmatic contact management. |
| HTTP client | requests | httpx | jmapc uses requests internally. Adding httpx means two HTTP clients. For sync-only CardDAV calls in a polling service, requests is perfectly adequate. |
| Logging | structlog | python-json-logger | structlog is more powerful (processor pipeline, context vars, log binding). python-json-logger just formats stdlib logger output as JSON -- less ergonomic for structured fields. |
| Logging | structlog | stdlib logging + JSONFormatter | Verbose, no context binding, manual field management. structlog wraps stdlib anyway. |
| Config | pydantic-settings | python-dotenv + os.environ | No type validation, no early failure on missing config, no nested config support. |
| Config | pydantic-settings | dynaconf | Overkill for a single service. pydantic-settings is simpler and already part of the pydantic ecosystem. |
| Retry | tenacity | Manual try/except + sleep | Error-prone, no backoff, no configurable strategies. |
| Retry | tenacity | Built into polling loop | Conflates polling logic with error handling. tenacity keeps retry logic declarative and separate. |
| Package mgr | uv | poetry | uv is faster, simpler, and the direction Python tooling is heading. Poetry is fine but heavier and slower. |
| Package mgr | uv | pip + pip-tools | Multiple tools where one suffices. No lockfile management. |
| Linting | ruff | flake8 + isort + black | Three tools where one suffices. Ruff is orders of magnitude faster. |
| Scheduling | Simple `time.sleep` loop | APScheduler / schedule | For a single polling interval, `while True: poll(); sleep(300)` is the simplest correct approach. APScheduler adds complexity for zero benefit in a single-task service. |

## Important: What NOT to Use

| Technology | Why Not |
|------------|---------|
| asyncio / async frameworks | This is a simple polling service. Sync code is easier to debug, test, and reason about. No concurrent I/O pressure. jmapc is sync-only anyway. |
| FastAPI / Flask / any web framework | No HTTP endpoints needed. This is a background worker, not a web service. |
| SQLite / PostgreSQL / any database | No persistent state needed. Contact state lives in Fastmail (CardDAV). Email state lives in Fastmail (JMAP). The service is stateless by design. |
| Celery / RQ / any task queue | Single task, single worker, simple sleep loop. Task queues add infra and complexity for zero benefit. |
| Helm | Single deployment with ConfigMap and Secret. Raw kubectl manifests are simpler and sufficient. |
| Docker Compose | Deploying to Kubernetes, not Docker Compose. Only one container, no multi-service orchestration needed. |

## Installation

```bash
# Initialize project
uv init mailroom
cd mailroom

# Core dependencies
uv add jmapc requests vobject lxml structlog pydantic-settings tenacity

# Dev dependencies
uv add --dev ruff pytest responses mypy pytest-cov
```

## Dockerfile Sketch

```dockerfile
FROM python:3.13-slim

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/

# Run the service
CMD ["uv", "run", "python", "-m", "mailroom"]
```

## Kubernetes Manifest Sketch

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mailroom
spec:
  replicas: 1  # Single instance -- no concurrency needed
  template:
    spec:
      containers:
      - name: mailroom
        image: ghcr.io/<user>/mailroom:latest
        envFrom:
        - configMapRef:
            name: mailroom-config
        - secretRef:
            name: mailroom-secrets
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: mailroom-config
data:
  POLL_INTERVAL: "300"
  JMAP_HOST: "jmap.fastmail.com"
  CARDDAV_URL: "https://carddav.fastmail.com/dav/addressbooks/user/<user>/Default"
---
apiVersion: v1
kind: Secret
metadata:
  name: mailroom-secrets
type: Opaque
stringData:
  JMAP_API_TOKEN: "fmu1-..."
  CARDDAV_PASSWORD: "..."
  CARDDAV_USERNAME: "..."
```

## Risk Assessment

### jmapc is the biggest risk

- **Version 0.2.x** -- pre-1.0, API may change
- **Single maintainer** (smkent)
- **52 stars** -- small community
- **GPL-3.0** -- copyleft license, entire project must be GPL-3.0 compatible (acceptable for a personal service, would be a problem for commercial distribution)
- **Last release Jan 2025** -- over a year ago, but JMAP spec is stable so fewer updates needed
- **Mitigation:** jmapc wraps standard JMAP JSON-over-HTTP. If abandoned, we can replace it with raw requests + JSON. The JMAP protocol is simple enough that a custom thin client is feasible (unlike, say, replacing an ORM).

### CardDAV is manual but straightforward

- No library exists, so we write a thin CardDAV client (~200 lines)
- CardDAV is a well-documented RFC (6352) over WebDAV
- Fastmail's implementation is standards-compliant
- **Mitigation:** Encapsulate all CardDAV operations in a single module. If a good library emerges, swap it in.

### vobject is stable but old

- Still depends on `six` (Python 2 compat library)
- Last meaningful update Dec 2024
- **Mitigation:** vCard format is simple and stable. vobject works correctly for our needs (create/parse contacts with email, name, group properties). If it breaks on future Python, vCard generation is simple enough to do manually.

## Sources

- PyPI JSON API (pypi.org/pypi/{package}/json) -- verified versions, upload dates, dependencies (HIGH confidence)
- GitHub API (api.github.com) -- verified stars, activity, repository status (HIGH confidence)
- GitHub raw source (raw.githubusercontent.com) -- verified jmapc API, models, methods (HIGH confidence)
- Fastmail help center (fastmail.help) -- verified CardDAV server endpoints and auth requirements (HIGH confidence)
- JMAP specification (jmap.io) -- verified protocol capabilities and method names (HIGH confidence)
