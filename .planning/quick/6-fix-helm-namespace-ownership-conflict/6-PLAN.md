---
phase: quick-6
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - helm/mailroom/templates/namespace.yaml
  - scripts/deploy.sh
autonomous: true
requirements: [QUICK-6]

must_haves:
  truths:
    - "namespace.yaml no longer exists in chart templates"
    - "deploy.sh creates the mailroom namespace with PSS labels before helm runs"
    - "helm upgrade --install succeeds on both fresh and existing namespaces"
  artifacts:
    - path: "scripts/deploy.sh"
      provides: "Pre-flight namespace creation with PSS labeling"
      contains: "kubectl create namespace"
    - path: "helm/mailroom/templates/namespace.yaml"
      provides: "DELETED — must not exist"
  key_links:
    - from: "scripts/deploy.sh"
      to: "helm upgrade --install"
      via: "kubectl namespace creation runs before helm command"
      pattern: "kubectl.*namespace.*mailroom"
---

<objective>
Fix Helm namespace ownership conflict by removing namespace.yaml from chart templates and moving namespace creation + PSS labeling into scripts/deploy.sh as a pre-flight kubectl step.

Purpose: Helm fails when namespace.yaml is in templates and the namespace already exists (missing Helm ownership annotations). Moving namespace creation to kubectl eliminates this conflict.
Output: Updated deploy.sh with pre-flight namespace step, deleted namespace.yaml from chart.
</objective>

<execution_context>
@/Users/flo/.claude/get-shit-done/workflows/execute-plan.md
@/Users/flo/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@helm/mailroom/templates/namespace.yaml
@scripts/deploy.sh
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove namespace.yaml and add pre-flight namespace creation to deploy.sh</name>
  <files>helm/mailroom/templates/namespace.yaml, scripts/deploy.sh</files>
  <action>
1. Delete `helm/mailroom/templates/namespace.yaml` entirely.

2. Update `scripts/deploy.sh` to add a pre-flight namespace block BEFORE the `helm upgrade` command (after the dry-run flag parsing, before the helm command). Insert:

```bash
# Pre-flight: ensure namespace exists with PSS labels
# (kubectl handles idempotency — no error if namespace already exists)
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace "$NAMESPACE" \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/warn-version=latest \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/audit-version=latest \
  --overwrite
```

Key details:
- Use `kubectl create namespace --dry-run=client -o yaml | kubectl apply -f -` for idempotent creation (works whether namespace exists or not).
- Use `--overwrite` on label command so it's idempotent on re-runs.
- If the script's `--dry-run` flag is set, SKIP the kubectl commands (they would actually create the namespace). Add a conditional: if dry-run, echo what would happen but don't execute. The dry-run guard should wrap only the kubectl commands (helm already gets `--dry-run` via EXTRA_ARGS).
- Keep `--create-namespace` on the helm command as a safety net (harmless if namespace already exists).
  </action>
  <verify>
    <automated>bash -c 'test ! -f /Users/flo/Work/Private/Dev/Services/mailroom/helm/mailroom/templates/namespace.yaml && echo "PASS: namespace.yaml deleted" || echo "FAIL: namespace.yaml still exists"' && grep -q 'kubectl create namespace' /Users/flo/Work/Private/Dev/Services/mailroom/scripts/deploy.sh && echo "PASS: kubectl in deploy.sh" && grep -q 'pod-security.kubernetes.io/enforce=restricted' /Users/flo/Work/Private/Dev/Services/mailroom/scripts/deploy.sh && echo "PASS: PSS labels in deploy.sh" && bash -n /Users/flo/Work/Private/Dev/Services/mailroom/scripts/deploy.sh && echo "PASS: deploy.sh syntax valid"</automated>
  </verify>
  <done>
- namespace.yaml is deleted from helm/mailroom/templates/
- deploy.sh creates namespace via kubectl before helm runs
- All 6 PSS labels are applied to the namespace
- Dry-run mode skips kubectl commands (echoes intent only)
- deploy.sh passes bash syntax check
  </done>
</task>

</tasks>

<verification>
- `helm/mailroom/templates/namespace.yaml` does not exist
- `scripts/deploy.sh` contains kubectl namespace creation with all 6 PSS labels
- `bash -n scripts/deploy.sh` passes (valid syntax)
- `helm template mailroom helm/mailroom/ -f helm/mailroom/secrets-values.yaml -n mailroom` renders without namespace resource (if secrets-values.yaml available)
</verification>

<success_criteria>
- namespace.yaml removed from chart templates
- deploy.sh handles idempotent namespace creation with PSS labeling before helm runs
- dry-run flag properly gates kubectl commands
- helm command retains --create-namespace as safety net
</success_criteria>

<output>
After completion, create `.planning/quick/6-fix-helm-namespace-ownership-conflict/6-SUMMARY.md`
</output>
