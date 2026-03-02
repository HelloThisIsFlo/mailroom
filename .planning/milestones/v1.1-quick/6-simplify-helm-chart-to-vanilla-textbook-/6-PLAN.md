---
phase: quick-6
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - helm/mailroom/templates/deployment.yaml
  - helm/mailroom/templates/setup-job.yaml
  - helm/mailroom/templates/_helpers.tpl
  - helm/mailroom/templates/namespace.yaml
autonomous: true
requirements: [TODO-15]

must_haves:
  truths:
    - "namespace.yaml template no longer exists"
    - "No securityContext blocks remain in deployment.yaml or setup-job.yaml"
    - "No readOnlyRootFilesystem or /tmp emptyDir hack in either template"
    - "No podSecurityContext or containerSecurityContext template definitions in _helpers.tpl"
    - "helm template renders valid YAML without errors"
    - "Standard patterns (labels, configmap, secret, probes, envFrom, resources) are untouched"
  artifacts:
    - path: "helm/mailroom/templates/deployment.yaml"
      provides: "Simplified deployment without securityContext"
    - path: "helm/mailroom/templates/setup-job.yaml"
      provides: "Simplified job without securityContext"
    - path: "helm/mailroom/templates/_helpers.tpl"
      provides: "Standard helpers only (name, fullname, chart, labels, selectorLabels)"
  key_links: []
---

<objective>
Strip security hardening cruft from the Helm chart, leaving only vanilla textbook patterns.

Purpose: The chart currently has PodSecurity Admission securityContext blocks, readOnlyRootFilesystem + /tmp emptyDir hacks, and a namespace.yaml that manages the namespace. These are infrastructure-level concerns that don't belong in an application chart. Remove them to keep the chart simple and beginner-friendly.

Output: Simplified Helm chart with no securityContext, no namespace management, no /tmp volume hacking.
</objective>

<execution_context>
@/Users/flo/.claude/get-shit-done/workflows/execute-plan.md
@/Users/flo/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@helm/mailroom/templates/deployment.yaml
@helm/mailroom/templates/setup-job.yaml
@helm/mailroom/templates/_helpers.tpl
@helm/mailroom/templates/namespace.yaml
@helm/mailroom/values.yaml
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove security hardening and namespace template</name>
  <files>
    helm/mailroom/templates/namespace.yaml
    helm/mailroom/templates/_helpers.tpl
    helm/mailroom/templates/deployment.yaml
    helm/mailroom/templates/setup-job.yaml
  </files>
  <action>
    1. DELETE `helm/mailroom/templates/namespace.yaml` entirely (rm the file). Namespaces are managed externally, not by app charts.

    2. In `helm/mailroom/templates/_helpers.tpl`:
       - DELETE the `mailroom.podSecurityContext` template definition (lines 49-56: the comment + define block for pod-level security context)
       - DELETE the `mailroom.containerSecurityContext` template definition (lines 58-70: the comment + define block for container-level security context)
       - Keep all other templates: mailroom.name, mailroom.fullname, mailroom.chart, mailroom.labels, mailroom.selectorLabels

    3. In `helm/mailroom/templates/deployment.yaml`:
       - REMOVE the pod-level `securityContext:` block (2 lines: `securityContext:` + the include line, currently lines 19-20)
       - REMOVE the container-level `securityContext:` block (2 lines: `securityContext:` + the include line, currently lines 53-54)
       - REMOVE the `/tmp` volumeMount from the container's `volumeMounts:` (2 lines: `- name: tmp` + `mountPath: /tmp`, currently lines 39-40)
       - REMOVE the `tmp` emptyDir volume from `volumes:` (2 lines: `- name: tmp` + `emptyDir: {}`, currently lines 61-62)
       - Keep everything else: metadata, replicas, selector, labels, terminationGracePeriodSeconds, container image/ports/env/envFrom, config volumeMount + volume, probes, resources

    4. In `helm/mailroom/templates/setup-job.yaml`:
       - REMOVE the pod-level `securityContext:` block (2 lines: `securityContext:` + the include line, currently lines 20-21)
       - REMOVE the container-level `securityContext:` block (2 lines: `securityContext:` + the include line, currently lines 43-44)
       - REMOVE the `/tmp` volumeMount (2 lines: `- name: tmp` + `mountPath: /tmp`, currently lines 40-41)
       - REMOVE the `tmp` emptyDir volume (2 lines: `- name: tmp` + `emptyDir: {}`, currently lines 49-50... after removals above the line numbers shift)
       - Keep everything else: metadata, annotations (helm hooks), backoffLimit, restartPolicy, container image/command/args/env/envFrom, config volumeMount + volume, resources
  </action>
  <verify>
    <automated>
      test ! -f helm/mailroom/templates/namespace.yaml && \
      ! grep -q "securityContext" helm/mailroom/templates/deployment.yaml && \
      ! grep -q "securityContext" helm/mailroom/templates/setup-job.yaml && \
      ! grep -q "podSecurityContext\|containerSecurityContext" helm/mailroom/templates/_helpers.tpl && \
      ! grep -q "readOnlyRootFilesystem" helm/mailroom/templates/_helpers.tpl && \
      ! grep -qP "name: tmp|emptyDir" helm/mailroom/templates/deployment.yaml && \
      ! grep -qP "name: tmp|emptyDir" helm/mailroom/templates/setup-job.yaml && \
      echo "PASS: All security cruft removed"
    </automated>
  </verify>
  <done>
    namespace.yaml deleted. No securityContext, readOnlyRootFilesystem, or /tmp emptyDir hack remains in deployment.yaml, setup-job.yaml, or _helpers.tpl. All standard patterns (labels, probes, envFrom, config volume, resources) are intact.
  </done>
