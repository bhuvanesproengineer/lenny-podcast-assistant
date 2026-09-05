# Technical Architecture & Systems Specification

## Project Title: Lenny Growth Assistant 🎙️⚙️

---

## 1. System Overview

**Lenny Growth Assistant** is an enterprise-grade Retrieval-Augmented Generation (RAG) platform and autonomous agent runtime designed to transform over 300+ transcripts of Lenny's Podcast into an interactive, grounded growth knowledge base.

The architecture solves three core challenges in production RAG systems:
1. **Conversational Disconnect**: Standard semantic search fails on follow-up questions with ambiguous pronouns ("What else did she recommend?"). The system embeds a **Context-Aware Query Rewriter** that expands colloquial queries using multi-turn session history.
2. **Intent Specialization**: Growth operators require both quick factual citations and long-form atomic essays. The system utilizes the **Pi Coding Agent SDK** to autonomously classify intent and route execution between `PodcastRAGTool` and `Ship30Tool`.
3. **Availability & Cost Optimization**: Cloud inference provides high reasoning capabilities but incurs API costs and rate limit risks. The system implements a **Dual Model Architecture** supporting both on-device Ollama (`llama3.2:3b` + `nomic-embed-text`) and Cloud LLM (`claude-sonnet-4`), backed by automatic fallback.

---

## 2. High-Level Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────────┐
│                    Next.js 15 Frontend (Port 3000)                     │
│  • Session Sidebar (History / New Chat / Rename / Delete)              │
│  • Chat Stream (Markdown Rendering / Source Badges / Model Pill)       │
│  • Artifact Viewer (Tabs: Preview, Raw Markdown, Sandboxed HTML)       │
│  • Client-Side Native Exporters (.md, .html) + Server Exporter (.pdf)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / JSON (REST API)
┌───────────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Backend (Port 8000)                         │
│  • /api/chat                      • /api/sessions                      │
│  • /api/settings/provider         • /export/docx, /export/pdf          │
│  • Contextual Query Rewriter      • Dynamic Provider Factory           │
└─────────────────┬──────────────────────────────────┬───────────────────┘
                  │                                  │
┌─────────────────▼──────────────┐  ┌────────────────▼───────────────────┐
│     Pi Coding Agent SDK        │  │      PostgreSQL 16 + pgvector      │
│  • Autonomous ReAct Loop       │  │  • Table: episodes (303 records)   │
│  • Dynamic Tool Registry       │  │  • Table: transcript_chunks        │
│  • PodcastRAGTool              │  │    (28,785 chunks, 768-dim vector) │
│  • Ship30Tool                  │  │  • Table: sessions & messages      │
│  • Execution Timeout Guards    │  │  • Index: HNSW / IVFFlat Cosine    │
└─────────────────┬──────────────┘  └────────────────────────────────────┘
                  │
┌─────────────────▼──────────────────────────────────────────────────────┐
│                    Dual Model Inference Layer                          │
│   • Local Mode: Ollama (llama3.2:3b + nomic-embed-text)                │
│   • Cloud Mode: OpenRouter (anthropic/claude-sonnet-4)                 │
│   • Auto-Fallback: Cloud Failure / Rate Limit -> Local Ollama          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Database Schema Specification

The persistence layer runs on PostgreSQL 16 utilizing the `pgvector` extension for cosine vector similarity search.

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
2. **`transcript_chunks`**: Stores windowed transcript content.
   - Column `embedding`: `vector(768)` matching `nomic-embed-text`.
   - Index: An HNSW / IVFFlat index on `embedding vector_cosine_ops` enables sub-50ms approximate nearest neighbor (ANN) retrieval across 28,785 chunks:
     ```sql
     CREATE INDEX IF NOT EXISTS idx_transcript_chunks_embedding
     ON transcript_chunks USING hnsw (embedding vector_cosine_ops)
     WITH (m = 16, ef_construction = 64);
     ```
3. **`sessions`**: Tracks distinct conversation threads with cascading foreign keys.
4. **`messages`**: Stores individual conversation turns, tools executed, and source citation metadata formatted as JSONB.

---

## 4. REST API Endpoint Reference

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

## 5. Component Boundaries & Responsibilities

