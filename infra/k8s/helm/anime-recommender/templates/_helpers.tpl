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

{{/* Fully-qualified image ref for a component: registry/repository:tag */}}
{{- define "anime.image" -}}
{{- $reg := .root.Values.image.registry -}}
{{- printf "%s/%s:%s" $reg .img.repository (.img.tag | toString) -}}
{{- end -}}
