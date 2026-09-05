# Product Requirements Document (PRD)

## Project Title: Lenny Growth Assistant 🎙️🚀

---

### 1. Executive Summary & Objective

**Lenny Growth Assistant** is an intelligent, grounded conversational growth platform built on top of 300+ transcripts of Lenny's Podcast. The platform empowers startup founders, product managers, growth operators, and aspiring builders to instantly access tactical, battle-tested frameworks from world-class tech leaders without spending 100+ hours listening to long-form podcast audio.

The system combines:
1. **Dense Vector Retrieval (RAG)** over 28,000+ transcript chunks powered by `pgvector`.
2. **Context-Aware Query Rewriting** to resolve conversational pronouns and coreferences.
3. **Autonomous Agent Tool Routing** via the **Pi Coding Agent SDK** (`PodcastRAGTool` vs. `Ship30Tool`).
4. **Ship 30 for 30 Content Generation** producing ~1,250-word atomic essays.
5. **Interactive Side-by-Side Artifact Viewer** with safe sandboxed HTML rendering, Markdown preview, and native file export (`.md`, `.html`, optional `.pdf`).
6. **Dual Model Inference** with instant runtime toggling between local privacy-first Ollama (`llama3.2:3b`) and cloud high-reasoning OpenRouter (`claude-sonnet-4`).

---

### 2. Problem Statement

Lenny's Podcast represents one of the world's densest repositories of product, growth, and leadership knowledge. However:
- **High Friction to Insight**: Insights are locked inside 1-3 hour unstructured audio recordings.
- **Search Inefficiency**: Keyword search fails when users ask thematic questions (e.g. "How should I structure my growth team at Series A?").
- **Hallucination Risk**: Generic LLMs hallucinate growth advice rather than citing specific guest experiences (e.g., Elena Verna, Shreyas Doshi, Brian Balfour).
- **Lack of Actionable Synthesis**: Operators need structured frameworks (atomic essays, checklists, step-by-step guides) rather than fragmented quotes.

---

### 3. Target Users & Personas

| Persona | Role | Primary Goal | Key Pain Point |
|---|---|---|---|
| **Alex (Early-Stage Founder)** | Seed/Series A Founder | Establish product-market fit, setup initial pricing & retention loops. | No time for podcasts; needs definitive answers with source attribution. |
| **Priya (Senior PM / Growth Lead)** | Growth Product Manager | Design experiment cadences, improve onboarding, model activation metrics. | Needs concrete frameworks and Ship 30 essays to share with leadership. |
| **David (Associate PM / Student)** | Aspiring Product Operator | Learn product strategy, master interview case studies, build mental models. | Overwhelmed by podcast volume; needs structured, bite-sized lessons. |

---

### 4. Success Metrics & KPIs

#### Quantitative Metrics
- **Retrieval Precision**: $\ge 90\%$ of retrieved transcript chunks directly address the core product query.
- **Retrieval Latency**: P95 semantic vector search latency $< 250\text{ ms}$ over 28,000+ chunks.
- **End-to-End Response Time**: Local Ollama generation $< 12\text{ s}$; Cloud Claude generation $< 6\text{ s}$.
- **Ship 30 Essay Completion Rate**: $> 98\%$ successful generations meeting the 1,000–1,500 word threshold.
- **Zero-Crash Container Uptime**: 99.9% uptime across Docker Compose healthcheck probes.

#### Qualitative Metrics
- **Grounded Attribution**: 100% of factual growth claims include guest name and episode title citations.
- **Format Integrity**: Exported Markdown and HTML documents preserve formatting, headings, bullet points, and source citations without data loss.

---

### 5. Technical Assumptions

1. Transcripts accurately reflect spoken podcast dialogue and guest attributions.
2. An embedding dimension of 768 (`nomic-embed-text`) paired with cosine distance provides sufficient semantic discrimination across product management terminology.
3. Users require local offline capabilities (Ollama) as a mandatory baseline demo with seamless cloud model upgrade options.
4. Generated HTML artifacts must be treated as untrusted and rendered inside an isolated, script-restricted sandbox.

---

### 6. Scope & Boundaries

```text
┌────────────────────────────────────────────────────────┐
│                        IN SCOPE                        │
├────────────────────────────────────────────────────────┤
│ • Ingestion of 303 podcast episodes (28,785 chunks)    │
│ • pgvector cosine similarity search + query rewriting  │
│ • Pi Agent ReAct routing (PodcastRAGTool & Ship30Tool) │
│ • Dual-model provider abstraction & automatic fallback │
│ • Session management & multi-turn message persistence  │
│ • 3-pane responsive web layout with Artifact Viewer    │
│ • Native export (.md, .html) and optional PDF (.pdf)   │
│ • Containerized production deployment via Docker Compose│
└────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────┐
│                      OUT OF SCOPE                      │
├────────────────────────────────────────────────────────┤
│ • Real-time live audio speech-to-text transcription    │
│ • Multi-tenant user auth & billing/payment gateways    │
│ • External web crawling outside Lenny's podcast corpus │
│ • Collaborative multi-user shared document editing     │
└────────────────────────────────────────────────────────┘
```

