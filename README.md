````markdown
# Inbox Companion

Inbox Companion is a **local-first email assistant** that helps you move toward *Inbox Zero* without sending your mail to anyone else’s cloud.

- **Privacy-first:** Runs fully on your machine.
- **LLM-powered:** Uses a local LLM (via **Ollama** or any **OpenAI-compatible** endpoint) to summarize, label, and score mail.
- **Today:** Supports **ProtonMail** via **Proton Bridge**.
- **Tomorrow:** OX, Gmail, Yahoo (planned).

---

## Why & Goals

Email remains the backbone of many workflows — and also the biggest distraction. This project aims to:

- **Summarize** messages into quick bullets + key actions.
- Track **working memory** (facts, people, follow-ups, deadlines).
- Score mail with **urgency** and **importance**, deriving a **priority 0–100**.
- Suggest **labels** (work/personal/finance/newsletter/…).
- Keep everything **local** and **auditable**.

A **meta-goal** is to explore **LLM-driven development** at project scale:
- What collaboration patterns work?
- How do we iterate with diffs vs snapshots?
- How do we keep the assistant productive as the codebase grows?

---

## Status

**Milestone 0+** — usable skeleton with end-to-end:
**ingest → store → search → summarize → prioritize**.

- Proton Bridge ingest ✅
- SQLite + FTS5 ✅
- React UI (Recent, Search, Backlog) ✅
- Summaries, labels, urgency/importance, priority ✅
- Async job: **summarize all missing** ✅
- Next: outbound actions (**Generate Draft** to IMAP Drafts), richer extraction, more providers.

---

## Architecture

- **Backend:** FastAPI + SQLAlchemy + APScheduler  
  SQLite schema:
  - `message`, `message_body`, `message_analysis`
  - `label`, `message_label`
  - `memory_item` (for the assistant’s small “working memory”)
  
  Features:
  - IMAP over STARTTLS (Proton Bridge)
  - FTS5 full-text search
  - LLM calls via HTTP (Ollama / OpenAI-compatible)
  - Background jobs (batch summarize)

- **Frontend:** React + Vite + Tailwind  
  Views: Recent / Search / Backlog, per-message expansion and analysis cards.

- **Containers:** Docker Compose (backend, frontend).  
  Persistent DB is bind-mounted to `./state`.

---

## Screenshots & UI walkthrough

> **Note:** The images referenced below live in `docs/images/`.  
> If you don’t see them yet, create them by taking screenshots of the running app and placing them under those paths.

### Recent view
![Recent view](docs/images/recent.png)

- Left-to-right: unread/star/answered flags, sender, subject, snippet, date.
- Click a row to expand: preview body and access actions (Load Body, Summarize, Load Analysis).

### Message expanded (before summary)
![Message expanded](docs/images/message-expanded.png)

- **Load body** fetches the full text from SQLite (if present).
- **Summarize** calls your local LLM and stores the result.

### Analysis card (after summary)
![Analysis card](docs/images/analysis-card.png)

- **Bullets:** quick gist.
- **Key actions:** suggested to-dos.
- **Urgency/Importance:** numeric (0–5).
- **Priority:** derived score 0–100 (used in Backlog sort).
- **Labels:** applied and persisted.

### Backlog with priorities
![Backlog view](docs/images/backlog.png)

- Sorts by computed **priority**.
- Ideal to “clear the deck”: scan summaries, take action, archive.

### LLM connectivity
![Model ping](docs/images/model-ping.png)

- “LLM ping” shows available models and connectivity status.

---

## Quick Start

### 1) Configure Proton Bridge

- Install Proton Bridge and sign in.
- Copy and edit environment:

```bash
cp env_example.env .env
````

* Update `.env` with your Bridge IMAP credentials.
* Default Bridge listens on `1143` (STARTTLS).

### 2) Run locally (dev)

```bash
# Backend
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend
npm --prefix frontend install
npm --prefix frontend run dev

