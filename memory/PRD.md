# NetPulse — Centralized MikroTik Management & Monitoring

## Original problem statement
Self-hosted, multi-router MikroTik control plane (FastAPI + React + MongoDB) using the RouterOS native API (port 8728/8729, no WebFig iframe). Winbox-like per-router workspace, groups/tenants, users & roles, Telegram alerts, backups, easy installation.

## User decisions (verbatim-faithful)
- Keep MongoDB (PostgreSQL/Redis deferred).
- Writes to RouterOS allowed from the workspace (add/edit/remove like Winbox); if the MikroTik user is read-only show popup "not enough permission".
- Auth: email+password (JWT) **and** Google (Emergent-managed). Super Admin seeded; other roles fully custom (per-module none/read/write + explicit device groups).
- Each user MUST enter their own MikroTik credentials in *My settings*; shared routers only expose name + IP (owner/Super Admin may still use stored credentials).
- Groups are hierarchical (parent → child); access is explicit per group (no inheritance).
- Multiple workspaces (tenants) with rename/create/delete.
- Telegram bot token + chat ID stored **per role** (encrypted with CREDENTIALS_FERNET_KEY).
- Backups: `.rsc` snapshot via API only (no FTP), stored in Emergent Object Storage.
- Terminal menu in router workspace.
- One-shot installation (Docker Compose + install.sh).

## Architecture
- `backend/core.py` (db, MODULES, Fernet), `auth.py` (JWT + Google session, /api/auth/*), `admin.py` (workspaces, groups tree, roles, users, /groups/{id}/access), `server.py` (routers, resources, config writes, terminal, backups, Telegram per role, alarms, audit, legacy migration), `storage.py` (object storage).
- Frontend: `src/App.js` shell + routes, `src/auth/AuthContext.jsx`, `src/lib/api.js` (Bearer + X-Workspace), `src/lib/ros.js`, `src/pages/*` (Login, Users, Roles, Workspaces, Groups(+GroupSettings), MySettings, NotificationsPanel), `src/components/*` (RouterWorkspace, ConfigEditor, TerminalPanel, BackupsPanel, Modal, Status).
- Deploy: `docker-compose.yml`, `deploy/Dockerfile.*`, `deploy/nginx.conf`, `install.sh`, `README-INSTALL.md`.
- RouterOS pools keyed `router:user`; HTTP 428 = user must set own MikroTik credentials; 403 "not enough permission" = RouterOS policy.

## Implemented (chronological)
- Read-only Winbox views, sidebar routing fix, Add/Edit router, offline-status fix, pooled sessions (iter 5–10).
- 2026-09-26: Groups CRUD + per-view heading buttons (iter 9, 100%). Edit router (iter 10, 100%).
- 2026-09-26: Auth (JWT + Google), Users/Roles/Workspaces, hierarchical groups, per-user ROS credentials, RouterOS add/set/remove with permission popup, Terminal, .rsc backups to object storage, Telegram per role, group settings modal, audit log, Docker install (iter 11: backend 27/28 → lockout fixed, frontend 100%).

## Credentials
See `/app/memory/test_credentials.md`. A Google account (andrafajarramadhan1999@gmail.com) signed in and currently has Viewer role / no workspace — promote via Users.

## Backlog
- P0: automatic alarm evaluation (CPU threshold / interface change / unreachable) → dispatch to role Telegram; scheduled backups.
- P1: WebSocket realtime, traffic graphs from RouterOS (replace sample chart), drag-and-drop dashboard widgets, more Winbox menus (bridge, VLAN, hotspot, wireless config).
- P2: PostgreSQL/Redis migration (deferred), SMTP delivery of backups, workspace-level Telegram override.