---

### 7. User Flows

#### Flow 1: Grounded Q&A with Citation Retrieval
```text
User enters query: "How did Superhuman measure PMF?"
  │
  ▼
Backend QueryRewriter resolves context & terminology
  │
  ▼
pgvector calculates cosine distance across 28,785 chunks (Top-K=6, Score >= 0.65)
  │
  ▼
PodcastRAGTool synthesizes answer with guest attribution (Rahul Vohra)
  │
  ▼
Chat stream renders grounded markdown response with expandable source pills
```

#### Flow 2: Ship 30 for 30 Long-Form Essay Generation
```text
User enters prompt: "Write a Ship 30 essay on the Retention Flywheel"
  │
  ▼
Pi Agent classifies intent -> Routes autonomously to Ship30Tool
  │
  ▼
RAG retrieves Casey Winters & Elena Verna retention transcripts
  │
  ▼
Ship30Writer formats atomic essay: Hook -> Problem -> Insight -> Action Steps -> Sources
  │
  ▼
Artifact Viewer automatically slides open on right pane
  │
  ▼
User views Preview / Raw Markdown / Raw HTML -> Clicks "Export (.md)" for instant download
```

#### Flow 3: Seamless Model Switching & Fallback
```text
User selects "Cloud LLM (Claude Sonnet 4)" from Top Header Modal
  │
  ▼
FastAPI updates active provider via POST /api/settings/provider
  │
  ▼
If Cloud encounters timeout or 429 rate limit:
  ├── System logs structured warning
  ├── Automatically falls back to Local Ollama (llama3.2:3b)
  └── User receives uninterrupted grounded response
```

---

### 8. Detailed Acceptance Criteria

| Feature Area | Criteria & Verification Method |
|---|---|
| **Semantic Search** | Given a query on product strategy, when RAG executes, then it returns chunks with cosine similarity $\ge 0.65$ and includes episode metadata. |
| **Query Rewriter** | Given a conversational follow-up ("What did she say next?"), when rewriter runs, it resolves pronouns using the prior 3 session messages. |
| **Agent Routing** | Given a query asking to "author an essay" or "write a Ship 30 guide", the Pi Agent must route execution to `Ship30Tool` instead of `PodcastRAGTool`. |
| **Ship 30 Essay** | The generated essay must contain an H1 title, Hook, Problem, Core Framework, Actionable Steps, and a Sources section citing specific episodes. |
| **Artifact Viewer** | Renders side-by-side with chat, supports tabs (Preview, Raw Markdown, Raw HTML), and does not block continued chatting. |
| **Native Export** | Clicking the Export button downloads `.md` for Ship 30 essays or `.html` for web artifacts, with `.pdf` accessible as an optional dropdown format. |
| **Session Persistence**| Sessions and messages persist in PostgreSQL across server restarts and browser reloads. Deleting a session cascades cleanly. |
| **Docker Deployment** | Running `docker compose up --build` brings up `lenny-postgres`, `lenny-backend`, and `lenny-frontend` in `healthy` state with zero manual interventions. |

---

### 9. Risk Assessment & Mitigation Strategy

| Risk | Impact | Likelihood | Mitigation Strategy |
|---|---|---|---|
| **Transcript Hallucinations** | High | Low | Enforce strict system prompts instructing the model to decline answering if transcript evidence score falls below threshold. |
| **Cloud API Outage / Rate Limits** | High | Medium | Built-in `FALLBACK_TO_LOCAL=true` logic that routes traffic to Ollama `llama3.2:3b` whenever OpenRouter fails. |
| **Local Hardware Constraint** | Medium | Medium | Standardize on lightweight `llama3.2:3b` (2.0 GB) and `nomic-embed-text` (274 MB) capable of running on 8GB RAM laptops. |
| **Malicious HTML Injection** | High | Low | HTML artifacts render inside an `iframe` with `sandbox="allow-same-origin"` and script execution strictly disallowed. |
| **Docker Container Crashes** | High | Low | Multi-stage Dockerfiles with verified dependencies (`pi-coding-agent`), healthcheck retries, and start-period grace windows. |

---

### 10. Phased Implementation Roadmap

- **Phase 1 (Data & Vector Ingestion)**: Automated transcript ingestion pipeline, chunking with overlapping windows, pgvector database schema and migrations.
- **Phase 2 (RAG & Conversational Core)**: FastAPI backend endpoints, asyncpg connection pooling, session service, context-aware query rewriter, cosine similarity retrieval.
- **Phase 3 (Pi Agent Orchestration)**: Integration of Pi Coding Agent SDK, `PodcastRAGTool`, `Ship30Tool`, and multi-turn ReAct loop.
- **Phase 4 (Frontend & Artifact Viewer)**: Next.js 15 3-pane layout, chat interface, syntax highlighting, sandboxed HTML viewer, native export engine.
- **Phase 5 (Operationalization & Testing)**: Docker Compose orchestration, comprehensive 85-test suite, automated healthcheck probes, production documentation.