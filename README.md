# NetPulse MikroTik Control Plane

NetPulse is a dark, RouterOS-inspired control room for centralized MikroTik monitoring. The first release includes a responsive overview, device groups, router inventory, alarm center, seeded Super Admin workspace, and router detail drawer.

## Ubuntu 24.04 quick start

1. Install Python 3.11+, Node 18+, MongoDB, and Yarn.
2. Keep the existing environment values in `backend/.env` and `frontend/.env`.
3. From `/app`, run:

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cd ../frontend && yarn install
```

Run the two services using the project supervisor, or for a local preview:

```bash
# terminal 1
cd /app/backend && . .venv/bin/activate && uvicorn server:app --host 0.0.0.0 --port 8001
# terminal 2
cd /app/frontend && yarn start
```

Open the frontend preview. The backend reads only `MONGO_URL` and `DB_NAME` from `backend/.env`; the frontend reads only `REACT_APP_BACKEND_URL` from `frontend/.env`.

## Current integration status

The dashboard uses a realistic fallback dataset so it is usable before router credentials are entered. RouterOS API polling, encrypted credential persistence, WebSockets, PostgreSQL/Redis, and Telegram delivery are intentionally staged for the next integration phase. No router or Telegram secrets are stored in this repository.

Before connecting real devices, enable RouterOS API-SSL on port 8729 and restrict the service to this server's IP. Add real authentication before exposing the app outside a trusted network.

## Live RouterOS and backup configuration

The direct API layer uses fixed, named operations only; it does not accept arbitrary RouterOS commands. Prefer API-SSL on `8729`. The currently supplied `8728` mode is supported for a trusted private network only because credentials are unencrypted in transit.

Before saving a real router, add these server-only settings to the runtime environment (never the React `.env`):

```bash
export CREDENTIALS_FERNET_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export BACKUP_ROOT=/var/lib/netpulse/backups
export BACKUP_ENCRYPTION_KEY="replace-with-a-long-server-secret"
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=your-account@example.com
export SMTP_PASSWORD=your-google-app-password
export SMTP_FROM=your-account@example.com
```

The backup engine is designed to create an encrypted binary `.backup` and sanitized `.rsc` export, store them under the configured backup root, record history in MongoDB, and deliver both as SMTP attachments. The UI remains safely configuration-only until these values and a real router record are present.