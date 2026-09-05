# Quality Assurance & Testing Specification Document

## Project Title: Lenny Growth Assistant 🎙️🧪

---

## 1. Testing Strategy Overview

The testing strategy for Lenny Growth Assistant combines automated backend testing (85 unit and integration tests), frontend type safety and production build validation, and an exhaustive manual UI test matrix.

```text
┌─────────────────────────────────────────────────────────────┐
│                    Testing Pyramid                          │
│                                                             │
│                [ Manual UI Verification ]                   │
│          3-Pane Layout, Export, Fallback Modals             │
│                                                             │
│             [ Frontend Static & Build Tests ]               │
│          TypeScript Typecheck (0 Errors), Next Build        │
│                                                             │
│             [ Backend Automated Test Suite ]                │
│       85 Tests: API, Retrieval, Agent Routing, DB           │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Automated Test Suite (85 Tests Passing)

### Test Execution Command
```bash
# Inside Docker Backend:
docker compose exec backend pytest -v

# Locally:
cd backend
pytest -v
```

### Test Suite Structure & Breakdown

| Test File | Modules Under Test | Test Count | Key Verification Areas |
|---|---|:---:|---|
| **`tests/test_agent.py`** | `LennyAgent`, `PiCodingAgent`, `PodcastRAGTool`, `Ship30Tool` | 32 | Tool registration, intent classification, ReAct loop execution, token limits, exception guards, empty evidence handling. |
| **`tests/test_session.py`** | `session_service.py`, SQLAlchemy models | 18 | Session creation, message sequencing, cascading deletions, session renaming, pagination (`skip`/`limit`), async connection cleanup. |
| **`tests/test_api.py`** | `app/api/chat.py`, `app/api/health.py`, `app/api/sessions.py` | 12 | `/health` 200 responses, `/api/chat` payload validation, error codes (400, 404, 500), CORS headers, streaming responses. |
| **`tests/test_providers.py`**| `OllamaProvider`, `CloudProvider`, `ProviderFactory` | 8 | Provider instantiation, fallback logic on rate limit (429/timeout), base URL normalization, prompt formatting. |
| **`tests/test_query_rewriter.py`** | `QueryRewriter` | 6 | Conversational coreference resolution, multi-turn history extraction, domain terminology injection. |
| **`tests/test_export.py`** | `export_service.py`, `app/api/export.py` | 5 | Word document (.docx) binary generation, PDF (.pdf) binary formatting, ReportLab page numbering, markdown block parsing. |
| **`tests/test_retrieval.py`**| `RAGService`, pgvector embeddings | 4 | Cosine similarity scoring, score threshold filtering ($\ge 0.65$), top-k limit enforcement, episode metadata joining. |
| **Total Passing Tests** | | **85** | **100% Pass Rate** |

---

## 3. Frontend Static Analysis & Verification

```bash
# TypeScript Compile Verification (Strict mode):
cd frontend
npm run typecheck

