# Deploying Mailroom to Kubernetes

Step-by-step guide for deploying Mailroom to a Kubernetes cluster. Assumes familiarity with kubectl and container registries.

## Prerequisites

- Docker installed locally
- `kubectl` configured with access to your cluster
- A Fastmail account with:
  - **JMAP API token** (Settings > Privacy & Security > API tokens)
  - **App password** with CardDAV access (Settings > Privacy & Security > Integrations > New app password)

## Steps

### 1. Build the Docker image

```bash
docker build -t ghcr.io/hellothisisflo/mailroom:latest .
```

### 2. Push to your container registry

```bash
docker push ghcr.io/hellothisisflo/mailroom:latest
```

> If using a different registry, update the image reference in `k8s/deployment.yaml` to match.

### 3. Create the namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

### 4. Create secrets

Copy the example and fill in your real Fastmail credentials:

```bash
cp k8s/secret.yaml.example k8s/secret.yaml
```

Edit `k8s/secret.yaml` and replace the placeholder values with your actual credentials. The file uses `stringData`, so you enter plaintext values directly -- no base64 encoding needed.

```bash
kubectl apply -f k8s/secret.yaml
```

> `k8s/secret.yaml` is in `.gitignore` -- never commit real credentials.

### 5. Apply the ConfigMap

```bash
kubectl apply -f k8s/configmap.yaml
```

The ConfigMap contains all non-secret configuration (poll interval, label names, contact group names). See [config.md](config.md) for a full reference of every environment variable.

### 6. Deploy

```bash
kubectl apply -f k8s/deployment.yaml
```

### 7. Verify

Check the pod is running:

```bash
kubectl -n mailroom get pods
```

Watch the logs:

```bash
kubectl -n mailroom logs -f deploy/mailroom
```

You should see `service_started` with the configured poll interval.

## Health Check

Mailroom exposes a `/healthz` endpoint on port 8080 inside the container. The Kubernetes deployment is already configured with liveness and readiness probes pointing to this endpoint.

To check health manually:

```bash
kubectl -n mailroom port-forward deploy/mailroom 8080:8080
curl http://localhost:8080/healthz
```

Returns `{"status": "ok", "last_poll_age_seconds": ...}` with HTTP 200 when healthy, or HTTP 503 when the last successful poll is too old.

## Updating

Build and push a new image, then restart the deployment:

```bash
docker build -t ghcr.io/hellothisisflo/mailroom:latest .
docker push ghcr.io/hellothisisflo/mailroom:latest
kubectl -n mailroom rollout restart deploy/mailroom
```

Watch the rollout:

```bash
kubectl -n mailroom rollout status deploy/mailroom
```

## Troubleshooting

### Pod crashes immediately (`CrashLoopBackOff`)

**Missing credentials:** Mailroom requires `MAILROOM_JMAP_TOKEN`, `MAILROOM_CARDDAV_USERNAME`, and `MAILROOM_CARDDAV_PASSWORD` to start. Check that the secret was applied:

```bash
kubectl -n mailroom get secret mailroom-secrets
```

**Wrong credentials:** Check logs for authentication errors:

```bash
kubectl -n mailroom logs deploy/mailroom --previous
```

### Pod starts but no emails are triaged

**Missing Fastmail labels:** Mailroom validates that all triage labels (`@ToImbox`, `@ToFeed`, `@ToPaperTrail`, `@ToJail`, `@ToPerson`) and system labels (`@MailroomError`, `@MailroomWarning`) exist as Fastmail mailboxes/labels at startup. Create them in Fastmail before deploying.

**Missing contact groups:** The four contact groups (`Imbox`, `Feed`, `Paper Trail`, `Jail`) must exist in Fastmail Contacts. Create them manually in Fastmail before deploying.

**Poll interval:** By default, Mailroom polls every 300 seconds (5 minutes). Check the ConfigMap if you want to adjust this.

### Connection failures

**JMAP errors:** Verify your JMAP token is valid and has the required scopes.

**CardDAV errors:** Verify the app password has CardDAV access. The username should be your full Fastmail email address.
