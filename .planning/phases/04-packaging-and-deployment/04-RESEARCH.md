# Phase 4: Packaging and Deployment - Research

**Researched:** 2026-02-25
**Domain:** Docker containerization, Kubernetes deployment, CI/CD with GitHub Actions
**Confidence:** HIGH

## Summary

Phase 4 wraps the existing Mailroom service into a long-lived polling loop, packages it in a Docker container, deploys it to a home Kubernetes cluster, and sets up CI for image builds. The codebase is already fully functional (Phases 1-3.1 complete) with pydantic-settings reading `MAILROOM_` env vars, structlog writing JSON to stderr, and the `ScreenerWorkflow.poll()` method processing one triage cycle. The remaining work is: (1) a `__main__.py` entry point with a polling loop, SIGTERM handling, and health endpoint, (2) a multi-stage Dockerfile using `uv` for fast dependency installation, (3) Kubernetes manifests (Namespace, Deployment, ConfigMap, Secret template), and (4) a GitHub Actions workflow to build and push to ghcr.io.

The project uses `uv` as its package manager (pyproject.toml + uv.lock), Python 3.12, and has zero web framework dependencies. The health endpoint will use Python's stdlib `http.server` in a background thread. All configuration is already externalized via `MAILROOM_` env vars, so k8s ConfigMap/Secret injection via `envFrom` requires zero code changes.

**Primary recommendation:** Build a single `__main__.py` with signal-based graceful shutdown, a `threading`-based health server, and a simple `while not shutdown` polling loop. Use the official uv Docker multi-stage pattern with `python:3.12-slim`. Keep k8s manifests minimal and flat in a `k8s/` directory.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Fixed interval polling (configurable, default 5 minutes) -- no EventSource/push
- Tiered error handling:
  - **Startup failures** (can't connect, missing config, can't resolve mailboxes) -> crash immediately, let k8s restart
  - **Transient runtime errors** (single poll cycle fails) -> log error, skip cycle, continue polling. Triage labels persist so work retries naturally next cycle
  - **Persistent runtime errors** (e.g., 10+ consecutive failures) -> crash, something systemic is wrong
- Graceful shutdown on SIGTERM: finish processing the current poll cycle before exiting
- HTTP health endpoint (`/healthz`) for k8s liveness/readiness probes. Readiness can check recency of last successful poll
- Plain k8s Secrets (manual `kubectl create secret` or apply from local file)
- Commit a `secret.yaml.example` with placeholder values -- actual secret not in git
- All `MAILROOM_` env vars go into a ConfigMap (poll interval, mailbox names, label names, group names, log level, warnings toggle)
- Inject as env vars via `envFrom` in the Deployment spec -- zero code changes needed since pydantic-settings already reads env vars
- GitHub Actions CI: push to main triggers Docker build + push
- Registry: ghcr.io (per DEPLOY-05 requirement)
- Public repository -- no imagePullSecrets needed in the cluster
- Dedicated `mailroom` namespace
- Minimal resource limits: ~64-128Mi memory, ~100m CPU (requests = limits)
- No monitoring/metrics endpoint -- structured JSON logs to stdout are sufficient, check with `kubectl logs`
- Manual deployment via `kubectl apply -f k8s/`
- No GitOps tooling (Flux/ArgoCD)

### Claude's Discretion
- Image tagging strategy (git SHA, latest, semver, or combination)
- Dockerfile base image and multi-stage build approach
- Exact health endpoint implementation (minimal HTTP server framework choice)
- Consecutive failure threshold for crash decision
- GitHub Actions workflow specifics (caching, build matrix, etc.)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEPLOY-01 | Dockerfile builds a slim Python image with all dependencies | Multi-stage uv Dockerfile pattern (Standard Stack, Architecture Patterns) |
| DEPLOY-02 | k8s Deployment manifest with 1 replica and resource limits | K8s manifest patterns, Deployment spec with resource requests/limits |
| DEPLOY-03 | k8s Secret manifest template for Fastmail credentials (actual values not committed) | secret.yaml.example pattern with placeholder values, .gitignore entry |
| DEPLOY-04 | k8s ConfigMap manifest with all configurable values | ConfigMap with all MAILROOM_ env vars, envFrom injection |
| DEPLOY-05 | Image is pushed to ghcr.io and deployable via `kubectl apply -f k8s/` | GitHub Actions workflow with docker/build-push-action, ghcr.io registry |
</phase_requirements>

