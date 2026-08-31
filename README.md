# AI-Video-Knowledge-Extractor

Turns a video (file or URL) into an interactive learning roadmap — intro, key points, topic tree, AI explanations, and quizzes — with accounts and per-user history. SvelteKit frontend, FastAPI backend, MCP tool server, SQLite, Docker.

## Architecture

```
Video URL ──► MCP: fetch_video_details ─┬─ captions ────────────────► Gemini ─┐
                                         └─ no captions ─► yt-dlp audio ─► Whisper ─┘
Uploaded file ──► FFmpeg ──► Whisper ──► Gemini
                                              │
                                              ▼
                                   Roadmap + Quizzes (MCP tools)
                                              │
                                              ▼
                          SvelteKit ◄──► FastAPI ◄──► SQLite (accounts + history)
```

- **Frontend** (`frontend/`): SvelteKit, routes = `/` (upload), `/history`, `/analysis/[id]`, shared layout for auth/theme.
- **Backend** (`backend/main.py`): FastAPI. Every Gemini/yt-dlp/account/history operation is proxied through one local **MCP tool server** (`backend/mcp_server/`), auto-spawned by `main.py`.
- **Data**: SQLite (`backend/app.db`) — users, sessions, analyses (with per-topic done-state).
- **Docker**: `docker-compose.yml` builds both services; backend DB path is a mounted volume.

## Flow

```mermaid
flowchart TD
    Z[Sign up / Log in] -->|MCP: signup / login| A[Upload file OR paste URL]
    A --> B{Input type?}
    B -- URL --> C[MCP: fetch_video_details]
    C --> D{Captions?}
    D -- yes --> E[Transcript]
    D -- no --> F[yt-dlp: audio] --> G[Whisper] --> E
    B -- File --> H[FFmpeg] --> I[Whisper] --> E
    E --> J[MCP: summarize_transcript]
    J --> K[yt-dlp: related videos]
    K --> L[Roadmap saved to SQLite]
    L --> M{User action}
    M -- Explain --> N[MCP: explain_topic] --> L
    M -- Quiz me --> O[MCP: quiz_topic] --> L
    M -- Final Quiz --> P[MCP: quiz_overall] --> L
    M -- Mark done --> Q[MCP: update_done_topics] --> L
    M -- History --> R[MCP: list_history / get_history_item] --> L
    M -- Log out --> S[MCP: logout]
```

## MCP Tools

Every Gemini/yt-dlp call, and every account/history read or write, goes through one local MCP tool server (`backend/mcp_server/video_details_server.py`), auto-spawned by `main.py` on startup. FastAPI never touches Gemini, yt-dlp, or the database directly — it's a thin HTTP layer that calls these tools and returns the result. That means the same tools are callable by any MCP client, not just this app's own frontend.

| Tool | Args | What it does |
|---|---|---|
| `fetch_video_details` | `url` | Reads a video's existing captions/subtitles via `yt-dlp` — no video or audio download. Raises a distinct error if no captions exist, so the caller knows to fall back to Whisper. |
| `summarize_transcript` | `transcript`, `target_language?` | Sends the transcript to Gemini, gets back `intro`, `key_points`, and a nested `roadmap` of topics/sub-topics with examples. If `target_language` is set, the whole output is written in that language regardless of the transcript's own. |
| `explain_topic` | `heading`, `content`, `example?` | Asks Gemini to go deeper on one roadmap topic — context, nuance, common misconceptions — beyond what's already in `content`. |
| `quiz_topic` | `heading`, `content`, `example?` | Gemini generates a 5-question multiple-choice quiz scoped to just that topic, difficulty-tagged, code-aware if the topic has a code example. |
| `quiz_overall` | `roadmap`, `count` | Gemini generates a 10-15 question quiz spanning the whole roadmap, for the "Final Quiz" feature. |
| `signup` | `email`, `password` | Creates an account (password hashed + salted before storage) and returns a session token. |
| `login` | `email`, `password` | Verifies credentials and returns a fresh session token. |
| `logout` | `token` | Invalidates a session token. |
| `list_history` | `token` | Returns the *token owner's* saved analyses only — never another account's. |
| `get_history_item` | `token`, `analysis_id` | Returns one saved analysis by id, scoped to the token's account; errors if it belongs to someone else. |
| `update_done_topics` | `token`, `analysis_id`, `done_topics` | Overwrites which topics are marked done for one analysis, scoped the same way. |

Every account/history tool takes a `token` as its first argument, resolves it server-side to a `user_id`, and scopes the query to that user — the token is the only thing that ties a request to an account, so one account can never read or modify another's data.

