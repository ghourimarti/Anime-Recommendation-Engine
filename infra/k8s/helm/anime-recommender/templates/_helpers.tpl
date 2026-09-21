{{/* Common name + label helpers — single source of truth for selectors. */}}

{{- define "anime.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "anime.labels" -}}
app.kubernetes.io/name: {{ include "anime.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/* Per-component selector labels (stable across upgrades — never add version here). */}}
{{- define "anime.selectorLabels" -}}
app.kubernetes.io/name: {{ include "anime.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Fully-qualified image ref for a component.

Resolution order:
  1. .img.digest        -> [registry/]repository@sha256:...  (same bytes everywhere)
  2. .img.tag           -> [registry/]repository:tag
  3. .Values.image.tag  -> one tag for every component (what CI sets)
  4. .Chart.AppVersion  -> G4: chart version == app version

Why the fallback exists: an empty tag used to render "repository:" — a trailing
colon, a malformed reference. helm exits 0 on that and kubeconform accepts it
(it is only a string); it fails when the kubelet pulls it, inside the cluster.
values-prod.yaml shipped exactly that, so a prod install that missed the --set
would have failed at pull time.

An empty registry is allowed and means no prefix: kind loads images straight
onto the node, so there is nothing to pull from.
*/}}
{{- define "anime.image" -}}
{{- $reg := .root.Values.image.registry | default "" -}}
{{- $repo := required "image.<component>.repository is required" .img.repository -}}
{{- $ref := $repo -}}
{{- if $reg }}{{ $ref = printf "%s/%s" $reg $repo }}{{ end -}}
{{- if .img.digest -}}
{{- printf "%s@%s" $ref .img.digest -}}
{{- else -}}
{{- $tag := .img.tag | default .root.Values.image.tag | default .root.Chart.AppVersion | toString -}}
{{- if not $tag }}{{ fail "image tag resolved empty: set image.tag, image.<component>.tag, or appVersion in Chart.yaml" }}{{ end -}}
{{- printf "%s:%s" $ref $tag -}}
{{- end -}}
{{- end -}}

{{/*
The api pod template, shared by api-rollout.yaml and api-deployment.yaml.

One definition so the two cannot drift: the rollout.enabled toggle changes the
delivery strategy and nothing else. A copy of the pod spec in each file would
eventually differ in a probe, a limit or an env var — and the canary would be
testing something other than what the Deployment runs.
*/}}
{{- define "anime.api.podTemplate" -}}
metadata:
  annotations:
    # See the note in web.yaml — rolls pods on ConfigMap change (P7.3).
    checksum/config: {{ include (print .Template.BasePath "/configmap.yaml") . | sha256sum }}
  labels:
    {{- include "anime.selectorLabels" . | nindent 4 }}
    component: api
    app: {{ include "anime.name" . }}-api
spec:
  serviceAccountName: {{ .Values.serviceAccount.api.name }}
  # Keep replicas on different nodes. The default scheduler spreads as a
  # preference, not a constraint — MEASURED in P7.5: after one node drain both
  # api replicas ended up on the same worker, where a single node failure would
  # have taken the whole api down.
  #
  # ScheduleAnyway, not DoNotSchedule: on a cluster with fewer schedulable nodes
  # than replicas, DoNotSchedule leaves pods Pending forever — trading an
  # availability risk for a guaranteed outage.
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: kubernetes.io/hostname
      whenUnsatisfiable: ScheduleAnyway
      labelSelector:
        matchLabels:
          {{- include "anime.selectorLabels" . | nindent 10 }}
          component: api
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    seccompProfile: { type: RuntimeDefault }
  containers:
    - name: api
      image: {{ include "anime.image" (dict "root" . "img" .Values.image.api) | quote }}
      imagePullPolicy: {{ .Values.image.pullPolicy }}
      ports:
        - containerPort: {{ .Values.api.port }}
      envFrom:
        - configMapRef: { name: {{ include "anime.name" . }}-config }
        - secretRef: { name: {{ .Values.externalSecrets.targetName }} }
      # Liveness = process up (no deps); readiness = can serve (checks DB) — the
      # K8s distinction the api's /health vs /ready endpoints implement.
      # preStop closes the endpoint-propagation race. Deleting a pod sends SIGTERM
      # and begins endpoint removal CONCURRENTLY; endpoint removal then has to
      # reach kube-proxy on every node. uvicorn exits on SIGTERM long before that
      # finishes, so kube-proxy keeps routing to a dead pod and those requests get
      # connection-refused.
      #
      # MEASURED (P7.5, before this hook): pod-kill dropped 1/119 requests and a
      # rollout-restart dropped 3/176 — as URLError, i.e. connection-level, not
      # HTTP. The sleep keeps the container serving while the removal propagates;
      # SIGTERM only arrives after preStop returns.
      #
      # 10s < terminationGracePeriodSeconds (30) on purpose: the grace period must
      # cover preStop PLUS the app's own shutdown, or the kubelet SIGKILLs mid-drain.
      lifecycle:
        preStop:
          exec:
            command: ["python", "-c", "import time; time.sleep(10)"]
      # startupProbe gates the other two: neither liveness nor readiness runs until
      # it succeeds. That decouples "slow to start" from "hung", which one probe
      # cannot express — without it, livenessProbe.initialDelaySeconds has to be
      # sized for the worst cold start, which then delays detection of a genuinely
      # dead process by the same amount.
      #
      # 5s x 30 = 150s budget. MEASURED (P7.4): container start -> Ready was 10.0s
      # on a warm node, and that was the readiness initialDelay, so real startup is
      # under 10s. The headroom is for a cold, loaded node pulling a reranker, not
      # for the normal case.
      startupProbe:
        httpGet: { path: /health, port: {{ .Values.api.port }} }
        periodSeconds: 5
        failureThreshold: 30
        timeoutSeconds: 3
      # initialDelaySeconds intentionally absent on both below: the startupProbe
      # already holds them off, so an extra delay only slows failure detection.
      livenessProbe:
        httpGet: { path: /health, port: {{ .Values.api.port }} }
        periodSeconds: 15
      readinessProbe:
        httpGet: { path: /ready, port: {{ .Values.api.port }} }
        periodSeconds: 10
      resources: {{- toYaml .Values.api.resources | nindent 8 }}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: { drop: ["ALL"] }
{{- end -}}
