# Observability (Grafana/Prometheus/Loki/Tempo) for photo-booth

## What this does
This repo can be monitored by the shared `observability-platform` stack running in Docker Desktop.

Baseline monitoring uses the observability platform’s **blackbox-exporter** to probe HTTP health endpoints.

**Container logs (no app code):** **Promtail** sends all container stdout/stderr on the host to Loki. In Grafana → **Logs + Traces Correlation**, use LogQL like `{container=~"backend"}` (or your compose service name).

## Prerequisites
1. Deploy `observability-platform` so the shared Docker network `obs_net` exists.
2. Observability platform must include blackbox targets for:
   - `http://backend:8000/health`

## Run-time changes to this repo
`photo-booth/docker-compose.yml` now attaches the **backend** service to `obs_net`
so blackbox-exporter can reach it by container name (`backend`).

## Expected endpoints
- Backend health: `GET /health`

## How to verify
1. Start `observability-platform` stack (Grafana defaults to `http://localhost:23001`; see `observability-platform/docs/ARCHITECTURE.md`).
2. Start photo-booth (via `docker compose up` in this repo). Default host ports are **`3200`** (web) and **`3201`** (API); override via `.env` or `.env.compose.override.example` if needed. See `observability-platform/docs/ARCHITECTURE.md`.
3. In Grafana, open **Service Health, Latency, Error Rate** and look for `photo-booth`.

## Next step (optional, for traces/logs)
If you add OpenTelemetry instrumentation, you can export to:
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`
- `OTEL_RESOURCE_ATTRIBUTES=tenant.id=<tenant>,service.namespace=photo-booth`

