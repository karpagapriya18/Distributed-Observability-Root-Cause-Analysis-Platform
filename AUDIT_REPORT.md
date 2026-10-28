# Audit and patch report

## Confirmed in original ZIP
- Existing FastAPI applications: ingestion, traces, logs, metrics, RCA, query, order, payment, notification.
- Existing React screens for overview, traces, dependencies, logs, metrics, RCA and alerts.
- Original Compose launched only MySQL and RabbitMQ; no API gateway implementation.
- Existing frontend queried backend ports directly; query client used stale metrics/logs ports.
- Existing metrics consumer persists alerts for every violating sample without grouping; sample table has no event_id idempotency constraint.
- Trace processing reads ingestion database models directly, violating strict service-owned data isolation.
- Original pytest discovery attempted to import publisher scripts and failed due to missing `pika` and DB environment variables.

## Added or changed
- Gateway with stable /backend/{service}/... routing, basic /api/v1 read proxy paths, correlation IDs, bounded timeout, 502/504 structured errors.
- Dockerfile, Compose service definitions, dev DB initialization, frontend Docker/Nginx, Vite gateway proxy.
- Frontend URLs switched to gateway proxy while preserving components.
- Query service URLs made environment-configurable.
- Missing Python dependencies added, pytest discovery restricted to tests/, gateway smoke tests added.

## Not yet implemented / not certified
- Full versioned REST contracts and ingestion POST/batch APIs are not present in original source.
- Complete trace/log/metrics consumers with idempotency, DLQ, retry and out-of-order policies need integration tests.
- Metric alert deduplication, time-bucketed percentile aggregation, auth/RBAC, request-size limits, RCA cross-service evidence and service-owned DB access need additional work.
- No Docker daemon or MySQL/RabbitMQ services are available in the audit runtime; Compose runtime and end-to-end acceptance cannot be verified here.
- `create_all` is a local-development bootstrap, NOT an Alembic migration strategy. Existing MySQL volumes require manual database creation or migrations; mysql-init.sql only runs on a new volume. Never run `docker compose down -v` on data you need.
- `mysql` root access is used for development convenience; configure dedicated per-service database users before production.
- Frontend pages display backend data but actual backend-generated telemetry across the full order→payment→notification path remains to be validated in a running stack.

## Local verification
1. Copy `.env.example` to `.env` and set secrets; preserve your existing `.env` if already configured.
2. If reusing MySQL data, create the seven schemas from `docker/mysql-init.sql` manually; do not remove volumes.
3. `docker compose config` then `docker compose up --build -d`.
4. `docker compose ps` and `docker compose logs --tail=80 db-init gateway ingestion metrics-consumer`.
5. Open `http://localhost:5173` and `http://localhost:8000/docs`.
6. `python -m pytest tests -q` in an environment with requirements installed.

## Important caveat
Gateway `/api/v1/...` routes are compatibility proxies, not a claim that every assignment endpoint is implemented. Validate upstream route contracts individually.

### Test results from this audit environment
- PASS: `python -m compileall -q services docker`.
- PASS: `python -m pytest tests -q` — 6 passed (three preexisting alert unit tests, three new gateway smoke tests).
- FAIL before pytest configuration fix: 4 collection errors (`pika` unavailable in the audit Python environment, DB URL unavailable during script import).
- NOT RUN: Docker Compose runtime, MySQL/RabbitMQ connectivity, real service-to-service E2E (Docker CLI/daemon not installed here).
- NOT RUN: React production build (`npm ci --offline` failed because the npm cache lacks `zustand-4.5.7.tgz`).