## Standard Stack

### Core
| Library/Tool | Version | Purpose | Why Standard |
|-------------|---------|---------|--------------|
| python:3.12-slim | 3.12 | Docker base image | Matches project's .python-version; slim variant is ~150MB vs ~1GB for full |
| ghcr.io/astral-sh/uv | latest | Build-time dependency installer | Official uv Docker image; 10-100x faster than pip for dependency resolution |
| http.server (stdlib) | Python 3.12 | Health endpoint `/healthz` | Zero dependencies; ThreadingHTTPServer handles concurrent probes |
| signal (stdlib) | Python 3.12 | SIGTERM graceful shutdown | Standard POSIX signal handling; no external deps |
| threading (stdlib) | Python 3.12 | Background health server | Run health endpoint alongside polling loop |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| docker/login-action | v3 | GitHub Actions GHCR auth | CI workflow login step |
| docker/metadata-action | v5 | Image tag/label extraction | CI workflow tagging step |
| docker/build-push-action | v6 | Docker build + push | CI workflow build step |
| kubectl | >= 1.28 | Manual deployment | Applying k8s manifests to cluster |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| http.server (stdlib) | FastAPI/Flask | Would add a dependency just for one endpoint; stdlib is sufficient for a simple `/healthz` |
| python:3.12-slim | python:3.12-alpine | Alpine uses musl libc which can cause subtle issues with Python packages; slim is safer |
| docker/metadata-action | Manual tagging | metadata-action handles SHA, latest, and branch tagging automatically with less boilerplate |

### Recommendations for Claude's Discretion Items

**Image tagging:** Use `type=sha` + `type=raw,value=latest,enable={{is_default_branch}}`. SHA tags provide traceability (every image maps to a commit), `latest` provides convenience for manual pulls. No semver needed for a personal service.

**Multi-stage build:** Two stages: (1) `python:3.12-slim` builder with uv for dependency install, (2) `python:3.12-slim` runtime with only the venv copied over. Use `UV_COMPILE_BYTECODE=1` for faster startup.

**Health endpoint:** Python stdlib `http.server.ThreadingHTTPServer` on port 8080 in a daemon thread. `GET /healthz` returns 200 with last-poll timestamp. Readiness checks that last successful poll was within 2x poll_interval.

**Consecutive failure threshold:** 10 consecutive failures (as suggested in CONTEXT.md). This is ~50 minutes at 5-min intervals, enough to ride out transient issues without staying broken indefinitely.

**GitHub Actions specifics:** Use BuildKit layer caching via `docker/build-push-action` with `cache-from` and `cache-to` set to `type=gha` for GitHub Actions cache backend. Single-platform build (linux/amd64) is sufficient for a home cluster.

## Architecture Patterns

### Recommended Project Structure
```
src/mailroom/
    __main__.py           # Entry point: polling loop, signal handling, health server
    __init__.py           # (exists)
    core/
        config.py         # (exists) MailroomSettings with pydantic-settings
        logging.py        # (exists) structlog configuration
    clients/
        jmap.py           # (exists) JMAP client
        carddav.py        # (exists) CardDAV client
    workflows/
        screener.py       # (exists) ScreenerWorkflow.poll()
Dockerfile                # Multi-stage build with uv
k8s/
    namespace.yaml        # mailroom namespace
    configmap.yaml        # MAILROOM_ env vars
    secret.yaml.example   # Template with placeholders (NOT real values)
    deployment.yaml       # 1-replica Deployment with envFrom, probes, resources
.github/
    workflows/
        build.yaml        # Build + push to ghcr.io on push to main
.gitignore                # Add k8s/secret.yaml to prevent accidental commits
```