# Production Bundle Build:
npm run build
```
- **Typecheck Result**: `tsc --noEmit` exits with code 0 (zero errors).
- **Next.js Production Build**: All static routes (`/`, `/_not-found`, `/api/health`) compiled and optimized.

---

## 4. Comprehensive Manual UI Test Plan

The following manual test plan verifies real-world user flows across the 3-pane interface:

### Category 1: Session Management & Chat Stream

| Case ID | Test Description | Action / Steps | Expected Result | Pass/Fail |
|:---:|---|---|---|:---:|
| **TC-01** | Create New Chat Session | Click `+ New Chat` in sidebar. | A new active session is created with a clean message panel; sidebar displays new session. | **PASS** |
| **TC-02** | Grounded Q&A with Citations | Send: *"How did Superhuman measure product-market fit?"* | Assistant streams answer referencing Rahul Vohra with source citation pill at bottom. | **PASS** |
| **TC-03** | Multi-Turn Coreference | Send follow-up: *"What exact question did he ask users?"* | QueryRewriter resolves context; answer returns the 4-choice question from Rahul Vohra. | **PASS** |
| **TC-04** | Missing Evidence Graceful Decline | Send: *"What is the best recipe for sourdough bread?"* | Assistant politely declines: indicates podcast corpus does not contain relevant advice. | **PASS** |
| **TC-05** | Session Renaming | Click edit icon on session in sidebar; enter new title; press Enter. | Session title updates immediately and persists upon page refresh. | **PASS** |
| **TC-06** | Session Deletion | Click delete icon on session; confirm deletion. | Session and all messages deleted from PostgreSQL; active chat resets to initial state. | **PASS** |

---

### Category 2: Ship 30 Essay Generation & Artifact Studio

| Case ID | Test Description | Action / Steps | Expected Result | Pass/Fail |
|:---:|---|---|---|:---:|
| **TC-07** | Automatic Artifact Trigger | Send: *"Write a Ship 30 essay on the Retention Flywheel."* | Pi Agent routes to `Ship30Tool`; generates ~1,250-word essay; Artifact Viewer auto-opens on right. | **PASS** |
| **TC-08** | Artifact Tab Navigation | In Artifact Viewer, toggle between `Preview`, `Raw Markdown`, and `Raw HTML`. | `Preview` renders formatted markdown; `Raw Markdown` displays syntax-highlighted code; `Raw HTML` displays sandboxed iframe and code. | **PASS** |
| **TC-09** | HTML Sandboxing Isolation | In `Raw HTML` tab, inspect iframe DOM elements. | iframe is configured with `sandbox="allow-same-origin"`; no scripts can execute. | **PASS** |
| **TC-10** | Copy to Clipboard | Click `Copy` button in Artifact Viewer header. | Text copies to system clipboard; button icon switches to green checkmark for 2 seconds. | **PASS** |
| **TC-11** | Fullscreen Toggle | Click `Fullscreen` button in Artifact Viewer header. | Viewer expands to occupy 100% viewport; clicking `Minimize` restores 3-pane layout. | **PASS** |

---

### Category 3: Artifact Export Functionality

| Case ID | Test Description | Action / Steps | Expected Result | Pass/Fail |
|:---:|---|---|---|:---:|
| **TC-12** | Native Markdown Export (Default) | Open a Ship 30 essay artifact; click primary `Export (.md)` button. | Browser immediately downloads `<title>.md`; file contains complete raw markdown text, headers, and citations. | **PASS** |
| **TC-13** | Native HTML Export (Default) | Open an HTML/CSS artifact; click primary `Export (.html)` button. | Browser immediately downloads `<title>.html`; file contains clean HTML without markdown fences. | **PASS** |
| **TC-14** | Optional PDF Export | Open any artifact; click chevron dropdown next to Export; select `PDF (.pdf)`. | Backend `/export/pdf` processes document; browser downloads styled, publication-ready PDF. | **PASS** |
| **TC-15** | Export Dropdown Dismissal | Click chevron dropdown; click outside the menu on the background. | Menu closes cleanly without triggering any download action. | **PASS** |

---

### Category 4: Model Provider Switching & Fallback

| Case ID | Test Description | Action / Steps | Expected Result | Pass/Fail |
|:---:|---|---|---|:---:|
| **TC-16** | Switch to Local Ollama | Click header model pill; select `🟢 Ollama Local`; click `Done`. | Active badge updates; subsequent queries execute via local `llama3.2:3b`. | **PASS** |
| **TC-17** | Switch to Cloud Claude | Click header model pill; select `☁️ Claude Cloud`; click `Done`. | Active badge updates; subsequent queries execute via OpenRouter `claude-sonnet-4`. | **PASS** |
| **TC-18** | Automatic Local Fallback | Set invalid OpenRouter key in `.env`; trigger query. | Backend catches 401/timeout; automatically falls back to Ollama `llama3.2:3b`; user receives answer. | **PASS** |

---

## 5. Summary of Test Validation Results

All 85 automated tests pass with 0 warnings or failures. The frontend compiles with strict TypeScript typing and builds a production bundle with zero warnings. Manual UI test cases TC-01 through TC-18 have all been executed and validated against the running Docker containers.
