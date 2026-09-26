# NetPulse — Installation

Self-hosted MikroTik control plane (FastAPI + React + MongoDB). Everything ships in Docker, so you do **not** install Python, Node or MongoDB by hand.

## One-shot install (Ubuntu 22.04 / 24.04, Debian 12)

```bash
git clone <your-repo-url> netpulse && cd netpulse
chmod +x install.sh
./install.sh
```

The script will:
1. Install Docker + Compose plugin if they are missing.
2. Generate `.env` with random secrets (`CREDENTIALS_FERNET_KEY`, `JWT_SECRET`, Super Admin password).
3. Build the backend and frontend images and start `mongo`, `backend`, `frontend`.
4. Print the URL (default port **8080**) and the Super Admin credentials.

Optional environment variables before running the script:

| Variable | Purpose |
|---|---|
| `NETPULSE_PORT` | Public port for the web UI (default 8080) |
| `ADMIN_EMAIL` | Super Admin email (default `admin@netpulse.local`) |
| `EMERGENT_LLM_KEY` | Enables object storage for `.rsc` backups |

## Day-to-day

```bash
docker compose ps                 # status
docker compose logs -f backend    # backend logs
docker compose up -d --build      # rebuild after git pull
docker compose down               # stop (data is kept in the mongo_data volume)
```

## Requirements on the network
- The server must reach every MikroTik on its **API port** (8728 plaintext or 8729 api-ssl).
- Each user enters **their own** MikroTik username/password in *My settings*; shared routers only expose name + IP.
- For HTTPS put nginx/Caddy/Traefik in front of port 8080 (cookies are marked `Secure`, Bearer tokens work on plain HTTP too).
