#!/usr/bin/env bash
set -euo pipefail

RELEASE="mailroom"
NAMESPACE="mailroom"
CHART_DIR="$(cd "$(dirname "$0")/../helm/mailroom" && pwd)"
SECRETS_FILE="$CHART_DIR/secrets-values.yaml"

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Error: secrets-values.yaml not found at $SECRETS_FILE" >&2
  exit 1
fi

EXTRA_ARGS=()
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  EXTRA_ARGS+=(--dry-run)
  DRY_RUN=true
  echo "Dry run — no changes will be applied"
  echo
fi

# Pre-flight: ensure namespace exists with PSS labels
# (kubectl handles idempotency — no error if namespace already exists)
if [[ "$DRY_RUN" == true ]]; then
  echo "[dry-run] Would create namespace '$NAMESPACE' with PSS labels"
else
  kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
  kubectl label namespace "$NAMESPACE" \
    pod-security.kubernetes.io/enforce=restricted \
    pod-security.kubernetes.io/enforce-version=latest \
    pod-security.kubernetes.io/warn=restricted \
    pod-security.kubernetes.io/warn-version=latest \
    pod-security.kubernetes.io/audit=restricted \
    pod-security.kubernetes.io/audit-version=latest \
    --overwrite
fi

helm upgrade --install "$RELEASE" "$CHART_DIR" \
  -f "$SECRETS_FILE" \
  -n "$NAMESPACE" --create-namespace \
  "${EXTRA_ARGS[@]}"