# Open
http://localhost:5173
```

### 3) Run via Docker

```bash
make up
# Backend:  http://localhost:8000
# Frontend: http://localhost:5173
```

SQLite DB persists at `./state/inbox.sqlite3`.

---

## Configuration (.env)

See `env_example.env` for the full list. Common settings:

```ini
# Proton Bridge IMAP over STARTTLS
IMAP_HOST=host.docker.internal
IMAP_PORT=1143
IMAP_USER=your_username
IMAP_PASS=your_password
IMAP_MAILBOX=INBOX
IMAP_USE_STARTTLS=true
IMAP_TLS_VERIFY=false  # enable in real use

# CORS (frontend dev)
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# SQLite
DB_PATH=/data/inbox.sqlite3

# Polling
POLL_INTERVAL_SECONDS=300
INITIAL_FETCH_LIMIT=50

# LLM
OLLAMA_URL=http://host.docker.internal:11434
LLM_MODEL_SUMMARY=deepseek-r1:8b
LLM_TIMEOUT_SECONDS=300

# State dir (prompts, db)
STATE_DIR=/state
```

> **LLM backends:** The app talks to **Ollama** by default. Any **OpenAI-compatible** endpoint on your network also works if it mimics the `/v1/chat/completions` API (adjust URL/token accordingly).

---

## Developer workflow (LLM-assisted)

This repo includes tools that make collaborating with an LLM practical as the project grows.

### Snapshots (for context sharing)

```bash
make full-snapshot        # → snapshot.txt (entire repo)
make backend-snapshot     # → snapshot-backend.txt
make frontend-snapshot    # → snapshot-frontend.txt
make meta-snapshot        # → snapshot-meta.txt
make pick-snapshot FILES="backend/src/inbox_backend/app/main.py frontend/src/App.tsx"
```

### API surface (signatures only)

```bash
make api                  # → api-snapshot.txt
```

These artifacts are great to paste into a chat so the LLM can reason about structure without needing all code.

---

## REST API: quick reference (curl)

All endpoints served by the backend at `http://localhost:8000`.

### Health & LLM

```bash
curl -s http://localhost:8000/healthz | jq
curl -s http://localhost:8000/api/llm/ping | jq
```

**Example `llm/ping` response**

```json
{
  "ok": true,
  "models": ["deepseek-r1:8b", "llama3.1:8b", "qwen2.5:7b"],
  "error": null
}
```

### Messages

```bash
# Recent
curl -s "http://localhost:8000/api/messages/recent?limit=20" | jq

# Search (FTS5 over subject/from/snippet/body-preview)
curl -s "http://localhost:8000/api/search?q=invoice&limit=50" | jq

# Full body
curl -s "http://localhost:8000/api/messages/123/body" | jq

# Analysis (summary + labels + metrics)
curl -s "http://localhost:8000/api/messages/123/analysis" | jq
```

**Example `messages/:id/analysis` response**

```json
{
  "message_id": 123,
  "analysis": {
    "version": 2,
    "lang": "en",
    "bullets": ["Monthly invoice from ACME", "Amount due: $1,240", "Payment link inside"],
    "key_actions": ["Pay by 2025-01-31", "Forward to accounting"],
    "urgency": 3,
    "importance": 4,
    "priority": 73,
    "labels": ["finance", "bill"],
    "confidence": 0.89,
    "truncated": false,
    "model": "deepseek-r1:8b",
    "token_usage": { "prompt": 1543, "completion": 302 },
    "notes": ""
  },
  "labels": ["finance", "bill"],
  "error": null
}
```

### Summarization

```bash
# Summarize one or more message IDs
curl -s -X POST http://localhost:8000/api/llm/summarize \
  -H 'Content-Type: application/json' \
  -d '{"ids":[123,124]}' | jq

# Summarize all missing analyses (async job)
curl -s -X POST "http://localhost:8000/api/llm/summarize_missing?limit=1000&only_unread=false" | jq
```

**Example `llm/summarize` response**