```text
┌───────────────────────┐
│   Next.js Frontend    │ ──> User Interaction, Layout, Sandboxing, Local File Export (.md/.html)
└───────────┬───────────┘
            │
┌───────────▼───────────┐
│    FastAPI Backend    │ ──> API Routing, Validation, Lifespan Hooks, Export Engine (.docx/.pdf)
└───────────┬───────────┘
            │
┌───────────▼───────────┐
│  Session / DB Service │ ──> AsyncPG Connection Pooling, SQLAlchemy ORM, Migration Management
└───────────┬───────────┘
            │
┌───────────▼───────────┐
│     Agent Manager     │ ──> Query Rewriting, ReAct Event Loop, Pi Agent Harness, Tool Invocations
└───────────┬───────────┘
            │
┌───────────▼───────────┐
│ RAG & Vector Engine   │ ──> Nomic Vector Embeddings, Cosine Distance Calculations, Thresholding
└───────────┬───────────┘
            │
┌───────────▼───────────┐
│  Inference Providers  │ ──> Ollama (Local) and OpenRouter (Cloud) with Automatic Fallback
└───────────────────────┘
```

---

## 6. Transcript Ingestion Pipeline

The ingestion pipeline (`backend/scripts/ingest.py`) processes 303 podcast markdown transcript files into vectorized records:

```text
[Podcast Transcripts Directory]
  │
  ▼
1. Scan Episode Folders (parse episode_number, guest, title from frontmatter)
  │
  ▼
2. Windowed Chunking Pipeline:
   - Chunk Size: ~1,000 characters
   - Chunk Overlap: 200 characters (preserves sentence continuity across boundaries)
  │
  ▼
3. Batch Vector Embedding:
   - Batches of 50 chunks sent to Ollama /api/embeddings (nomic-embed-text)
   - Outputs normalized 768-dimensional float arrays
  │
  ▼
4. Bulk Upsert into PostgreSQL:
   - Transactional commit of episode metadata and chunk vectors
   - HNSW index build for high-throughput similarity search
```

---

## 7. Retrieval Pipeline (RAG) Sequence Flow

```text
User Query: "What did she say about retention loops?"
  │
  ▼
[QueryRewriter]
  ├── Reads last 3 messages in Session history
  └── Rewrites query to: "Elena Verna rules and strategies for product-led retention loops"
  │
  ▼
[Embedding Generator]
  └── Vectorizes rewritten query via nomic-embed-text (768-dim float vector)
  │
  ▼
[pgvector Cosine Search]
  ├── SQL: SELECT content, episode_id, (1 - (embedding <=> :query_vector)) AS score
  │        FROM transcript_chunks WHERE score >= 0.65 ORDER BY score DESC LIMIT 6
  └── Returns top-6 matching transcript chunks with episode metadata
  │
  ▼
[Context Assembly & Deduplication]
  ├── Deduplicates repeated chunks from identical episodes
  └── Injects structured transcript text with [Episode: Guest] citations into agent prompt
  │
  ▼
[Inference Provider]
  └── LLM synthesizes grounded answer strictly referencing retrieved transcript evidence
```

---

## 8. Pi Agent Orchestration & Tool Routing

The **Pi Coding Agent SDK** (`pi-coding-agent`) provides the autonomous ReAct (Reasoning + Acting) loop that decides how to fulfill incoming requests:

```text
                         Incoming User Prompt
                                   │
                                   ▼
                       [Intent Classification]
                      Is the user requesting an
                     atomic essay / Ship 30 guide?
                                  / \
                                 /   \
                             YES/     \NO
                               /       \
                              ▼         ▼
                       [Ship30Tool]  [PodcastRAGTool]
```

- **`PodcastRAGTool`**:
  - Activated for tactical questions, growth queries, definition lookups, and guest advice.
  - Queries `RAGService`, formats evidence, and returns an `AgentResponse` containing markdown text and episode sources.
- **`Ship30Tool`**:
  - Activated when the prompt requests writing, authoring, essay generation, or Ship 30 frameworks.
  - Generates a structured ~1,250-word atomic essay following the Ship 30 framework:
    `# Title` $\rightarrow$ `## Hook` $\rightarrow$ `## Problem` $\rightarrow$ `## Framework / Lesson` $\rightarrow$ `## Action Steps` $\rightarrow$ `## Sources`.
  - Automatically triggers the Artifact Viewer in the frontend.

---

## 9. Model Toggle & Automatic Fallback Engine

The system abstracts all model calls behind `BaseLLMProvider` (`backend/app/providers/base.py`):

```python
class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Standard completion interface."""
    @abstractmethod
    async def generate_ship30(self, topic: str, context: Optional[str] = None) -> str:
        """Long-form essay synthesis."""
```

