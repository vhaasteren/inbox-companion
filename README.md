# Inbox Companion

Inbox Companion is a **local-first email assistant** that helps you move toward *Inbox Zero* without giving your mail to someone else’s cloud.  
It integrates with [ProtonMail](https://proton.me) (via Proton Bridge) today, with planned support for OX, Gmail, and Yahoo.  

The assistant uses a **locally running LLM** (via [Ollama](https://ollama.ai) or any OpenAI-compatible API endpoint on your network).  
All summaries, labels, and priorities are computed **on your own machine**.  

---

## Motivation

Email is still the main workflow tool for many professionals — but it’s noisy.  
We want an assistant that:

- Summarizes incoming mail into bullets and key actions.
- Tracks tasks, follow-ups, and deadlines in a “working memory”.
- Scores each mail on **urgency** and **importance**, computing a priority 0–100.
- Suggests labels (work, personal, finance, …).
- Keeps everything **private**: no third-party cloud, no server-side AI.

A **meta-goal** of this repo is to test **LLM-driven development** workflows.  
We use repo “snapshots” and API surface summaries to collaborate with LLMs as the project grows.

---

## Current Status

- **Milestone 0+:**  
  End-to-end ingest → store → search → summarize → prioritize, fully local.
- Supported email service: **ProtonMail** (via Proton Bridge).  
- Backlog triage works with summaries, labels, urgency/importance, and priority.  
- SQLite persistence with full-text search (FTS5).  
- React UI with recent/search/backlog views.  
- Background jobs for “summarize all missing”.  

Next milestone: add **outbound actions** (e.g., generate draft into IMAP Drafts).

---

## Architecture

- **Backend:** FastAPI + SQLAlchemy + APScheduler
  - IMAP client over STARTTLS (with Proton Bridge).
  - SQLite schema (`message`, `message_body`, `message_analysis`, `label`, `memory_item`).
  - LLM calls via HTTP → Ollama (configurable model, strict JSON contract).
  - REST endpoints for messages, backlog, labels, memory, jobs.

- **Frontend:** React + Vite + Tailwind
  - Modes: Recent / Search / Backlog.
  - Expand rows for preview, full body, analysis.
  - One-click “Summarize visible” with progress banner.

- **Containerization:** Docker Compose with two services:
  - Backend (bind-mounts `./state/inbox.sqlite3`).
  - Frontend (Vite dev server).

---

## Workflow & Tooling

This repo is also an experiment in **LLM-driven coding workflows**:

- **Snapshots:**  
  Generate repo or partial snapshots to feed into LLM context.  
  ```bash
  make full-snapshot        # entire repo → snapshot.txt
  make backend-snapshot     # backend only
  make frontend-snapshot    # frontend only
  make meta-snapshot        # everything except backend/frontend
  make pick-snapshot FILES="backend/src/app/main.py frontend/src/App.tsx"
  ```

* **API surface:**
  Compact list of function/method signatures.

  ```bash
  make api   # → api-snapshot.txt
  ```

These tools help keep ChatGPT/Ollama in sync with project state.

---

## Quick Start

### 1. Configure Proton Bridge

* Install and log in to Proton Bridge.

* Copy and edit the env file:

  ```bash
  cp env_example.env .env
  ```

* Update `.env` with your Proton Bridge IMAP credentials.
  Default Bridge port is `1143` with STARTTLS.

### 2. Run Locally

```bash
# Backend
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend
npm --prefix frontend install
npm --prefix frontend run dev

# Open UI
http://localhost:5173
```

### 3. Run via Docker

```bash
make up
# Backend → http://localhost:8000
# Frontend → http://localhost:5173
```

SQLite DB is persisted in `./state/inbox.sqlite3`.

---

## Configuration

Environment variables (see `env_example.env`):

* IMAP: `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASS`, `IMAP_MAILBOXES`
* TLS: `IMAP_USE_STARTTLS=true`, `IMAP_TLS_VERIFY`
* DB: `DB_PATH=/data/inbox.sqlite3`
* Polling: `POLL_INTERVAL_SECONDS=300`
* LLM:

  * `OLLAMA_URL=http://host.docker.internal:11434`
  * `LLM_MODEL_SUMMARY=deepseek-r1:8b`
  * `LLM_TIMEOUT_SECONDS=300`

---

## Backend API

The backend exposes a JSON REST API. Below are common `curl` commands.

### Health

```bash
curl -s http://localhost:8000/healthz | jq
curl -s http://localhost:8000/api/llm/ping | jq
```

### Messages

```bash
# Recent
curl -s "http://localhost:8000/api/messages/recent?limit=20" | jq

# Search
curl -s "http://localhost:8000/api/search?q=invoice&limit=50" | jq

# Full body
curl -s "http://localhost:8000/api/messages/123/body" | jq

# Analysis
curl -s "http://localhost:8000/api/messages/123/analysis" | jq
```

### Summarization

```bash
# Summarize one or more
curl -s -X POST http://localhost:8000/api/llm/summarize \
  -H 'Content-Type: application/json' \
  -d '{"ids": [123, 124]}' | jq

# Summarize all missing (async job)
curl -s -X POST "http://localhost:8000/api/llm/summarize_missing?limit=1000&only_unread=false" | jq
```

### Jobs

```bash
# List all jobs
curl -s http://localhost:8000/api/llm/jobs | jq

# Filter by kind
curl -s "http://localhost:8000/api/llm/jobs?kind=summarize_missing" | jq

# Job progress
curl -s http://localhost:8000/api/llm/jobs/<job_id> | jq
```

### Mail Polling

```bash
# Refresh now
curl -s -X POST http://localhost:8000/api/refresh_now | jq

# Backfill older mail
curl -s -X POST http://localhost:8000/api/backfill \
  -H 'Content-Type: application/json' \
  -d '{"days": 7, "only_unseen": true}' | jq
```

### Labels & Memory

```bash
# Labels
curl -s http://localhost:8000/api/labels | jq
curl -s -X POST http://localhost:8000/api/labels \
  -H 'Content-Type: application/json' \
  -d '{"name": "work", "color": "#0066ff"}' | jq

# Memory
curl -s http://localhost:8000/api/memory | jq
curl -s -X POST http://localhost:8000/api/memory \
  -H 'Content-Type: application/json' \
  -d '{"kind": "fact", "key": "team", "value": "Astrophysics Group"}' | jq
```

---

## Security & Privacy

* All network calls are local: Proton Bridge and Ollama run on `localhost`.
* No third-party cloud storage.
* SQLite DB lives in `./state/`.
* LLM prompts enforce strict JSON and redact reasoning.
* STARTTLS for IMAP; TLS verification configurable (enable in real use).

---

## Roadmap

* ✉️ Generate Draft (append to IMAP Drafts).
* 🏷️ Smarter label taxonomy & auto-labeling.
* 🔁 Incremental learning from memory store.
* 🧪 Richer text extraction, attachment awareness.
* 📬 Support for Gmail, OX, Yahoo.

---

*Try it today: run Proton Bridge, copy `.env`, `make up`, open [http://localhost:5173](http://localhost:5173).*
