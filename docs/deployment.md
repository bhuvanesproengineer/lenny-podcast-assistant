# Production Deployment Guide

## Lenny Growth Assistant 🎙️🚀

This guide covers production deployment for the Lenny Growth Assistant stack:
- **Database**: Neon Serverless PostgreSQL with `pgvector`
- **Backend**: Render (FastAPI + Python 3.11/3.12)
- **Frontend**: Vercel (Next.js 15 App Router)
- **Local Alternative**: Docker Compose

---

## 1. Database Setup: Neon (PostgreSQL + pgvector)

Neon provides serverless PostgreSQL with native `pgvector` support, auto-scaling, and connection pooling.

### Steps:
1. Sign up / log in to [Neon Console](https://console.neon.tech).
2. Create a new project named `lenny-growth-assistant`.
3. In the SQL Editor, enable the `pgvector` extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
4. Copy the connection string from the Neon dashboard:
   ```text
   postgresql://[user]:[password]@[neon-hostname]/neondb?sslmode=require
   ```
5. Ensure your SQLAlchemy async connection string in the backend uses `postgresql+asyncpg://`:
   ```text
   DATABASE_URL=postgresql+asyncpg://[user]:[password]@[neon-hostname]/neondb?ssl=require
   ```
6. Run database migrations / initialization from your backend:
   ```bash
   cd backend
   python -m app.db.init_db
   ```
7. Populate vectors into Neon using the Gemini ingestion pipeline:
   ```bash
   python scripts/ingest_gemini.py
   ```

---

## 2. Backend Deployment: Render (FastAPI)

Render hosts the asynchronous FastAPI backend with automated TLS, health check monitoring, and continuous deployment from GitHub.

### Render Web Service Configuration:
- **Environment**: Python 3
- **Region**: Choose the region closest to your Neon database (e.g., US East / Ohio)
- **Root Directory**: `backend`
- **Build Command**:
  ```bash
  pip install --upgrade pip && pip install -r requirements.txt
  ```
- **Start Command**:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
  ```
- **Health Check Path**: `/health`

### Environment Variables on Render:
| Variable | Value / Description |
|---|---|
| `DATABASE_URL` | Neon `postgresql+asyncpg://...` connection string |
| `LLM_PROVIDER` | `cloud` |
| `EMBEDDING_PROVIDER` | `gemini` |
| `EMBEDDING_MODEL` | `gemini-embedding-001` |
| `OPENAI_API_KEY` | Your Groq API key (`gsk_...`) |
| `OPENAI_BASE_URL` | `https://api.groq.com/openai/v1` |
| `OPENAI_MODEL` | `openai/gpt-oss-20b` |
| `GEMINI_API_KEY` | Your Google Gemini API key |
| `CLOUD_TOP_K` | `4` |
| `CORS_ORIGINS` | `https://your-vercel-domain.vercel.app` |

---

## 3. Frontend Deployment: Vercel (Next.js)

Vercel provides edge-optimized hosting for the Next.js 15 frontend application.

### Steps:
1. Import your GitHub repository into [Vercel](https://vercel.com).
2. Set **Root Directory** to `frontend`.
3. Framework Preset: **Next.js**.
4. Configure Build and Output Settings:
   - Build Command: `npm run build`
   - Output Directory: `.next`
   - Install Command: `npm install`

### Environment Variables on Vercel:
| Variable | Value / Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL of your deployed Render backend (e.g., `https://lenny-backend.onrender.com`) |

5. Deploy! Once deployed, verify:
   - Chat interaction connects to `/api/chat` on Render.
   - Session history loads from `/api/sessions`.
   - Export tools download markdown and trigger PDF generation.

---

## 4. Local Deployment: Docker Compose

For a unified local or self-hosted deployment:

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Start PostgreSQL with pgvector, FastAPI, and Next.js
docker compose up -d

# 3. Check health status
docker compose ps

# 4. View logs
docker compose logs -f backend
```

Ports:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`

---

## 5. Current Deployment Status & Evaluation Path

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

[Watch Demo Video on Google Drive](https://drive.google.com/file/d/1tZf7oJCRH9cTJLxpbBy4VNBdEDeLWxKC/view?usp=drive_link)

### Running Locally
1. Install Ollama
2. Pull required models:
   - `llama3.2:3b`
   - `nomic-embed-text`
3. Configure environment variables
4. Start backend and frontend
5. Query the assistant

The local workflow has been tested successfully and is the recommended evaluation path.
