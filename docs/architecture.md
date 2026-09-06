# Technical Architecture & Systems Specification

## Project Title: Lenny Growth Assistant 🎙️⚙️

---

## 1. System Overview

**Lenny Growth Assistant** is an enterprise-grade Retrieval-Augmented Generation (RAG) platform and autonomous agent runtime designed to transform over 300+ transcripts of Lenny's Podcast into an interactive, grounded growth knowledge base.

The architecture solves four core challenges in production RAG systems:
1. **Conversational Disconnect**: Standard semantic search fails on follow-up questions with ambiguous pronouns ("What else did she recommend?"). The system embeds a **Context-Aware Query Rewriter** that expands colloquial queries using multi-turn session history and speaker entity resolution.
2. **Intent Specialization**: Growth operators require both quick factual citations and long-form atomic essays. The system utilizes the **Pi Coding Agent SDK** to autonomously classify intent and route execution between `PodcastRAGTool` and `Ship30Tool`.
3. **Dual Provider & Complete Pipeline Isolation**: Production environments require both local, zero-cost development and robust cloud inference. The system implements a **Strictly Isolated Dual Pipeline**:
   - **Local Mode**: Uses Ollama (`llama3.2:3b` + `nomic-embed-text`) querying the `transcript_chunks` table (28,785 rows).
   - **Cloud Mode**: Uses Google Gemini (`gemini-embedding-001`) querying the `transcript_chunks_gemini` table (30,152 rows) and Groq LLM (`openai/gpt-oss-20b`), completely decoupled from localhost Ollama services.
4. **Cloud Rate Limits & TPM Protection**: Cloud providers enforce strict Tokens-Per-Minute (TPM) ceilings on free tiers. Cloud mode features an active **Token Budget Optimization Engine** (`CLOUD_TOP_K=4`, aggressive boilerplate trimming, 1,800 token context limit, and rolling TPM trackers).

---

## 2. High-Level Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────────┐
│                    Next.js 15 Frontend (Port 3000)                     │
│  • Session Sidebar (History / New Chat / Rename / Delete)              │
│  • Chat Stream (Markdown Rendering / Source Badges / Model Pill)       │
│  • Artifact Studio (Preview, Raw Markdown, Sandboxed HTML, Copy)       │
│  • Client-Side Native Exporters (.md, .html) + Server Exporter (.pdf)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / JSON (REST API)
┌───────────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Backend (Port 8000)                         │
│  • /api/chat                      • /api/sessions                      │
│  • /api/settings/provider         • /export/docx, /export/pdf          │
│  • Contextual Query Rewriter      • Dynamic Provider Factory           │
│  • EmbeddingRouter                • Cloud Token Budget Engine          │
└─────────────────┬──────────────────────────────────┬───────────────────┘
                  │                                  │
┌─────────────────▼──────────────┐  ┌────────────────▼───────────────────┐
│     Pi Coding Agent SDK        │  │      PostgreSQL 16 + pgvector      │
│  • Autonomous ReAct Loop       │  │  • Table: episodes (303 records)   │
│  • Dynamic Tool Registry       │  │  • Table: transcript_chunks        │
│  • PodcastRAGTool              │  │    (28,785 chunks, 768-dim Ollama) │
│  • Ship30Tool                  │  │  • Table: transcript_chunks_gemini │
│  • Execution Timeout Guards    │  │    (30,152 chunks, 768-dim Gemini) │
│  • Intent Routing              │  │  • Table: sessions & messages      │
└─────────────────┬──────────────┘  └────────────────────────────────────┘
                  │
┌─────────────────▼──────────────────────────────────────────────────────┐
│                    Dual Model Inference Layer                          │
│                                                                        │
│  [LOCAL PIPELINE]                                                      │
│  LLM_PROVIDER=ollama ──> Ollama llama3.2:3b                            │
│  EMBEDDING_PROVIDER=ollama ──> nomic-embed-text (Ollama /api/embed)    │
│  Target Vector Table: transcript_chunks (28,785 rows)                  │
│                                                                        │
│  [CLOUD PIPELINE]                                                      │
│  LLM_PROVIDER=cloud ──> Groq openai/gpt-oss-20b (api.groq.com)        │
│  EMBEDDING_PROVIDER=gemini ──> gemini-embedding-001 (Google AI)        │
│  Target Vector Table: transcript_chunks_gemini (30,152 rows)           │
│  Auto-Fallback: Cloud Failure / Rate Limit -> Local Ollama             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Dual Pipeline Execution Flows