### Pattern 1: Polling Loop with Graceful Shutdown
**What:** Main loop that polls on a fixed interval, handles SIGTERM by finishing the current cycle, and crashes on persistent failures.
**When to use:** Long-lived services that do periodic work without needing a web framework.
**Example:**
```python
# src/mailroom/__main__.py
import signal
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class ShutdownHandler:
    """Flag-based shutdown for SIGTERM graceful exit."""
    def __init__(self):
        self._shutdown = threading.Event()
        signal.signal(signal.SIGTERM, self._handle)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, signum, frame):
        self._shutdown.set()

    @property
    def should_stop(self) -> bool:
        return self._shutdown.is_set()

    def wait(self, timeout: float) -> None:
        """Sleep for timeout seconds, but wake immediately on shutdown signal."""
        self._shutdown.wait(timeout)

# Main loop
shutdown = ShutdownHandler()
consecutive_failures = 0

while not shutdown.should_stop:
    try:
        processed = workflow.poll()
        consecutive_failures = 0
    except Exception:
        consecutive_failures += 1
        log.error("poll_failed", consecutive_failures=consecutive_failures)
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            log.critical("too_many_failures", threshold=MAX_CONSECUTIVE_FAILURES)
            raise SystemExit(1)

    shutdown.wait(settings.poll_interval)
```

### Pattern 2: Threaded Health Endpoint
**What:** Minimal HTTP server on a daemon thread providing `/healthz` for k8s probes.
**When to use:** Services without a web framework that still need k8s health checks.
**Example:**
```python
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

class HealthHandler(BaseHTTPRequestHandler):
    # Class-level state shared with polling loop
    last_successful_poll: float = 0.0
    poll_interval: int = 300

    def do_GET(self):
        if self.path == "/healthz":
            age = time.time() - self.last_successful_poll
            healthy = self.last_successful_poll == 0.0 or age < (self.poll_interval * 2)
            status = 200 if healthy else 503
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok" if healthy else "unhealthy",
                "last_poll_age_seconds": round(age, 1),
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default access logs

def start_health_server(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
```

