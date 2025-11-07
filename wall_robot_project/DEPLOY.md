# Deployment Guide

This document describes recommended production deployment steps for the Wall-Finishing Robot Control API.

## Overview

- The app is a FastAPI ASGI application (`robot_control_system:app`).
- SQLite is used for storage; for small deployments this is sufficient, but ensure the underlying disk is durable.
- The app supports optional Redis-backed rate limiting and optional MQTT notifications.

## Reverse proxy and TLS (nginx)

A common and simple approach is to place `nginx` in front of the app (gunicorn/uvicorn workers). Example `nginx` server block:

```
server {
    listen 80;
    server_name your.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your.example.com;

    ssl_certificate /etc/letsencrypt/live/your.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your.example.com/privkey.pem;

    location /static/ {
        alias /path/to/your/repo/static/;
        expires 1d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}
```

Obtain TLS certs via Let's Encrypt / certbot and configure auto-renewal.

## Running the app

Production: use `uvicorn` managed by a process supervisor (systemd) or container orchestration.

Example systemd unit (simple):

```
[Unit]
Description=Wall Robot API
After=network.target

[Service]
User=robot
Group=robot
WorkingDirectory=/srv/wall_robot
Environment=PYTHONUNBUFFERED=1
Environment=DB_PATH=/srv/wall_robot/robot_trajectories.db
ExecStart=/usr/bin/env uvicorn robot_control_system:app \
    --host 127.0.0.1 --port 8000 --workers 4 --log-level info
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Environment variables

- `DB_PATH` or `db_path` via `.env` — path to SQLite file (ensure permissions are correct).
- `API_KEY` (optional) — if set, write endpoints require this key.
- `JWT_SECRET` (optional) — used to issue/verify tokens.
- `REDIS_URL` (optional) — enable Redis-backed rate limiter (e.g., `redis://127.0.0.1:6379/0`).
- `MQTT_ENABLED=true` and `MQTT_HOST/MQTT_PORT/MQTT_TOPIC` — enable MQTT publish for completed trajectories.

## SQLite PRAGMA tuning recommendations

Tune PRAGMA values based on workload and disk durability requirements. Example production-lean settings (write-heavy):

- PRAGMA journal_mode = WAL
- PRAGMA synchronous = NORMAL  (or FULL for extra durability)
- PRAGMA cache_size = -64000   (64MB page cache)
- PRAGMA temp_store = MEMORY
- PRAGMA mmap_size = 0 (or >0 if OS supports it and DB file is large)

Place the DB on a fast filesystem (SSD) and ensure periodic backups.

## Backup & migration

- Regular backups: copy the SQLite file while the app is stopped or rely on WAL checkpoint to ensure consistency.
- Migration script: `migrations/remove_legacy_column.py` (if present) rewrites schema to drop legacy JSON columns.

## Scaling notes

- SQLite is great for single-node deployments. If you need horizontal scaling, migrate to a client/server DB (Postgres recommended).
- Use Redis for distributed rate limits and caching.
- Offload heavy path planning to a worker queue (Celery/RQ) if planning becomes CPU-bound.

## Security

- Use a reverse proxy (nginx) with TLS termination.
- Run the app under a dedicated user with limited permissions.
- Protect secrets via environment variables or a secret manager (Vault/Cloud Secret Manager).

## Observability

- Forward logs to a central aggregator (Filebeat/Fluentd) or use cloud-native logging.
- Monitor disk usage of the DB file.
- Run health checks (the `/health` endpoint) via your orchestrator.

## CI / Integration tests

- The GitHub Actions workflow should bring up Redis and Mosquitto services for integration tests. If using external services, provide URLs via `REDIS_URL`, `MQTT_HOST`, and `MQTT_PORT`.

## Docker Compose and migration

For local development and to mirror CI, use the included `docker-compose.yml` and `docker-compose.override.yml`.

Bring up the stack:

```
docker compose up --build
```

This will start the `app`, `redis`, and `mosquitto` services. The app stores its DB in the `data` named volume (mapped to `./data` when using the override file).

Migration (safe) guide:

1. Stop the app so the DB is not actively written, or ensure you have a consistent backup.
2. Create a manual backup:

```
copy .\robot_trajectories.db .\robot_trajectories.db.manual.bak
```

3. Run the helper (PowerShell):

```
.\scripts\run_migration.ps1 -DbPath .\robot_trajectories.db
```

This script makes an additional backup and then performs a safe table rewrite to remove the legacy `trajectory_points` JSON column if present. Inspect the backup before deleting.


## Troubleshooting

- If you see database locked errors, check for long-running VACUUM or concurrent writes. WAL mode reduces contention.
- If MQTT publish fails, confirm broker is reachable and credentials (if any) are correct.


---

If you'd like, I can also generate a sample `docker-compose.yml` that runs the app together with Redis and Mosquitto for a simple dev/test environment.
