# TA Platform deployment

For the BRIDGE web tutor and teacher panel, read `BRIDGE_HANDOVER.md` before deploying. The source archive includes a compiled `frontend/dist` so the supplied Nginx configuration can serve the new pages. Set the required BRIDGE model service endpoints in `.env` and review source chunks before activating a module.

## Local smoke test

```powershell
Copy-Item .env.example .env
# Set DB_PASSWORD, JWT_SECRET and ROBOT_AUTH_KEYS. Set BRIDGE model URLs and model names for BRIDGE.
docker compose up -d --build
docker compose ps
```

The application is served at `http://localhost`. API documentation is at
`/api/docs`. Create the first teacher account from the backend container:

```bash
docker compose exec backend python -m app.create_teacher \
  --student-id T00001 --phone 13800000001 \
  --password 'use-a-strong-password' --name 'Course lead'
```

## Alibaba Cloud ECS

1. Use Ubuntu 22.04 on ECS. Restrict security group port 22 to your fixed IP;
   expose only 80 and 443 publicly.
2. Install Docker and Git, clone this repository under `/opt/ta-platform`, and
   create `.env` from `.env.example`.
3. Set a strong `DB_PASSWORD`, `JWT_SECRET`, `ROBOT_AUTH_KEYS`; configure the
   BRIDGE internal model endpoints and only the legacy services you use.
   Never commit `.env`.
4. Point an A record for the domain to the ECS public IP and set
   `CORS_ORIGINS=https://your-domain.example`.
5. Run `docker compose up -d --build`. Nginx proxies `/api` and `/ws` to the
   backend and serves `frontend/dist`.
6. Install a TLS certificate with Certbot, mount `/etc/letsencrypt` into the
   Nginx container, then restart Nginx.

For a small first deployment, PostgreSQL and Redis run as Compose services with
named volumes. Move them to Alibaba RDS PostgreSQL and Redis/Tair later by
changing `DATABASE_URL` and `REDIS_URL`; no application code changes are needed.

## Backups and operations

```bash
mkdir -p /opt/backups
docker compose exec -T postgres pg_dump -U ta_admin ta_platform \
  | gzip > /opt/backups/ta_platform_$(date +%Y%m%d).sql.gz
docker compose logs -f backend
docker compose ps
```

Schedule the backup command daily and copy the resulting files to OSS. Rotate
old backups after 30 days. Check `/api/health` after every deployment.

## Robot client

On Raspberry Pi, install `robot-client/requirements.txt` and configure:

```bash
export ROBOT_SERVER_URL=wss://your-domain.example
export ROBOT_ID=TA-Robot-01
export ROBOT_AUTH_KEY='the-secret-from-ROBOT_AUTH_KEYS'
export ROBOT_VOICE_ENABLED=true
python main.py
```

Without microphone hardware or an ASR gateway, leave voice disabled and use the
simulator telemetry path. The server still accepts a `voice_question` message
with a `text` field for end-to-end testing.
