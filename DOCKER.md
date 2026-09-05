# Production Docker Deployment Guide

This guide describes how to deploy the entire **Lenny Growth Assistant** system using Docker and Docker Compose.

---

## Architecture Overview

```
                                   [ Browser ]
                                        │
                         ┌──────────────┴──────────────┐
                         │  http://localhost:3000      │  http://localhost:8000
                         ▼                             ▼
                ┌─────────────────┐           ┌─────────────────┐
                │ lenny-frontend  │──proxy───▶│  lenny-backend  │
                │    (Next.js)    │           │    (FastAPI)    │
                └─────────────────┘           └─────────────────┘
                         │                             │
                         │      [ lenny-network ]      │
                         │                             ▼
                         │                    ┌─────────────────┐
                         │                    │ lenny-postgres  │
                         │                    │(pgvector:pg16)  │
                         │                    └─────────────────┘
                         │                             │
                         │                             ▼
                         └───────────────▶ [ postgres_data volume ]
```

The system comprises three coordinated containers connected over an internal bridge network (`lenny-network`):
1. **`lenny-postgres`**: PostgreSQL 16 database with the `pgvector` extension and persistent storage volume (`postgres_data`).
2. **`lenny-backend`**: FastAPI Python 3.12 application exposing API endpoints on port `8000`, equipped with health checks, structured logging, and automated database table initialization.
3. **`lenny-frontend`**: Next.js 15 production container serving the modern AI SaaS web application on port `3000`.

---

## Prerequisites

- **Docker Desktop** (version 24.0+) or **Docker Engine** with the `docker-compose-plugin`
- **Host Ollama Instance** (optional for local models):
  If using local inference, ensure Ollama is installed and running on your host machine with models pulled:
  ```bash
  ollama pull llama3.2:3b
  ollama pull nomic-embed-text
  ```
- **OpenRouter API Key** (optional for Cloud Claude model):
  Get a key from [openrouter.ai](https://openrouter.ai/).

---

## Quick Start (One-Command Launch)

### 1. Clone & Configure Environment

```bash
git clone <repo-url>
cd lenny-growth-assistant

# Create .env from template
cp .env.example .env
```

Edit `.env` to supply your credentials:
```ini
OPENROUTER_API_KEY=sk-or-v1-your-key-here
CLOUD_MODEL=anthropic/claude-sonnet-4
LLM_PROVIDER=cloud
FALLBACK_TO_LOCAL=true
```

### 2. Build and Start All Containers

Run the single command:
```bash
docker-compose up --build
```

To run in detached background mode:
```bash
docker-compose up --build -d
```

### 3. Verify Container Status & Health

Check that all three containers report `healthy`:
```bash
docker-compose ps
```

Expected output:
```
NAME             IMAGE                  COMMAND                  SERVICE      STATUS                    PORTS
lenny-backend    lenny-backend:latest   "uvicorn app.main:ap…"   backend      Up (healthy)              0.0.0.0:8000->8000/tcp
lenny-frontend   lenny-frontend:latest  "docker-entrypoint.s…"   frontend     Up (healthy)              0.0.0.0:3000->3000/tcp
lenny-postgres   pgvector/pgvector:pg16 "docker-entrypoint.s…"   postgres     Up (healthy)              0.0.0.0:5432->5432/tcp
```

### 4. Access the Application

- **Web Application**: Open [http://localhost:3000](http://localhost:3000)
- **FastAPI Documentation**: Open [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Health Check**: Open [http://localhost:8000/health](http://localhost:8000/health)
- **Frontend Health Check**: Open [http://localhost:3000/api/health](http://localhost:3000/api/health)

---

## Health Check Details

Every service is monitored by Docker health checks with automatic startup gating:

| Service | Health Check Command | Interval | Timeout | Retries |
| :--- | :--- | :--- | :--- | :--- |
| **`postgres`** | `pg_isready -U postgres -d lenny_growth_db` | 5s | 5s | 5 |
| **`backend`** | `curl -f http://localhost:8000/health` | 10s | 5s | 5 |
| **`frontend`** | `wget --no-verbose --tries=1 --spider http://localhost:3000/api/health` | 10s | 5s | 3 |

Startup order:
- `backend` waits for `postgres` to become `healthy` before launching.
- `frontend` waits for `backend` to become `healthy` before launching.

---

## Transcript Ingestion in Docker

To ingest Lenny's Podcast transcripts into the PostgreSQL `pgvector` database inside the running container:

```bash
docker-compose exec backend python -m app.scripts.ingest_transcripts
```

---

## Operational Commands

### View Logs
```bash
# View aggregated logs for all services
docker-compose logs -f

# View backend logs only
docker-compose logs -f backend

# View frontend logs only
docker-compose logs -f frontend

# View database logs only
docker-compose logs -f postgres
```

### Restart Services
```bash
docker-compose restart
```

### Stop Services
```bash
# Stop containers without deleting data
docker-compose down

# Stop containers and wipe PostgreSQL volume data (fresh start)
docker-compose down -v
```

### Execute Shell Inside Container
```bash
# Backend interactive bash shell
docker-compose exec backend bash

# PostgreSQL interactive psql terminal
docker-compose exec postgres psql -U postgres -d lenny_growth_db
```

---

## Troubleshooting

### 1. Backend Cannot Reach Local Ollama
Docker containers access the host machine via `host.docker.internal`:
- On **Windows & macOS**, `host.docker.internal` is supported natively.
- On **Linux**, `extra_hosts: ["host.docker.internal:host-gateway"]` (already in `docker-compose.yml`) maps the host gateway.
- Ensure Ollama is configured to listen on all interfaces. Set `OLLAMA_HOST=0.0.0.0` before running `ollama serve`.

### 2. Port Already in Use
If port `5432`, `8000`, or `3000` is occupied by a local process:
Modify the port mappings in `docker-compose.yml`:
```yaml
ports:
  - "5433:5432" # change host port to 5433
```

### 3. Database Reset
To wipe the database volume and force re-initialization:
```bash
docker-compose down -v
docker-compose up --build
```
