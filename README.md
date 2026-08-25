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