### Pattern 3: Multi-Stage Dockerfile with uv
**What:** Two-stage Docker build that installs dependencies in a builder stage and copies only the virtualenv to a slim runtime image.
**When to use:** Python projects using uv for package management.
**Example:**
```dockerfile
# Stage 1: Build
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable

# Copy source and install project
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# Stage 2: Runtime
FROM python:3.12-slim

# Create non-root user
RUN groupadd -r app && useradd -r -d /app -g app -N app

# Copy only the virtualenv (no uv binary, no source needed)
COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

USER app
EXPOSE 8080

CMD ["python", "-m", "mailroom"]
```
Source: [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/), [hynek.me](https://hynek.me/articles/docker-uv/)

### Pattern 4: K8s Deployment with envFrom
**What:** Deployment spec that injects ConfigMap and Secret as environment variables, matching pydantic-settings' MAILROOM_ prefix convention.
**When to use:** Python services using pydantic-settings for configuration.
**Example:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mailroom
  namespace: mailroom
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mailroom
  template:
    metadata:
      labels:
        app: mailroom
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: mailroom
          image: ghcr.io/hellothisisflo/mailroom:latest
          envFrom:
            - configMapRef:
                name: mailroom-config
            - secretRef:
                name: mailroom-secrets
          ports:
            - containerPort: 8080
              name: health
          livenessProbe:
            httpGet:
              path: /healthz
              port: health
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /healthz
              port: health
            initialDelaySeconds: 5
            periodSeconds: 30
          resources:
            requests:
              memory: "64Mi"
              cpu: "100m"
            limits:
              memory: "128Mi"
              cpu: "100m"
```

### Anti-Patterns to Avoid
- **Fat runtime image:** Do not include uv, build tools, or dev dependencies in the final image. Use multi-stage builds.
- **Root user in container:** Always create and switch to a non-root user in the runtime stage.
- **Blocking signal handlers:** SIGTERM handler must only set a flag, not do cleanup work. Let the main loop finish its cycle naturally.
- **Secrets in git:** Never commit actual k8s Secret values. Use a `.example` template with placeholder strings.
- **Sleep instead of Event.wait:** Using `time.sleep(300)` ignores SIGTERM for up to 5 minutes. Use `threading.Event.wait()` which wakes immediately on shutdown signal.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Docker image tagging | Custom shell scripts for tag extraction | docker/metadata-action | Handles branch, SHA, latest logic with edge cases already solved |
| GHCR authentication | Manual docker login commands | docker/login-action with GITHUB_TOKEN | Secure, no PAT management, automatic for public repos |
| uv installation in Docker | pip install uv or curl script | `COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv` | Official image, pinnable, fastest method |
| Dependency caching in CI | Manual cache key management | BuildKit layer cache with `type=gha` | Integrated with GitHub Actions cache backend, automatic invalidation |

**Key insight:** The Docker and CI ecosystem has mature, well-tested actions for every step of the build-push pipeline. Custom scripting adds maintenance burden and misses edge cases (multi-arch, cache invalidation, attestation).

## Common Pitfalls

### Pitfall 1: SIGTERM During Poll Cycle
**What goes wrong:** Kubernetes sends SIGTERM, but the service is mid-poll processing a CardDAV operation. If the handler calls `sys.exit()` directly, the triage label may have been removed but the contact not yet created, leaving the system in an inconsistent state.
**Why it happens:** Signal handlers that do immediate cleanup instead of cooperative shutdown.
**How to avoid:** Use a flag-based pattern. The signal handler sets `shutdown_event`. The main loop checks the flag between poll cycles, not during. The `terminationGracePeriodSeconds` in k8s should be longer than the worst-case poll duration (60s is generous for HTTP operations).
**Warning signs:** Pod logs show `SIGKILL` after SIGTERM, indicating the grace period was exhausted.

### Pitfall 2: Health Endpoint Blocks on Poll
**What goes wrong:** If the health endpoint runs in the same thread as the polling loop, k8s probes timeout during long poll cycles and restart the pod.
**Why it happens:** Single-threaded design for health + work.
**How to avoid:** Run the health HTTP server on a daemon thread. It must respond independently of the polling loop's state.
**Warning signs:** Pod restarts with `Liveness probe failed` in kubectl events.

### Pitfall 3: ConfigMap Keys Don't Match Env Var Names
**What goes wrong:** pydantic-settings expects `MAILROOM_JMAP_TOKEN` but the ConfigMap has `jmap_token`. The service starts with default values or crashes on missing required fields.
**Why it happens:** ConfigMap keys become env var names verbatim when using `envFrom`. There is no automatic prefix or case transformation.
**How to avoid:** ConfigMap keys must be the full, uppercased env var names: `MAILROOM_POLL_INTERVAL`, `MAILROOM_LOG_LEVEL`, etc. Match exactly what pydantic-settings expects.
**Warning signs:** Service crashes at startup with pydantic ValidationError for required fields.

### Pitfall 4: Secret Template Committed with Real Values
**What goes wrong:** Developer fills in `secret.yaml.example`, renames to `secret.yaml`, applies it, then accidentally commits the real secret.
**Why it happens:** Git doesn't ignore the `.example` file and the real file isn't in `.gitignore`.
**How to avoid:** Add `k8s/secret.yaml` to `.gitignore`. Keep only `k8s/secret.yaml.example` tracked. Document the workflow in comments.
**Warning signs:** `git status` shows `k8s/secret.yaml` as an untracked or modified file.

### Pitfall 5: uv.lock Not Copied Before pyproject.toml in Dockerfile
**What goes wrong:** Docker cache invalidation. If `COPY . /app` is done before dependency installation, every code change triggers a full dependency reinstall.
**Why it happens:** Incorrect Dockerfile layer ordering.
**How to avoid:** Use bind mounts for uv.lock and pyproject.toml in the dependency install step (before COPY). The official uv Dockerfile guide uses `--mount=type=bind` to avoid COPY entirely for lock files.
**Warning signs:** Docker builds take 30+ seconds even for trivial code changes.

### Pitfall 6: Pod Stuck in CrashLoopBackOff Due to Missing Config
**What goes wrong:** The Deployment is applied before the ConfigMap or Secret, or the Secret has wrong keys. The pod crashes on startup, enters CrashLoopBackOff with increasing delays.
**Why it happens:** k8s `envFrom` silently skips if the referenced ConfigMap/Secret doesn't exist (with `optional: false` it fails). Missing required env vars cause pydantic ValidationError.
**How to avoid:** Apply ConfigMap and Secret before the Deployment. Use `kubectl apply -f k8s/` which applies all files in alphabetical order -- name files with numeric prefixes if needed, or just document the dependency.
**Warning signs:** `kubectl describe pod` shows `CreateContainerConfigError` or pod logs show pydantic ValidationError.

## Code Examples

### Entry Point (__main__.py) Structure
```python
"""Mailroom polling service entry point."""
import signal
import sys
import threading
import time

import structlog

from mailroom.clients.carddav import CardDAVClient
from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings
from mailroom.core.logging import configure_logging
from mailroom.workflows.screener import ScreenerWorkflow

MAX_CONSECUTIVE_FAILURES = 10
HEALTH_PORT = 8080

def main() -> None:
    # 1. Load config (crashes on missing required vars -- startup failure)
    settings = MailroomSettings()
    configure_logging(settings.log_level)
    log = structlog.get_logger(component="main")

    # 2. Connect clients (crashes on auth failure -- startup failure)
    jmap = JMAPClient(token=settings.jmap_token)
    jmap.connect()

    carddav = CardDAVClient(
        username=settings.carddav_username,
        password=settings.carddav_password,
    )
    carddav.connect()

    # 3. Resolve mailboxes and validate groups (crashes on missing -- startup failure)
    mailbox_ids = jmap.resolve_mailboxes(settings.required_mailboxes)
    carddav.validate_groups(settings.contact_groups)

    # 4. Build workflow
    workflow = ScreenerWorkflow(jmap, carddav, settings, mailbox_ids)

    # 5. Start health server
    # ... (see health endpoint pattern)

    # 6. Polling loop with graceful shutdown
    shutdown = threading.Event()
    signal.signal(signal.SIGTERM, lambda s, f: shutdown.set())
    signal.signal(signal.SIGINT, lambda s, f: shutdown.set())

    log.info("service_started", poll_interval=settings.poll_interval)
    consecutive_failures = 0

    while not shutdown.is_set():
        try:
            workflow.poll()
            consecutive_failures = 0
            # Update health endpoint timestamp
        except Exception:
            consecutive_failures += 1
            log.error("poll_failed", consecutive=consecutive_failures, exc_info=True)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log.critical("too_many_consecutive_failures", threshold=MAX_CONSECUTIVE_FAILURES)
                sys.exit(1)

        shutdown.wait(settings.poll_interval)

    log.info("service_stopped", reason="shutdown_signal")

if __name__ == "__main__":
    main()
```
Source: Based on project's existing config/logging patterns + stdlib signal/threading docs.

### GitHub Actions Workflow
```yaml
name: Build and push Docker image

on:
  push:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha
            type=raw,value=latest,enable={{is_default_branch}}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```
Source: [GitHub docs](https://docs.github.com/en/actions/use-cases-and-examples/publishing-packages/publishing-docker-images), [docker/metadata-action](https://github.com/docker/metadata-action)

### ConfigMap Example
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mailroom-config
  namespace: mailroom
data:
  MAILROOM_POLL_INTERVAL: "300"
  MAILROOM_LOG_LEVEL: "info"
  MAILROOM_LABEL_TO_IMBOX: "@ToImbox"
  MAILROOM_LABEL_TO_FEED: "@ToFeed"
  MAILROOM_LABEL_TO_PAPER_TRAIL: "@ToPaperTrail"
  MAILROOM_LABEL_TO_JAIL: "@ToJail"
  MAILROOM_LABEL_TO_PERSON: "@ToPerson"
  MAILROOM_LABEL_MAILROOM_ERROR: "@MailroomError"
  MAILROOM_LABEL_MAILROOM_WARNING: "@MailroomWarning"
  MAILROOM_WARNINGS_ENABLED: "true"
  MAILROOM_SCREENER_MAILBOX: "Screener"
  MAILROOM_GROUP_IMBOX: "Imbox"
  MAILROOM_GROUP_FEED: "Feed"
  MAILROOM_GROUP_PAPER_TRAIL: "Paper Trail"
  MAILROOM_GROUP_JAIL: "Jail"
```

### Secret Template Example
```yaml
# k8s/secret.yaml.example
# Copy to secret.yaml, fill in real values, apply with:
#   kubectl apply -f k8s/secret.yaml
# DO NOT commit secret.yaml to git!
apiVersion: v1
kind: Secret
metadata:
  name: mailroom-secrets
  namespace: mailroom
type: Opaque
stringData:
  MAILROOM_JMAP_TOKEN: "your-fastmail-jmap-token-here"
  MAILROOM_CARDDAV_USERNAME: "your-fastmail-email@fastmail.com"
  MAILROOM_CARDDAV_PASSWORD: "your-fastmail-app-password-here"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pip + requirements.txt in Docker | uv + uv.lock in Docker | 2024-2025 | 10-100x faster installs, reproducible via lockfile |
| Multi-stage with pip freeze | uv sync --locked --no-dev | 2024-2025 | Single command replaces pip install + freeze |
| docker build + docker push scripts | docker/build-push-action v6 | 2024 | BuildKit, layer caching, multi-platform support |
| Manual image tagging | docker/metadata-action v5 | 2023 | Automatic SHA + latest + semver extraction |
| Personal Access Tokens for GHCR | GITHUB_TOKEN with packages permission | 2022 | No manual token management, automatic rotation |

**Deprecated/outdated:**
- `pip install uv` in Dockerfile: Use `COPY --from=ghcr.io/astral-sh/uv:latest` instead (faster, no pip needed)
- `docker/build-push-action@v2-v4`: Use v6 for latest BuildKit features and cache support

## Open Questions

1. **Exact resource limits for production**
   - What we know: User specified ~64-128Mi memory, ~100m CPU
   - What's unclear: Actual memory usage under load (many contacts, many emails per poll)
   - Recommendation: Start with requests=64Mi/100m, limits=128Mi/100m. Monitor with `kubectl top pod` after deployment and adjust. httpx + vobject parsing is not memory-intensive for typical volumes.

2. **terminationGracePeriodSeconds value**
   - What we know: SIGTERM must allow current poll cycle to finish
   - What's unclear: Worst-case poll cycle duration (depends on number of senders and emails)
   - Recommendation: Set to 60 seconds. A single poll cycle involves HTTP calls to Fastmail JMAP/CardDAV which should complete well within this window. If polls regularly exceed 60s, the service has bigger problems.

3. **Health endpoint readiness semantics during startup**
   - What we know: Readiness should check recency of last successful poll
   - What's unclear: What to return before the first poll completes (service just started)
   - Recommendation: Return 200 during startup (last_successful_poll == 0.0 treated as "just started, give it a chance"). After the first poll, require last_poll_age < 2 * poll_interval.

## Sources

### Primary (HIGH confidence)
- [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/) - Multi-stage Dockerfile patterns, env vars, bind mount caching
- [GitHub docs: Publishing Docker images](https://docs.github.com/en/actions/use-cases-and-examples/publishing-packages/publishing-docker-images) - GHCR workflow, GITHUB_TOKEN auth
- [docker/metadata-action](https://github.com/docker/metadata-action) - Tag strategy types (sha, raw, semver)
- [Python http.server docs](https://docs.python.org/3/library/http.server.html) - ThreadingHTTPServer, BaseHTTPRequestHandler
- [Kubernetes ConfigMaps docs](https://kubernetes.io/docs/concepts/configuration/configmap/) - envFrom injection pattern

### Secondary (MEDIUM confidence)
- [hynek.me: Production-ready Python Docker Containers with uv](https://hynek.me/articles/docker-uv/) - Non-root user setup, entrypoint patterns
- [Kubernetes Configuration Good Practices](https://kubernetes.io/blog/2025/11/25/configuration-good-practices/) - Manifest organization, common labels

### Tertiary (LOW confidence)
- None -- all findings verified with primary or secondary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official uv and Docker documentation, well-established patterns
- Architecture: HIGH - Patterns derived from official docs and verified project structure
- Pitfalls: HIGH - Common Docker/k8s issues documented across multiple authoritative sources

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable domain, no fast-moving APIs)
