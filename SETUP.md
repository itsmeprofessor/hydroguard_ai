# HydroGuard AI — Full Stack Setup Guide

Complete instructions to run HydroGuard AI with Docker backend and Flutter web frontend.

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker Desktop | Latest | All backend services |
| Flutter SDK | 3.41+ | Build Flutter web app |
| OpenSSL | Any | Generate self-signed SSL cert |

---

## Step 1 — Create `.env` file

Create `.env` in the project root (`D:\Programming\FYP\hydroguard_ai\.env`):

```env
# Required — generate a strong random key (min 32 chars)
JWT_SECRET_KEY=your-secret-key-min-32-chars-change-this

# Required
ADMIN_TOKEN=hydroguard-admin-token
POSTGRES_PASSWORD=hydroguard_pg_pass
REDIS_PASSWORD=hydroguard_redis_pass

# Optional — WeatherAPI key for live weather (free at weatherapi.com)
WEATHERAPI_KEY=your_weatherapi_key_here

# CORS
CORS_ORIGINS=http://localhost,http://localhost:80
```

Generate a strong `JWT_SECRET_KEY`:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 2 — Generate SSL Certificates (one-time)

nginx requires certs even for local dev:

```powershell
mkdir nginx\certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 `
  -keyout nginx\certs\privkey.pem `
  -out nginx\certs\fullchain.pem `
  -subj "/CN=localhost"
```

---

## Step 3 — Build the Flutter Web App

```powershell
cd frontend\citizen_flutter_app
flutter pub get
flutter build web --dart-define=API_BASE='' --release
cd ..\..
```

> `API_BASE=''` = same-origin mode. Flutter calls `/auth/login`, nginx proxies to the backend. **Required for Docker deployment.**

---

## Step 4 — Start the Full Stack

```powershell
docker compose up --build
```

First run builds the Python image (~3–4 min). Subsequent runs start in ~20 seconds.

**What starts:**

| Container | Role | Exposed Port |
|---|---|---|
| `hydroguard-db` | PostgreSQL 16 | 5432 (localhost only) |
| `hydroguard-redis` | Redis 7 | 6379 (localhost only) |
| `hydroguard-api` | FastAPI backend | **8000** |
| `hydroguard-nginx` | Reverse proxy + Flutter web | **80** (HTTP), **443** (HTTPS) |
| `hydroguard-backup` | Daily `pg_dump` | — |

---

## Step 5 — Verify All Containers Are Healthy

```powershell
docker ps
```

Wait until all show `(healthy)`:

```
hydroguard-api     Up (healthy)   0.0.0.0:8000->8000/tcp
hydroguard-nginx   Up             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
hydroguard-db      Up (healthy)   127.0.0.1:5432->5432/tcp
hydroguard-redis   Up (healthy)   127.0.0.1:6379->6379/tcp
```

---

## Step 6 — Create Your First User

**Option A — Register through the app:**

Open `http://localhost` and click **Create account** on the login screen.

**Option B — Register via API:**

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/auth/register" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"email":"admin@hydroguard.pk","username":"Admin","password":"your-password"}'
```

**Promote a user to ADMIN role:**

```powershell
docker exec -it hydroguard-db psql -U hydroguard -c `
  "UPDATE users SET role='ADMIN' WHERE email='admin@hydroguard.pk';"
```

---

## Step 7 — Access the App

| URL | What you get |
|---|---|
| `http://localhost` | Flutter web app — login screen |
| `http://localhost:8000/docs` | FastAPI Swagger UI (API explorer) |
| `http://localhost:8000/health` | Backend health status (JSON) |
| `http://localhost:8000/api/v2/cities/overview` | Live city HRI data |

**Role routing after login:**

| Role | Redirects to | Shell |
|---|---|---|
| `USER` | `/citizen/home` | Home / Forecast / Map / Learn / Settings |
| `ADMIN` | `/admin/dashboard` | Dashboard / HRI / Alerts / Map / More |

---

## Day-to-Day Operations

### Stop everything
```powershell
docker compose down
```

### Stop and wipe all data (fresh start)
```powershell
docker compose down -v
```

### Restart only the API (after a backend Python change)
```powershell
docker compose restart hydroguard-api
```

### Rebuild Flutter and deploy (no Docker restart needed)
```powershell
cd frontend\citizen_flutter_app
flutter build web --dart-define=API_BASE='' --release
# nginx reads build/web directly — just hard-refresh the browser (Ctrl+Shift+R)
cd ..\..
```

### View backend logs live
```powershell
docker compose logs -f hydroguard-api
```

### View nginx access logs
```powershell
docker compose logs -f nginx
```

### Run backend tests
```powershell
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Login spinner hangs forever | Browser cached HTTPS (HSTS) from port 443 visit | Use `http://localhost` (not `https://`) |
| Forecast screen loads for 10–15 seconds | WeatherAPI external call latency | Normal — spinner shows while loading |
| `JWT_SECRET_KEY is required` on startup | `.env` file missing or in wrong directory | Check `.env` exists in project root |
| `POSTGRES_PASSWORD is required` | Same as above | Same fix |
| Flutter app shows old version | Build cache | Run `flutter build web ...` + `Ctrl+Shift+R` in browser |
| `hydroguard-api` stays `starting` | DB or Redis not yet healthy | Wait ~30 seconds; `docker compose logs hydroguard-api` |
| nginx `502 Bad Gateway` | API container not ready | Check `docker ps` — wait for `(healthy)` on `hydroguard-api` |
| Admin More shows "Degraded" | WebSocket not yet connected | Wait 5–10 seconds; page refreshes automatically |

---

## Architecture Overview

```
Browser
  │
  ▼
nginx (port 80/443)
  ├── /          → Flutter web app  (frontend/citizen_flutter_app/build/web/)
  ├── /auth/*    → FastAPI backend  (hydroguard-api:8000)
  ├── /api/*     → FastAPI backend
  ├── /health    → FastAPI backend
  └── /ws/*      → FastAPI WebSocket (hydroguard-api:8000)
          │
          ▼
    FastAPI (Python)
          │
          ├── PostgreSQL 16  (user accounts, anomaly records)
          └── Redis 7        (rate limiting, WS connection state)
```

**ML Models** are stored in `backend/saved_models/city_models/` and loaded at startup. 6 cities trained: Islamabad, Karachi, Lahore, Peshawar, Quetta, Gilgit.

---

## Test Accounts

| Email | Password | Role |
|---|---|---|
| `zain@gmail.com` | `zain1234` | ADMIN |
| `test@hydroguard.pk` | `hydroguard123` | USER |

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | **Yes** | — | HS256 signing key (min 32 chars) |
| `ADMIN_TOKEN` | **Yes** | — | Legacy X-Admin-Token header value |
| `POSTGRES_PASSWORD` | **Yes** | — | PostgreSQL password |
| `REDIS_PASSWORD` | **Yes** | — | Redis auth password |
| `WEATHERAPI_KEY` | No | — | WeatherAPI.com key for live weather |
| `CORS_ORIGINS` | No | `http://localhost,...` | Comma-separated allowed origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | JWT refresh token lifetime |
| `API_PORT` | No | `8000` | FastAPI exposed port |
| `DEBUG` | No | `false` | Enable debug logging |