## Sequence Diagram

```mermaid
sequenceDiagram
    actor User
    participant UI as SvelteKit
    participant API as FastAPI
    participant MCP as MCP Tools
    participant G as Gemini

    User->>UI: Sign up / Log in
    UI->>API: POST /api/auth/signup|login
    API->>MCP: signup / login
    MCP-->>API: token
    API-->>UI: token (stored, sent as Bearer)

    User->>UI: Analyze video
    UI->>API: POST /api/analyze (Bearer)
    API->>API: transcript (captions or Whisper)
    API->>MCP: summarize_transcript
    MCP->>G: generate roadmap
    G-->>MCP: roadmap
    MCP-->>API: roadmap
    API-->>UI: render + save to History

    User->>UI: Explain / Quiz me / Final Quiz
    UI->>API: POST /api/topic/... 
    API->>MCP: explain_topic / quiz_topic / quiz_overall
    MCP->>G: generate
    G-->>MCP: result
    MCP-->>API: result
    API-->>UI: show panel / quiz

    User->>UI: Mark done / View History
    UI->>API: PUT done-topics / GET history
    API->>MCP: update_done_topics / list_history / get_history_item
    MCP-->>API: data
    API-->>UI: update view

    User->>UI: Log out
    UI->>API: POST /api/auth/logout
    API->>MCP: logout
```

## Why Each Technology

| Tech | Role |
|---|---|
| **SvelteKit** | UI: upload, roadmap, history, quizzes |
| **FastAPI** | HTTP orchestrator, auth guard |
| **MCP** | Single tool surface for every Gemini/yt-dlp/account/history op |
| **yt-dlp** | Captions, audio download, related-video search — no API key |
| **FFmpeg** | Audio extraction from uploaded files |
| **Whisper** | Speech-to-text fallback (CPU) when no captions exist |
| **Gemini** | Roadmap generation, explanations, quizzes |
| **SQLite** | Accounts, sessions, saved analyses — one file, no extra service |

## Features

- Sign up / log in — private per-account history
- Upload a file **or** paste a URL; captions-first, Whisper fallback
- Roadmap: intro, key points, nested topics with examples, related links, real related YouTube videos
- Output language override (translate the roadmap regardless of source language)
- **Explain** (deeper AI breakdown) / **Quiz me** (5 Qs) / **Final Quiz** (10-15 Qs) — difficulty-tagged, code-aware
- Mark topics done → progress bar, persisted server-side per analysis
- Search/filter roadmap topics
- Dark mode
- Export analysis to Markdown
- Docker Compose for both services

## Project Structure

**Backend**
- `main.py` — FastAPI routes + auth guard; `python main.py` starts API + MCP server
- `mcp_server/video_details_server.py` — all MCP tools (see table above)
- `services/mcp_client.py` — FastAPI's client for the MCP server
- `services/db.py` — SQLite (users, sessions, analyses)
- `services/downloader.py`, `audio_extractor.py`, `transcriber.py` — transcript pipeline
- `services/summarizer.py`, `topic_assistant.py` — Gemini prompts
- `services/video_search.py` — related-video search
- `Dockerfile`, `.dockerignore`

**Frontend** (`frontend/src/`)
- `routes/+layout.svelte` — theme toggle, account bar, auth gate
- `routes/+page.svelte` — upload form
- `routes/history/+page.svelte` — past analyses
- `routes/analysis/[id]/+page.svelte` — roadmap, quizzes, export
- `lib/auth.svelte.ts`, `lib/theme.svelte.ts` — shared reactive state
- `lib/types.ts`, `lib/languages.ts`, `lib/textUtils.ts` — shared helpers
- `app.css` — all styles (shared across routes)
- `Dockerfile`, `.dockerignore`

**Root**: `docker-compose.yml`, `.env.example`

## Out of Scope

- No async job queues — processing is synchronous per request
- No password reset / email verification
- No streaming progress during analysis

## Running Locally

**Docker (both services):**
```bash
cp .env.example .env   # set GEMINI_API_KEY
docker compose up --build
```

**Manual:**
```bash
cd backend
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python main.py       # API + MCP server on :8000

cd frontend
npm install && npm run dev      # :5173
```

Requires `GEMINI_API_KEY` (`backend/.env`, free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)) and `ffmpeg` on `PATH` for local dev.

## Status

Full pipeline, accounts, per-user history, all Gemini/yt-dlp/account/history ops as MCP tools, dark mode, export, and Docker are all in place end-to-end.