```json
{
  "results": [
    { "id": 123, "status": "ok", "skipped": false },
    { "id": 124, "status": "error", "error": "Ollama request failed: timeout" }
  ],
  "summary": { "ok": 1, "skipped": 0, "errors": 1 }
}
```

### Jobs (progress for summarize-all)

```bash
# List all jobs (newest first)
curl -s http://localhost:8000/api/llm/jobs | jq

# Filter by kind
curl -s "http://localhost:8000/api/llm/jobs?kind=summarize_missing" | jq

# Poll a job by ID
curl -s http://localhost:8000/api/llm/jobs/<job_id> | jq
```

**Example `llm/jobs` response**

```json
{
  "jobs": [
    {
      "job_id": "2b5bbee9cf0b4b57b8371865180eddc2",
      "kind": "summarize_missing",
      "created_at": "2025-01-04T12:34:56Z",
      "total": 120,
      "ok": 35,
      "skipped": 2,
      "errors": 1,
      "remaining": 82,
      "pct": 31.7,
      "status": "running",
      "note": null
    }
  ]
}
```

### Mail polling / backfill

```bash
# Trigger a quick poll
curl -s -X POST http://localhost:8000/api/refresh_now | jq

# Backfill older mail
curl -s -X POST http://localhost:8000/api/backfill \
  -H 'Content-Type: application/json' \
  -d '{"days": 7, "only_unseen": true}' | jq
```

### Labels & memory

```bash
# Labels
curl -s http://localhost:8000/api/labels | jq
curl -s -X POST http://localhost:8000/api/labels \
  -H 'Content-Type: application/json' \
  -d '{"name":"work","color":"#2563eb"}' | jq

# Memory (assistant working memory)
curl -s http://localhost:8000/api/memory | jq
curl -s -X POST http://localhost:8000/api/memory \
  -H 'Content-Type: application/json' \
  -d '{"kind":"fact","key":"team","value":"Astrophysics Group"}' | jq
```

---

## Frontend usage tips

* **Summarize (one):** Expand a row → click **Summarize**.
  A banner shows LLM progress; results persist into the DB.
* **Summarize visible:** In Recent/Search/Backlog → **Summarize visible** (top right).
  Runs a capped batch to keep the UI responsive.
* **Backlog:** Uses derived **priority** (0–100) to sort.
  Tweak labels/urgency/importance by running summaries again with a faster/cheaper model if desired.

---

## Implementation surface (current)

> Compact signature snapshots are generated with `make api`.
> See `api-snapshot.txt` for the up-to-date list.

### Backend: notable modules

* `db.py` — session lifecycle, migrations, FTS setup
* `imap_preview.py` — IMAP helpers + text extraction
* `repository.py` — data access (messages, bodies, analyses, labels, memory)
* `llm_client.py` — model calls (Ollama/OpenAI-compatible), prompts, timeouts
* `main.py` — FastAPI app, routes, background jobs, prompt composition

### Frontend: notable modules

* `src/lib/api.ts` — REST client wrappers
* `src/App.tsx` — UI (Recent, Search, Backlog, analysis cards)

---

## Security & Privacy

* Runs **entirely local** by default (Bridge + Ollama on `localhost`).
* **No third-party storage**; SQLite in `./state`.
* **Strict JSON contracts** for LLM output; reasoning is not stored.
* **STARTTLS** for IMAP; enable certificate verification for real use (`IMAP_TLS_VERIFY=true`).

---

## Roadmap

* ✉️ **Generate Draft** into IMAP Drafts.
* 🏷️ Smarter labels, auto-rules.
* 🔁 Ongoing learning from memory items.
* 🧪 Better HTML→text, attachment awareness.
* 📬 Providers: OX, Gmail, Yahoo.

---

## Contributing

* Use `make full-snapshot` or `make api` when asking the LLM to help — these artifacts keep context tight.
* Prefer **surgical edits** when patching code during review.
* PRs welcome (tests and screenshots appreciated).

---

## License

MIT