### Local Flow (Development / Offline)
```text
User Query
    │
    ▼
Ollama Embeddings (nomic-embed-text, 768-dim)
    │
    ▼
pgvector Cosine Search ON transcript_chunks (28,785 chunks)
    │
    ▼
Ollama LLM (llama3.2:3b)
    │
    ▼
Synthesized Grounded Response + Citations
```

### Cloud Flow (Production / Serverless)
```text
User Query
    │
    ▼
Gemini Embeddings (gemini-embedding-001, 768-dim)
    │
    ▼
pgvector Cosine Search ON transcript_chunks_gemini (30,152 chunks, top_k=4)
    │
    ▼
Token Budget Optimization & Trimming (<1,800 prompt tokens)
    │
    ▼
Groq LLM (openai/gpt-oss-20b via api.groq.com)
    │
    ▼
Synthesized Grounded Response + Citations
```

---

## 4. Database Schema Specification

The persistence layer runs on PostgreSQL 16 (or Neon Serverless Postgres) utilizing the `pgvector` extension for cosine vector similarity search.

```text
┌─────────────────────────┐           ┌───────────────────────────────┐
│        episodes         │           │       transcript_chunks       │
├─────────────────────────┤           ├───────────────────────────────┤
│ id (UUID, PK)           │ 1       * │ id (UUID, PK)                 │
│ title (VARCHAR(255))    ├───────────┤ episode_id (UUID, FK)         │
│ guest (VARCHAR(255))    │           │ chunk_index (INTEGER)         │
│ episode_url (TEXT)      │           │ content (TEXT)                │
│ published_date (DATE)   │           │ embedding (VECTOR(768))       │
│ created_at (TIMESTAMP)  │           │ token_count (INTEGER)         │
└─────────────────────────┘           │ created_at (TIMESTAMP)        │
                                      └───────────────────────────────┘

┌─────────────────────────────────────────┐
│        transcript_chunks_gemini         │
├─────────────────────────────────────────┤
│ id (UUID, PK)                           │
│ episode_title (VARCHAR(512))            │
│ guest (VARCHAR(255))                    │
│ chunk_index (INTEGER)                   │
│ chunk_text (TEXT)                       │
│ embedding (VECTOR(768))                 │
│ youtube_url (TEXT)                      │
│ publish_date (VARCHAR(64))              │
│ created_at (TIMESTAMP)                  │
└─────────────────────────────────────────┘

┌─────────────────────────┐           ┌───────────────────────────────┐
│        sessions         │           │           messages            │
├─────────────────────────┤           ├───────────────────────────────┤
│ id (VARCHAR(64), PK)    │ 1       * │ id (VARCHAR(64), PK)          │
│ title (VARCHAR(255))    ├───────────┤ session_id (VARCHAR(64), FK)  │
│ created_at (TIMESTAMP)  │           │ role (VARCHAR(20))            │
│ updated_at (TIMESTAMP)  │           │ content (TEXT)                │
└─────────────────────────┘           │ selected_tool (VARCHAR(64))   │
                                      │ sources (JSONB)               │
                                      │ created_at (TIMESTAMP)        │
                                      └───────────────────────────────┘
```

### Table Definitions & Vector Indexing

1. **`episodes`**: Stores catalog metadata for each of the 303 podcast episodes.
2. **`transcript_chunks`**: Stores windowed chunks embedded with local `nomic-embed-text` (768-dim vector, 28,785 rows). Joined with `episodes` via `episode_id`.
3. **`transcript_chunks_gemini`**: Stores windowed chunks embedded with Google `gemini-embedding-001` (768-dim vector, 30,152 rows). Contains denormalized metadata (`episode_title`, `guest`, `youtube_url`, `publish_date`) allowing rapid single-table vector scans.
4. **`sessions`**: Tracks distinct conversation threads with cascading foreign keys.
5. **`messages`**: Stores individual conversation turns, tools executed, and source citation metadata formatted as JSONB.
6. **Vector Indexing**: Both tables utilize HNSW vector cosine indexes:
   ```sql
   CREATE INDEX IF NOT EXISTS idx_transcript_chunks_gemini_embedding
   ON transcript_chunks_gemini USING hnsw (embedding vector_cosine_ops)
   WITH (m = 16, ef_construction = 64);
   ```

---

## 5. REST API Endpoint Reference

