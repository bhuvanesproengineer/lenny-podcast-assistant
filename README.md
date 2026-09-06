# Lenny Growth Assistant 🎙️🚀

## Overview
**Lenny Growth Assistant** is an intelligent AI growth assistant built with **FastAPI**, **Next.js**, and **PostgreSQL (pgvector)**. Trained on grounded insights from over 300+ transcripts of [Lenny's Podcast](https://www.youtube.com/@LennysPodcast), the assistant provides factually grounded answers with source episode citations and authors long-form atomic essays formatted with the **Ship 30 for 30** methodology.

> 📺 **Demo Video**: [Watch the full demonstration video on Google Drive](https://drive.google.com/file/d/1tZf7oJCRH9cTJLxpbBy4VNBdEDeLWxKC/view?usp=drive_link) showcasing the complete system running end-to-end.

---

## Features

- **FastAPI Backend**: Asynchronous REST API with lifecycle diagnostics, session management, and streaming support.
- **Next.js Frontend**: Modern 3-pane layout featuring chat streaming, session sidebar, and interactive Artifact Viewer.
- **PostgreSQL + pgvector**: Dense vector similarity search using cosine distance over thousands of podcast transcript chunks.
- **Session Persistence**: Multi-turn conversation history and thread management stored in PostgreSQL.
- **Source Citations**: Factual answers include verbatim transcript excerpts, guest attributions, and episode titles.
- **Ship30 Article Generation**: Generates 1,000–1,500 word atomic essays structured by Hook, Problem, Insight, Framework, Application, and Takeaway.
- **Artifact Generation**: Renders dedicated side-by-side artifacts with safe HTML sandboxing, raw Markdown tabs, and direct downloads.
- **Local Mode (Ollama)**: 100% on-device inference using `llama3.2:3b` and `nomic-embed-text` embeddings.
- **Cloud Mode (Groq)**: High-speed cloud reasoning using Groq API (`openai/gpt-oss-20b`) and Google GenAI embeddings (`gemini-embedding-001`).
- **Dual Embedding Architecture**: Strict isolation between local `transcript_chunks` and cloud `transcript_chunks_gemini`.
- **RAG Retrieval**: Context-aware retrieval with speaker matching, similarity scoring, and dynamic top-K controls.
- **Cloud Token Optimization & TPM Protection**: Automatic top_k=4 reduction, whitespace/dialogue compression, context trimming, and a sliding 60-second window TPM rate limiter.

---

## Architecture

The system features two strictly isolated end-to-end execution pipelines:

### Local Flow
```text
User
  ↓
Ollama Embeddings (nomic-embed-text, 768-dim)
  ↓
Vector Table: transcript_chunks
  ↓
pgvector Cosine Similarity Search
  ↓
Ollama LLM (llama3.2:3b)
  ↓
Response (Grounded Answer + Citations)
```

### Cloud Flow
```text
User
  ↓
Gemini Embeddings (gemini-embedding-001, 768-dim)
  ↓
Vector Table: transcript_chunks_gemini
  ↓
pgvector Cosine Similarity Search (top_k=4)
  ↓
Context Compression & Token Trimming (1,800 token budget)
  ↓
TPM Protection Rate Limiter (20,000 TPM window)
  ↓
Groq LLM (openai/gpt-oss-20b)
  ↓
Response (Grounded Answer + Citations)
```

---

## Database

The relational and vector schema runs on PostgreSQL with the `pgvector` extension:

1. **`sessions`**:
   - Stores distinct conversation threads.
   - Fields: `id` (UUID PK), `title`, `created_at`, `updated_at`.
2. **`messages`**:
   - Stores multi-turn conversation messages linked to a session.
   - Fields: `id` (Integer PK), `session_id` (FK to `sessions`), `role` (`user`/`assistant`), `content`, `created_at`.
3. **`artifacts`** (Message Metadata & Views):
   - Structured essay and guide documents produced by `Ship30Tool` / `ArtifactGenerator`.
   - Carries raw markdown, rendered HTML, word count, and artifact status.
4. **`transcript_chunks`** (Local Pipeline Table):
   - Chunks generated from all 303 episodes embedded with Ollama's `nomic-embed-text` (768 dimensions).
   - Contains **28,785** records joined with the `episodes` table.
5. **`transcript_chunks_gemini`** (Cloud Pipeline Table):
   - Isolated table populated with Google Gemini embeddings (`gemini-embedding-001`, 768 dimensions).
   - Fields: `id` (UUID PK), `episode_title`, `guest_name`, `publication_date`, `timestamp_ref`, `youtube_url`, `chunk_text`, `embedding` (`vector(768)`).
   - Contains **30,152** records.

---

## Environment Variables

### Application & Server Settings
| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Runtime environment (`development` / `production`). | `development` |
| `LOG_LEVEL` | Logging verbosity level (`info`, `debug`, `warning`). | `info` |
| `BACKEND_HOST` | FastAPI binding host. | `0.0.0.0` |
| `BACKEND_PORT` | FastAPI binding port. | `8000` |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins. | `http://localhost:3000` |

### Database
| Variable | Description | Example / Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection URL with pgvector support. | `postgresql://user:pass@host:5432/dbname?sslmode=require` |

### Dual Model Layer Selection
| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | Active LLM provider: `ollama` (Local) or `cloud` (Groq Cloud). | `ollama` |
| `FALLBACK_TO_LOCAL` | Automatically fall back to local Ollama on cloud error/rate limit. | `true` |

### Local Mode (Ollama)
| Variable | Description | Default |
|---|---|---|
| `OLLAMA_BASE_URL` | Base URL of local Ollama daemon. | `http://localhost:11434` |
| `OLLAMA_DEFAULT_MODEL` | Default model for on-device reasoning. | `llama3.2:3b` |

### Cloud Mode (Groq)
| Variable | Description | Default |
|---|---|---|
| `GROQ_API_KEY` | Groq Cloud API authentication key. | *(Required for cloud)* |
| `GROQ_BASE_URL` | Base URL for Groq's OpenAI-compatible chat endpoint. | `https://api.groq.com/openai/v1` |
| `GROQ_MODEL` | Groq chat completion model. | `openai/gpt-oss-20b` |

### Embeddings & Vector Search
| Variable | Description | Default |
|---|---|---|
| `EMBEDDING_PROVIDER` | Active embedding provider (`ollama` or `gemini`). | `ollama` |
| `EMBEDDING_MODEL` | Embedding model name (`nomic-embed-text` or `gemini-embedding-001`). | `nomic-embed-text` |
| `EMBEDDING_DIMENSION` | Dimensionality of embedding vector column. | `768` |
| `SIMILARITY_TOP_K` | Default number of vector chunks to retrieve. | `4` |
| `SIMILARITY_THRESHOLD` | Cosine similarity cutoff threshold. | `0.50` |

### Gemini Cloud Embeddings (Cloud Mode)
| Variable | Description | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Google Gemini API key. | *(Required for cloud)* |
| `GEMINI_EMBEDDING_MODEL` | Supported Gemini embedding model. | `gemini-embedding-001` |

### Cloud Token Controls & TPM Protection
| Variable | Description | Default |
|---|---|---|
| `CLOUD_TOP_K` | Reduced top-k chunk count for Cloud mode. | `4` |
| `CLOUD_MAX_CONTEXT_TOKENS` | Max token budget for compressed context prompt. | `1800` |
| `CLOUD_TPM_LIMIT` | Groq TPM safety threshold for sliding 60s rate limiter. | `20000` |

### Frontend
| Variable | Description | Default |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Backend URL accessible by the Next.js client. | `http://localhost:8000` |

---

## Setup

### 1. Database Setup (Neon PostgreSQL)
1. Provision a PostgreSQL instance on [Neon](https://neon.tech) or a local PostgreSQL 16+ server.
2. Enable the pgvector extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
3. Copy your database connection string to `DATABASE_URL` in `.env`.

### 2. Backend Setup
```bash
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
FastAPI runs on `http://localhost:8000` with Swagger docs at `/docs`.

### 3. Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Next.js development server
npm run dev
```
Next.js runs on `http://localhost:3000`.

---

## Deployment

- **Frontend (Vercel)**:
  - Connect your GitHub repository to Vercel.
  - Set Root Directory to `frontend`.
  - Add environment variable: `NEXT_PUBLIC_API_URL=https://your-backend-service.onrender.com`.
- **Backend (Render)**:
  - Deploy `backend` as a Web Service on Render using the provided `Dockerfile` or Python runtime.
  - Set build command: `pip install -r requirements.txt`.
  - Set start command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
  - Add environment variables (`DATABASE_URL`, `GROQ_API_KEY`, `GOOGLE_API_KEY`, `LLM_PROVIDER=cloud`, `EMBEDDING_PROVIDER=gemini`).
- **Database (Neon)**:
  - Hosted serverless PostgreSQL with native `pgvector` extension.
  - Tables `transcript_chunks` (Ollama) and `transcript_chunks_gemini` (Gemini) exist concurrently on Neon.

---

## Known Limitations

1. **Groq TPM Rate Limits**:
   - Free tier Groq inference has a 30,000 tokens-per-minute (TPM) quota.
   - Mitigated by our built-in `TPMTracker` sliding 60-second token accumulator, context compression, and `CLOUD_TOP_K=4` reduction.
2. **Gemini Free-Tier Request Limits**:
   - Google Free Tier limits `embedContent` requests to 1,000 per day per project.
   - Mitigated by rotating models (`gemini-embedding-001`, `gemini-embedding-2`) and automatic cooldown management.
3. **Ingestion Time**:
   - Ingesting all 303 transcript episodes requires handling API throttling and batch rate limits during large-scale offline runs.

---

## Current Deployment Status

The local Ollama-powered workflow is fully functional and was used for end-to-end testing and validation.

### Verified Working Flow

```text
User Query
→ Query Embedding (Ollama / nomic-embed-text)
→ pgvector Retrieval
→ Lenny Podcast Transcript Search
→ LLM Response Generation
→ Source-Cited Answer
```

### Cloud Embedding Status

The project includes a cloud embedding pipeline using Gemini embeddings and a dedicated pgvector index.

Due to free-tier API quota limitations during final testing and deployment preparation, the cloud embedding workflow was not fully validated in the deployed environment.

The local Ollama workflow remains fully operational and demonstrates the complete RAG architecture required by the assignment.

### Demo Evidence

A complete demonstration video showing the system running successfully is available here:

https://drive.google.com/file/d/1tZf7oJCRH9cTJLxpbBy4VNBdEDeLWxKC/view?usp=drive_link

### Running Locally

1. Install Ollama
2. Pull required models:
   - `llama3.2:3b`
   - `nomic-embed-text`
3. Configure environment variables
4. Start backend and frontend
5. Query the assistant

The local workflow has been tested successfully and is the recommended evaluation path.

### Implementation Checklist
- [x] **FastAPI Backend**: Fully operational with async lifespan health checks and REST endpoints.
- [x] **PostgreSQL + pgvector**: Database schema and vector indices verified on Neon.
- [x] **Grounded RAG Retrieval Engine**: Verified against transcripts with quality validation, logging, and strict citations.
- [x] **Ship30 Article Skill**: Autonomous long-form atomic essay generation with section constraints and `## Transcript Sources`.
- [x] **Local Mode (Ollama)**: Verified end-to-end with `llama3.2:3b` and 28,785 `nomic-embed-text` chunks.
- [x] **Cloud Mode (Groq)**: High-speed inference using Groq `openai/gpt-oss-20b`.
- [x] **Dual Provider Architecture**: Strict pipeline isolation between Local and Cloud modes.
- [x] **Cloud Token Budget & TPM Protection**: Top-k reduction, context compression, and rate limiting.
- [x] **Automated Test Suite**: 115 passing tests across 9 test suites.

---

## Changelog

### Major Architecture Updates
- **Dual-Provider Architecture**: Implemented strict provider isolation separating local Ollama retrieval from cloud Gemini + Groq retrieval.
- **Cloud Provider Integration & Groq Support**: Added `GroqProvider` using OpenAI-compatible chat completions (`openai/gpt-oss-20b`).
- **Cloud Token Optimization**: Implemented `CLOUD_TOP_K=4` reduction, dialogue whitespace compression, and context trimming (`CLOUD_MAX_CONTEXT_TOKENS=1800`).
- **TPM Protection**: Integrated an asynchronous sliding 60-second window rate limiter to guard against Groq 429 rate limit exceptions.
- **Gemini Ingestion Pipeline**: Built `backend/scripts/ingest_gemini.py` supporting standalone offline ingestion into `transcript_chunks_gemini`.
- **Gemini Embedding Model Fix**: Replaced deprecated `text-embedding-004` with `gemini-embedding-001` and added startup validation with `"hello world"` test embedding.
- **pgvector Enhancements**: Parallel vector table support across `transcript_chunks` (local) and `transcript_chunks_gemini` (cloud).
