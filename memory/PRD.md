# NetPulse MikroTik Control Plane PRD

## Original problem statement
Build a full-stack, responsive web application for Centralized Multi-MikroTik Management & Real-Time Monitoring System, self-hosted on a local/cloud server as a web-based alternative to Winbox with persistent connections, multi-tenancy, and central monitoring. Required direction: React/Tailwind/Lucide/Shadcn frontend, FastAPI backend, RouterOS API, live monitoring, threshold alarms, Telegram alerts, RBAC, easy Ubuntu 24.04 installation.

## Product decisions
- Persona: network operator or partner administrator managing several MikroTik routers.
- First release prioritizes monitoring dashboard, device/group management, RBAC screens, alarms, and router detail views.
- Real router connectivity is the target; no credentials were supplied during this build, so the preview uses safe demo data.
- Seeded Super Admin screens are used now; full authentication is deferred.
- Existing FastAPI + MongoDB environment is retained to keep installation simple for a beginner.

## Implemented — 2026-08-25
- Built NetPulse RouterOS-inspired dark monitoring workspace with responsive sidebar navigation.
- Added fleet metrics, aggregate traffic chart, alarm center, router table, search, group filters, status badges, and mobile navigation.
- Added router detail drawer with Interfaces, Resources, and Logs tabs plus connection/console action feedback.
- Added `/api/monitoring/overview` and `/api/health` endpoints with MongoDB-safe health handling.
- Added Ubuntu 24.04 setup notes and integration boundaries in the root README.

## Remaining backlog
- P0: connect RouterOS API-SSL polling with per-router credential encryption and connection test.
- P0: add real JWT authentication and tenant-scoped RBAC enforcement.
- P1: add PostgreSQL/Redis deployment profile or document the migration path from the easy MongoDB starter.
- P1: add Telegram Bot API secrets, alarm rule persistence, deduplication, and recovery notifications.
- P1: add WebSocket live updates and native RouterOS graph fetching.
- P2: add drag-and-drop widget layouts, write-protected configuration commands, and audit history.

## Next tasks
1. Collect RouterOS API-SSL endpoint and Telegram bot credentials.
2. Implement encrypted secret storage and a single-worker polling service.
3. Replace fallback overview values with real metrics while retaining an offline/demo mode.