| Method | Path | Request Body | Response Codes | Description |
|---|---|---|---|---|
| `GET` | `/health` | None | `200 OK`, `503 Service Unavailable` | Probes FastAPI runtime, database connectivity, and pgvector extension status. |
| `POST` | `/api/chat` | `{"session_id": str, "message": str}` | `200 OK`, `400 Bad Request`, `500 Server Error` | Orchestrates query rewriting, agent routing, RAG retrieval, and response synthesis. |
| `POST` | `/api/session/new` | `{"title": Optional[str]}` | `201 Created` | Creates a new chat session. |
| `GET` | `/api/sessions` | Query: `?skip=0&limit=50` | `200 OK` | Lists recent chat sessions ordered by `updated_at DESC`. |
| `GET` | `/api/sessions/{id}` | None | `200 OK`, `404 Not Found` | Retrieves complete chronological message history for a specific session. |
| `PATCH`| `/api/sessions/{id}` | `{"title": str}` | `200 OK`, `404 Not Found` | Updates session title. |
| `DELETE`| `/api/sessions/{id}`| None | `204 No Content`, `404 Not Found` | Deletes session and all associated messages via database cascade. |
| `GET` | `/api/settings/provider` | None | `200 OK` | Retrieves active provider, model slug, endpoint, and key status. |
| `POST`| `/api/settings/provider` | `{"provider": "cloud" \| "ollama"}` | `200 OK`, `400 Bad Request` | Hot-swaps the active inference provider at runtime. |
| `POST`| `/export/docx` | `{"markdown": str, "title": str}` | `200 OK` | Generates a styled `.docx` Word document with header typography. |
| `POST`| `/export/pdf` | `{"markdown": str, "title": str}` | `200 OK` | Generates a styled `.pdf` document with ReportLab two-pass numbering. |

---

## 6. Ingestion Pipelines

The platform maintains two specialized ingestion pipelines:

### 1. Local Ingestion (`backend/scripts/ingest.py`)
- Reads episode markdown transcripts from disk.
- Chunks text into ~1,000 character windows with 200 character overlap.
- Vectorizes via Ollama `nomic-embed-text` (`http://localhost:11434/api/embeddings`).
- Inserts 28,785 chunks into `transcript_chunks` with foreign keys to `episodes`.

### 2. Gemini Cloud Ingestion (`backend/scripts/ingest_gemini.py`)
- Traverses all 303 episode directories in `lennys-podcast-transcripts/episodes/**/transcript.md`.
- Parses YAML frontmatter (title, guest, youtube_url, publish_date).
- Reuses robust chunking logic (~1,000 chars, 200 char overlap).
- Vectorizes via Google Gemini `gemini-embedding-001` (768 dimensions).
- Bulk-inserts 30,152 chunks into `transcript_chunks_gemini` with batching, deduplication checks, and retry mechanisms.

---

## 7. Cloud Token Budget & TPM Protection Engine

Groq free-tier models enforce strict rate limits (typically 6,000 TPM):
1. **Dynamic Top-K Reduction**: Cloud mode reduces retrieval results from `top_k=6` to `top_k=4` (`CLOUD_TOP_K=4`).
2. **Aggressive Context Compression**: Strips podcast boilerplate, sponsor shoutouts, and repetitive conversational filler before assembling prompt context.
3. **Strict Token Budgeting**: Enforces a maximum context budget of 1,800 prompt tokens.
4. **TPM Tracker**: Tracks rolling per-minute token consumption and delays or routes requests to prevent rate limit exceptions.

---

## 8. Pi Agent Orchestration & Tool Routing

The **Pi Coding Agent SDK** (`pi-coding-agent`) provides the autonomous ReAct loop:
- **`PodcastRAGTool`**: Activated for tactical questions, growth queries, definition lookups, and guest advice. Retrieves evidence from the isolated provider vector store and returns markdown text with source badges.
- **`Ship30Tool`**: Activated when the prompt requests writing, authoring, essay generation, or Ship 30 frameworks. Generates a structured atomic essay following the Ship 30 framework and triggers the frontend Artifact Studio.

---

## 9. Security & Sandboxing Architecture

1. **Sandboxed HTML Rendering**: Web artifacts render inside an `<iframe>` configured with `sandbox="allow-same-origin"`. Script execution (`allow-scripts`) is explicitly omitted, eliminating XSS vulnerabilities.
2. **Database Protection**: Parameterized SQLAlchemy async queries prevent SQL injection.
3. **CORS Restrictions**: Configured via FastAPI middleware to restrict cross-origin requests to trusted frontend origins.
4. **Secret Isolation**: Secrets (`GROQ_API_KEY`, `GEMINI_API_KEY`, `DATABASE_URL`) are read via environment variables and never logged or exposed to client bundles.