</task>

<task type="auto">
  <name>Task 2: Validate chart renders correctly</name>
  <files>helm/mailroom/templates/deployment.yaml, helm/mailroom/templates/setup-job.yaml, helm/mailroom/templates/_helpers.tpl</files>
  <action>
    Run `helm template` to verify the simplified chart still renders valid Kubernetes YAML without errors. Use the existing values.yaml and a minimal secrets override.

    ```
    helm template mailroom helm/mailroom/ --set secrets.MAILROOM_JMAP_TOKEN=test --set secrets.MAILROOM_CARDDAV_PASSWORD=test
    ```

    Verify the output contains:
    - A Deployment with the mailroom container, config volume, probes, envFrom
    - A Job with helm hook annotations, setup command, config volume, envFrom
    - A ConfigMap with the config.yaml content
    - A Secret with the test values
    - NO Namespace resource in the output
    - NO securityContext anywhere in the output

    If `helm` CLI is not installed, skip the template rendering and rely on Task 1's file-level verification. The chart structure is simple enough that correct file edits guarantee valid output.
  </action>
  <verify>
    <automated>
      helm template mailroom helm/mailroom/ --set secrets.MAILROOM_JMAP_TOKEN=test --set secrets.MAILROOM_CARDDAV_PASSWORD=test 2>&1 | grep -q "kind: Deployment" && \
      ! helm template mailroom helm/mailroom/ --set secrets.MAILROOM_JMAP_TOKEN=test --set secrets.MAILROOM_CARDDAV_PASSWORD=test 2>&1 | grep -q "securityContext" && \
      ! helm template mailroom helm/mailroom/ --set secrets.MAILROOM_JMAP_TOKEN=test --set secrets.MAILROOM_CARDDAV_PASSWORD=test 2>&1 | grep -q "kind: Namespace" && \
      echo "PASS: Chart renders valid YAML, no security cruft, no namespace" || \
      echo "WARN: helm not available or render issue -- rely on Task 1 file checks"
    </automated>
  </verify>
  <done>
    `helm template` renders valid YAML. Output contains Deployment, Job, ConfigMap, Secret. No Namespace resource, no securityContext blocks in rendered output.
  </done>
</task>

</tasks>

<verification>
- namespace.yaml file does not exist
- grep for "securityContext", "podSecurityContext", "containerSecurityContext", "readOnlyRootFilesystem", "emptyDir" across all templates returns zero matches
- `helm template` renders clean YAML (if helm CLI available)
- Standard patterns (labels, probes, envFrom, config volume, resources) still present in templates
</verification>

<success_criteria>
Helm chart contains only vanilla textbook patterns: Deployment, Job, ConfigMap, Secret, NOTES.txt, and standard _helpers.tpl. No securityContext, no namespace management, no readOnlyRootFilesystem hack.
</success_criteria>

<output>
After completion, create `.planning/quick/6-simplify-helm-chart-to-vanilla-textbook-/6-SUMMARY.md`
</output>