### Hot-Swapping & Resilience Architecture
1. **Dynamic Switching**: The active provider is managed in memory by `ProviderFactory`. Switching via `POST /api/settings/provider` or the UI header badge takes effect immediately for the next request without restarting the server.
2. **Automatic Fallback Circuit**:
   - If `LLM_PROVIDER=cloud` is active:
   - When OpenRouter encounters an HTTP 429 (rate limit), 503 (service unavailable), network timeout, or missing key:
   - The provider catches the exception, logs a warning, and immediately invokes `OllamaProvider.generate()` with local model `llama3.2:3b`.
   - The user receives a continuous response rather than an unhandled 500 error.

---

## 10. Security & Sandboxing Architecture

1. **Sandboxed HTML Rendering**:
   - Web artifacts and HTML previews render inside an `<iframe>` configured with:
     ```html
     <iframe sandbox="allow-same-origin" srcDoc={content} />
     ```
   - Script execution (`allow-scripts`) is explicitly **omitted**, eliminating any possibility of XSS or malicious script injection from generated content.
2. **Database Protection**:
   - All SQL operations utilize parameterized SQLAlchemy async queries.
   - Vector similarity queries use bound parameters for embedding vectors, preventing SQL injection.
3. **CORS Restrictions**:
   - Configured via FastAPI middleware to restrict cross-origin requests strictly to trusted frontend origins (`http://localhost:3000`).
4. **Secret Isolation**:
   - API keys are injected via environment variables (`.env`) and never exposed in client bundles or logged to disk.

---

## 11. Deployment Topology & Docker Compose Networking

All services communicate across an isolated Docker bridge network (`lenny-network`):

```text
┌────────────────────────────────────────────────────────────────────────┐
│                     Host Machine (Developer / Server)                  │
│                                                                        │
│   Ollama Service (Listening on host:11434)                             │
│   ▲                                                                    │
│   │ (Bridged via host.docker.internal)                                 │
│   │                                                                    │
│  ┌┼─────────────────────────────────────────────────────────────────┐  │
│  ││               Docker Compose Network (lenny-network)            │  │
│  ││                                                                 │  │
│  ││  ┌──────────────────────┐             ┌──────────────────────┐  │  │
│  ││  │    lenny-frontend    │ ──────────> │    lenny-backend     │  │  │
│  ││  │ (Node 20 / Next.js)  │  Port 8000  │  (Python / FastAPI)  │  │  │
│  ││  │      Port 3000       │             │      Port 8000       │  │  │
│  ││  └──────────────────────┘             └──────────┬───────────┘  │  │
│  ││                                                  │              │  │
│  ││                                                  │ Port 5432    │  │
│  ││                                                  ▼              │  │
│  ││                                       ┌──────────────────────┐  │  │
│  │└────────────────────────────────────── │    lenny-postgres    │  │  │
│  │                                        │  (PostgreSQL 16 +    │  │  │
│  │                                        │      pgvector)       │  │  │
│  │                                        └──────────┬───────────┘  │  │
│  │                                                   │              │  │
│  │                                                   ▼              │  │
│  │                                            [postgres_data]       │  │
│  │                                            (Named Volume)        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

### Healthcheck Cascades
- `lenny-postgres` probes `pg_isready` every 5s.
- `lenny-backend` waits for `postgres` to be `healthy` before starting; probes `GET /health` every 10s.
- `lenny-frontend` waits for `backend` to be `healthy` before serving; probes `GET /api/health` every 10s.

---

## 12. Technical Trade-Offs & Architecture Decisions

| Decision | Chosen Architecture | Alternative Considered | Engineering Trade-Off Rationale |
|---|---|---|---|
| **Vector Index** | `pgvector` HNSW index | Dedicated Vector DB (Pinecone, Qdrant) | Keeps relational session data and vector chunks in a single PostgreSQL instance, eliminating distributed transactions and multi-database maintenance. |
| **Agent Framework**| Pi Coding Agent SDK | LangChain / CrewAI | Lightweight, highly transparent ReAct loop without heavyweight abstractions or brittle dependency conflicts. |
| **Artifact Export**| Client-side Blob download (.md, .html) | Server-side file generation | Instant zero-latency downloads directly in the browser; avoids server file storage and eliminates unnecessary network hops. Server handles complex binary formats (.docx, .pdf). |
| **HTML Sandbox** | `iframe` with `allow-same-origin` | React `dangerouslySetInnerHTML` | Absolute isolation of generated CSS/styles and strict prevention of arbitrary script execution. |
