# NetPulse — Centralized MikroTik & Multi-Vendor Management / Monitoring

## Original problem statement
Self-hosted, multi-device control plane (FastAPI + React + MongoDB) using the RouterOS native API (8728/8729, no WebFig iframe). Winbox-like per-device workspace, groups/tenants, users & roles, Telegram alerts per role, backups, syslog, public NOC display, easy installation.

## User decisions (faithful)
- Keep MongoDB (PostgreSQL/Redis deferred).
- RouterOS writes from the workspace; read-only MikroTik user → popup "not enough permission".
- Auth: email+password (JWT) **and** Google (Emergent-managed). Super Admin seeded; custom roles per module + explicit device groups (no group inheritance).
- Each user enters their own MikroTik credentials in *My settings*; shared devices expose only name (+IP for owner/Super Admin).
- Telegram bot token + chat ID **per role** (Fernet-encrypted); alarms go to every role whose groups include the device's group.
- Terminal: **both** real SSH and Telnet (xterm.js over WebSocket, per-device ports, credentials from My settings) **plus** the API command bridge as fallback. Non-MikroTik vendors must also get SSH/Telnet.
- Config forms must use **dropdowns read live from the device** (interface, bridge, pool, profile, server…), never manual typing.
- API port free-form + **SSL checkbox** (api-ssl), SSH/Telnet ports configurable.
- Alarm interface watch per device: all / ethernet+sfp / pick specific interfaces / off.
- Syslog server (UDP 514) for MikroTik and other devices, categories + alarm rules (e.g. login failure) → role Telegram, 30-day retention.
- Terminology: “routers” → **devices**.
- Public NOC display page per workspace **without login** (read only); clicking a device requires sign-in.
- Overview must be customisable: **multiple board tabs**, selectable widgets, group/device scope.
- Phase 3 (agreed, pending): multi-vendor devices (MikroTik full features; Huawei/Juniper/Cisco/Other = ping + SNMP v2c), ping 60 s, **SNMP polling 1 min**, interface + CPU only, 30-day retention, SSH/Telnet for those vendors too.
- Phase 4 (agreed, pending): free-form topology map, links created manually by picking SNMP-discovered interfaces on both ends.
- One-shot install (Docker Compose + install.sh); syslog 514/udp published there.

## Architecture
`backend/core.py` (db, MODULES incl. `syslog`, Fernet) · `auth.py` (JWT + Google, lockout by email) · `admin.py` (workspaces, group tree, roles, users) · `server.py` (devices CRUD, RouterOS resources + writes, pooled sessions, backups, Telegram per role, `deliver_alarm`, audit, API terminal) · `engine.py` (live traffic, alarm-interface watch, alarm settings, backup schedules, cron webhooks, port-check) · `sshterm.py` (SSH/Telnet WebSocket bridge) · `syslogd.py` (UDP collector, rules) · `display.py` (public board) · `boards.py` (dashboards) · `storage.py`.
Frontend: `App.js` shell + board tabs, `pages/*` (Login, Users, Roles, Workspaces + PublicDisplay, Groups, MySettings, NotificationsPanel, AlarmSettings, SyslogPage, DisplayBoard), `components/*` (RouterWorkspace, ConfigEditor with live pick-lists, TrafficPanel, SshTerminal, TerminalPanel, BackupsPanel + schedule, AlarmWatchPanel, DashboardTabs + SyslogWidget), `lib/ros.js` (Winbox menu, columns, editable fields, reference sources).
Schedules: `.emergent/crons.yml` → `/api/cron/alarm-scan` & `/api/cron/backup-scan` every 15 min (Bearer `WEBHOOK_CRON_SECRET`).

## Implemented (chronological)
- iter 5–10: read-only Winbox views, sidebar routing, add/edit device, offline-status fix, pooled RouterOS sessions, groups CRUD.
- 2026-09-26 (iter 11): auth + RBAC, users/roles/workspaces, hierarchical groups, per-user ROS credentials, RouterOS add/set/remove, API terminal, .rsc backups to object storage, Telegram per role, audit, Docker install; login lockout 429 fixed.
- 2026-09-26 (iter 12 — 32 pass/1 skip): Winbox menus Bridge/Bridge Ports/VLAN/Wireless/Wireless Security/Registration/IP Pools/Hotspot(5); **live bandwidth** from RouterOS counters (overview chart + per-device Traffic panel, uplink-only totals); **scheduled .rsc backups** (daily/weekly, keep N) via cron; **automatic alarm engine** (CPU, interface up/down, unreachable → role Telegram, throttled); **reference dropdowns** in every config form; real **SSH terminal** + per-device ssh_port.
- 2026-09-26 (iter 13 — 27 pass/1 skip): **Telnet terminal** (negotiation + auto-login) and control frames for true session state; **Check ports** diagnostic (shows NetPulse outbound IP + api/ssh/telnet/winbox reachability); **alarm interface watch modes** per device; **syslog server** UDP 514 with categories, filters, rules → Telegram, 30-day TTL, test injector; **public NOC display** per workspace (token link, IP hiding, rotate/disable) at `/display/{token}`; **custom dashboards** (multi-tab boards, widget picker incl. syslog widget, group/device scope); Routers→**Devices** rename; API port free-form + **api-ssl checkbox**; xterm upgraded (@xterm/xterm 6) with guarded teardown.

## Verified facts about the live device
`mr-65920574` IDC MONITORING 103.102.13.4 — API 8728 open, **SSH 2122 works** (real shell verified), telnet 1623 filtered from the app's egress IP. Remote ports must allow the NetPulse server IP (shown by Check ports), not the operator's PC.

## Backlog
- **P0 Phase 3**: device_type (MikroTik/Huawei/Juniper/Cisco/Other), ICMP ping monitor (60 s), SNMP v2c poller (1 min: interface counters + CPU, 30-day retention), SSH/Telnet terminals for non-MikroTik, vendor-aware UI gating.
- **P0 Phase 4**: topology canvas (free placement, saved positions), manual links picking SNMP-discovered interfaces, link colour by status/traffic; embed the map in the public display board.
- P1: Telegram delivery for syslog rules verified with a real bot; WebSocket push instead of polling; board widget drag-and-drop; per-board public display selection; TCP syslog.
- P2: PostgreSQL/Redis migration, SMTP backup delivery, workspace-level Telegram override, native MikroTik graphs.
