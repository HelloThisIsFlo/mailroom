#!/usr/bin/env bash
set -euo pipefail

CHART_DIR="$(cd "$(dirname "$0")/../helm/mailroom" && pwd)"
SECRETS_FILE="$CHART_DIR/secrets-values.yaml"

if [ ! -f "$SECRETS_FILE" ]; then
  echo "Error: $SECRETS_FILE not found"
  echo "Copy secrets-values.yaml.example and fill in your credentials"
  exit 1
fi

helm upgrade --install mailroom "$CHART_DIR" \
  -f "$SECRETS_FILE" \
  -n mailroom \
  --create-namespace

kubectl rollout status deployment/mailroom -n mailroom --timeout=120s
