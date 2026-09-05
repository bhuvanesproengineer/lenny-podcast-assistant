# Lenny Growth Assistant 🎙️🚀

An enterprise-grade, grounded AI growth assistant powered by the **Pi Coding Agent SDK**, **FastAPI**, **PostgreSQL (pgvector)**, and **Next.js 15**. The assistant synthesizes actionable frameworks, tactical advice, and growth strategies from over 300+ transcripts of [Lenny's Podcast](https://www.youtube.com/@LennysPodcast), and authors long-form atomic essays formatted with the **Ship 30 for 30** methodology.

---

## 🏗️ Architecture Overview

The application follows a decoupled three-tier architecture with an autonomous agentic orchestration layer:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Next.js 15 Frontend (Port 3000)                 │
│   ┌─────────────────────┬──────────────────────┬───────────────────┐   │
│   │   Session Sidebar   │   Chat Stream Panel  │  Artifact Viewer  │   │
│   │   - Chat History    │   - Grounded Q&A     │  - Raw Markdown   │   │
│   │   - Session Switch  │   - Source Citations │  - Sandboxed HTML │   │
│   │   - New Session     │   - Model Badge Pill │  - Native Export  │   │
│   └─────────────────────┴──────────────────────┴───────────────────┘   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / JSON (REST API)
┌───────────────────────────────────▼────────────────────────────────────┐
│                        FastAPI Backend (Port 8000)                     │
│  • Session & Message CRUD        • Document Export (.docx, .pdf)       │
│  • Provider Switching Engine     • Vector Retrieval Pipeline           │
│  • Query Rewriter (Context-Aware)• Autonomous Agent Runner             │
└─────────────────┬──────────────────────────────────┬───────────────────┘
                  │                                  │
┌─────────────────▼──────────────┐  ┌────────────────▼───────────────────┐
│     Pi Coding Agent SDK        │  │     PostgreSQL 16 + pgvector       │
│  • ReAct Autonomous Loop       │  │  • 303 Podcast Episodes            │
│  • PodcastRAGTool (Citations)  │  │  • 28,785 Transcript Chunks        │
│  • Ship30Tool (Atomic Essays)  │  │  • Cosine Similarity Vector Index  │
│  • Error Recovery & Guardrails │  │  • Persistent Session & Chat Log   │
└─────────────────┬──────────────┘  └────────────────────────────────────┘
                  │
┌─────────────────▼──────────────────────────────────────────────────────┐
│                    Dual Model Inference Layer                          │
│   Local: Ollama (llama3.2:3b + nomic-embed-text)  [On-Device / Zero $] │
│   Cloud: OpenRouter (anthropic/claude-sonnet-4)    [High Reasoning]    │
│   Automatic Fallback: Cloud Outage / Rate Limit → Local Ollama        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 💻 Tech Stack

| Layer | Technology | Key Capabilities |
|---|---|---|
| **Frontend** | Next.js 15, React 19, Tailwind CSS | 3-pane layout, Sandboxed iframe HTML viewer, Markdown preview, Client-side native export |
| **Backend** | FastAPI, Python 3.12, SQLAlchemy, AsyncPG | Async REST API, Uvicorn ASGI server, Structured logging, Modular providers |
| **Database** | PostgreSQL 16, pgvector extension | HNSW/IVFFlat cosine similarity vector indexing, ACID conversation persistence |
| **Agent SDK** | Pi Coding Agent (`pi-coding-agent`) | Autonomous ReAct tool routing, State management, Intent classification |
| **Inference** | Ollama & OpenRouter | Local privacy-preserving inference (`llama3.2:3b`) & Cloud reasoning (`claude-sonnet-4`) |
| **Embeddings**| nomic-embed-text (768-dim) | Semantic chunk vectorization with Ollama embedding provider |
| **Container** | Docker & Docker Compose | Multi-stage production builds, non-root user, health check cascades |

---

## 📋 Prerequisites

Ensure your system meets the following requirements before installation:

- **Docker & Docker Compose**: Docker 24.0+ and Docker Compose v2.20+ (Recommended path)
- **Python**: Python 3.12+ (For local backend execution)
- **Node.js**: Node.js 20.x+ and npm 10.x+ (For local frontend execution)
- **PostgreSQL**: Version 16+ with `pgvector` extension installed
- **Ollama**: Installed and running locally ([Download Ollama](https://ollama.ai/))
  - RAM: 8GB minimum (16GB recommended for simultaneous local model execution)
  - GPU: Optional (Apple Silicon Metal, NVIDIA CUDA, or CPU fallback)

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` in the repository root:

```bash
cp .env.example .env
```

| Variable Name | Required | Default Value | Description |
|---|---|---|---|
| `ENVIRONMENT` | No | `production` | Runtime environment (`development` or `production`) |
| `LOG_LEVEL` | No | `info` | Server logging level (`debug`, `info`, `warning`, `error`) |
| `BACKEND_PORT` | No | `8000` | Port on which FastAPI backend listens |
| `CORS_ORIGINS` | No | `http://localhost:3000,http://frontend:3000` | Allowed CORS origins for browser communication |
| `POSTGRES_USER` | Yes | `postgres` | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | `postgres` | PostgreSQL password |
| `POSTGRES_DB` | Yes | `lenny_growth_db` | PostgreSQL database name |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://postgres:postgres@postgres:5432/lenny_growth_db` | Async connection string for SQLAlchemy / AsyncPG |
| `SYNC_DATABASE_URL` | Yes | `postgresql://postgres:postgres@postgres:5432/lenny_growth_db` | Synchronous connection string for Alembic migrations |
| `LLM_PROVIDER` | Yes | `cloud` | Default active model provider (`cloud` or `ollama`) |
| `FALLBACK_TO_LOCAL` | No | `true` | When `true`, automatically falls back to Ollama if Cloud fails |
| `OPENROUTER_API_KEY` | Cond. | (Empty) | API key for OpenRouter cloud models (Required if `LLM_PROVIDER=cloud`) |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenRouter API base endpoint |
| `CLOUD_MODEL` | No | `anthropic/claude-sonnet-4` | Cloud LLM model slug |
| `OLLAMA_BASE_URL` | Yes | `http://host.docker.internal:11434` | Ollama endpoint (`host.docker.internal` in Docker, `localhost` on host) |
| `OLLAMA_DEFAULT_MODEL`| Yes | `llama3.2:3b` | Local Ollama LLM model tag |
| `EMBEDDING_PROVIDER` | Yes | `ollama` | Provider used to compute embeddings (`ollama`) |
| `EMBEDDING_MODEL` | Yes | `nomic-embed-text` | Embedding model tag (768 dimensions) |
| `EMBEDDING_DIMENSION` | Yes | `768` | Vector dimension size matching pgvector column |
| `SIMILARITY_TOP_K` | No | `6` | Number of relevant chunks retrieved per RAG query |
| `SIMILARITY_THRESHOLD`| No | `0.65` | Minimum cosine similarity score for relevance filtering |
| `NEXT_PUBLIC_API_URL` | Yes | `http://localhost:8000` | Frontend browser URL pointing to FastAPI backend |

---

## 🦙 Local Model Setup (Ollama)

Lenny Growth Assistant supports 100% offline, privacy-first local execution using Ollama:

1. **Start Ollama Service**:
   ```bash
   ollama serve
   ```

2. **Pull Required Models**:
   ```bash
   # Pull lightweight local reasoning LLM (2.0 GB)
   ollama pull llama3.2:3b

   # Pull high-performance embedding model (274 MB)
   ollama pull nomic-embed-text
   ```

3. **Verify Models Are Ready**:
   ```bash
   ollama list
   ```
   You should see `llama3.2:3b` and `nomic-embed-text` listed.

4. **Docker Network Access**:
   When running inside Docker, the backend container reaches your host's Ollama via `http://host.docker.internal:11434`. On Linux hosts where `host.docker.internal` is not automatically configured, ensure `OLLAMA_ORIGINS="*"` is set when running `ollama serve`.

---

## ☁️ Cloud Model Setup (OpenRouter)

For maximum reasoning depth and publication-grade Ship 30 essays:

1. Create an account at [openrouter.ai](https://openrouter.ai) and generate an API key.
2. In your `.env` file, configure:
   ```bash
   LLM_PROVIDER=cloud
   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxx
   CLOUD_MODEL=anthropic/claude-sonnet-4
   ```
3. **Automatic Fallback Guard**:
   If your OpenRouter balance is exhausted, rate limited (429), or unavailable, the assistant **automatically switches to local Ollama (`llama3.2:3b`)** without breaking the user session or throwing unhandled errors.

---

## 🚀 Run Commands

### Option A: Production Run with Docker Compose (Recommended)

Launch the full stack (PostgreSQL + pgvector, FastAPI Backend, Next.js Frontend) with a single command:

```bash
# Build images and start all services in detached mode
docker compose up --build -d

# Verify all containers are running and healthy
docker compose ps
```

All 3 containers boot with automatic healthcheck verification:
- `lenny-postgres`: `http://localhost:5432` (Health: `pg_isready`)
- `lenny-backend`: `http://localhost:8000` (Health: `GET /health` → `200 OK`)
- `lenny-frontend`: `http://localhost:3000` (Health: `GET /api/health` → `200 OK`)

Access the web interface at **[http://localhost:3000](http://localhost:3000)**.

To inspect logs:
```bash
docker compose logs -f backend
```

To stop containers:
```bash
docker compose down
```

### Option B: Local Development Run (Without Docker)

#### 1. Start PostgreSQL with pgvector
```bash
docker run -d --name lenny-postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=lenny_growth_db pgvector/pgvector:pg16
```

#### 2. Run Backend
```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 3. Run Frontend
```bash
cd frontend
npm install
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000).

---

## 📚 Ingest Podcast Transcripts

To populate your PostgreSQL database with the complete dataset of 303 podcast episodes and 28,785 vectorized transcript chunks:

```bash
# Inside Docker:
docker compose exec backend python scripts/ingest.py

# Or locally with virtual environment active:
cd backend
python scripts/ingest.py
```

The script will:
1. Parse episode metadata and frontmatter from `lennys-podcast-transcripts/`.
2. Segment transcripts into semantically coherent overlapping windows.
3. Generate 768-dimensional embeddings via `nomic-embed-text`.
4. Batch-insert records into PostgreSQL with pgvector indexes.

---

## 🧪 Testing

The repository contains a comprehensive automated test suite covering all critical pathways:

### Backend Automated Test Suite (85 Tests Passing)
```bash
# Run tests inside Docker container:
docker compose exec backend pytest -v

# Or run tests locally:
cd backend
pytest -v
```

**Test Coverage Summary**:
- **API Endpoints (`test_api.py`)**: Session creation, health checks, chat orchestration, tool routing responses, error handling (12 tests).
- **Agent Orchestration (`test_agent.py`)**: ReAct tool loop, dynamic tool registration, token limit guards, execution timeouts (32 tests).
- **Semantic Retrieval (`test_retrieval.py`)**: Vector cosine similarity ranking, score thresholding, source citation verification (4 tests).
- **Query Rewriting (`test_query_rewriter.py`)**: Context-aware coreference resolution, domain terminology expansion (6 tests).
- **Provider Switching & Fallback (`test_providers.py`)**: Cloud provider, Ollama provider, error fallback to local LLM (8 tests).
- **Session & Message Persistence (`test_session.py`)**: Database CRUD, cascading deletes, session title updates, chronological history (18 tests).
- **Document Export (`test_export.py`)**: Word document (.docx) generation, PDF document (.pdf) formatting, markdown block parsing (5 tests).

### Frontend Typecheck & Production Build
```bash
cd frontend
npm run typecheck    # 0 TypeScript errors
npm run build        # Production bundle compiled & verified
```

For complete test specifications and manual UI test scenarios, see [docs/testing.md](docs/testing.md).

---

## 🔧 Troubleshooting

| Issue / Symptom | Root Cause | Resolution |
|---|---|---|
| **`ModuleNotFoundError: No module named 'pi_agent'`** | The PyPI distribution package name is `pi-coding-agent`, but Python code imports `pi_agent`. | Ensure `pi-coding-agent>=0.6.0` is present in `backend/requirements.txt` and rebuild with `docker compose up --build`. |
| **Backend cannot connect to Ollama (`Connection Refused`)** | In Docker, `localhost:11434` refers to the container itself, not the host machine. | Use `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env`. On Linux, ensure `extra_hosts: ["host.docker.internal:host-gateway"]` is present in `docker-compose.yml`. |
| **`pgvector` extension missing error** | Standard PostgreSQL images do not include vector search extensions. | Use `pgvector/pgvector:pg16` Docker image as configured in `docker-compose.yml`. Database tables and extensions are created automatically on startup by `init_db()`. |
| **Port 8000, 3000, or 5432 already in use** | A local PostgreSQL instance or existing process is holding the port. | Stop the local service or change host port mapping in `docker-compose.yml` (e.g. `"5433:5432"`). |
| **Artifact Export downloads PDF instead of native format** | Prior export handler defaulted unconditionally to PDF format. | Resolved in latest release: The Export button now automatically detects the artifact type and downloads native Markdown (`.md`) for Ship 30 essays or HTML (`.html`) for web artifacts, with PDF remaining an optional selection. |
| **Empty or weak RAG retrieval results** | Query contains colloquial phrasing or conversational references like "what did he say?". | The system utilizes `QueryRewriter` to expand conversational queries into dense keyword queries against episode transcripts. |

---

## 📄 Documentation Sitemap

- [docs/PRD.md](docs/PRD.md) - Product Requirements Document & Business Goals
- [docs/architecture.md](docs/architecture.md) - Deep Technical Architecture & Schema Specification
- [docs/design.md](docs/design.md) - UI/UX Design System, 3-Pane Layout, & Accessibility
- [docs/testing.md](docs/testing.md) - Comprehensive Automated & Manual UI Test Plan
- [agent_transcripts/](agent_transcripts/) - Agent Scaffolding & Major Debugging Case Studies
- [DOCKER.md](DOCKER.md) - Container Operations, Health Checks, & Deployment
