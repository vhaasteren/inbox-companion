# Inbox Companion

Local-first email triage that pulls your mail from Proton Bridge (IMAP), stores it in a tiny SQLite database, and gives you a fast UI with LLM-powered summaries, labels, and a backlog view — all running on your own machine.

## Why?

Inbox zero is great; sending your mail to someone else’s cloud isn’t. Inbox Companion keeps the entire loop local:

* **Ingest:** IMAP over STARTTLS from Proton Bridge
* **Store:** SQLite (with FTS5) on disk in `./state/`
* **Triage:** React UI for search, flags, and quick reading
* **Assist:** Local LLM via Ollama to summarize, label, and prioritize

## What it does today

* **Pull & persist mail**

  * Poll one or many mailboxes (configurable) via IMAP/STARTTLS
  * Store headers + text body in SQLite; full-text search via FTS5
  * Track flags (unread, answered, starred) and keep them in sync

* **Search & browse**

  * “Recent” list with sender/subject/snippet, flags, and previews
  * “Search” over subject/from/snippet/body preview (FTS5)

* **Backlog triage**

  * LLM summaries with bullets, key actions, labels, and numeric **urgency/importance**
  * Derived **priority (0–100)** to sort the backlog
  * Per-message label mapping and a small “living prompt memory” store
  * Works against your **local Ollama** server (no cloud)

* **Quality-of-life**

  * One-click “Refresh now” and configurable polling
  * “Backfill…” older mail (SINCE N days; optional UNSEEN; limit)
  * LLM connectivity check (model list)

> **Status:** “Milestone 0+” — usable skeleton with end-to-end ingest → store → search → summarize → prioritize. Next milestones will add outbound actions (e.g., **Generate Draft** that appends to IMAP Drafts).

## Architecture at a glance

* **Backend:** FastAPI + SQLAlchemy + APScheduler

  * IMAP client (STARTTLS; toggle certificate verification for Bridge)
  * SQLite schema: `message`, `message_body`, `message_analysis`, `label`, `message_label`, `memory_item`
  * FTS5 virtual table + triggers to index subjects/from/snippets/previews
  * LLM: HTTP to **Ollama** (default model configurable), strict JSON contract
  * REST endpoints for messages, search, backlog, labels, memory, and LLM

* **Frontend:** React + Vite + Tailwind

  * Recent/Search/Backlog modes
  * Row expansion → preview, load full body, summarize, show analysis & labels
  * Batch “Summarize visible” with progress banner

* **Containerization:** `docker-compose.yml` starts backend and frontend; persistent DB lives in `./state` (bind-mount to `/data`).

## Quick start

### Local (host)

1. Duplicate and fill env:

   ```bash
   cp env_example.env .env   # put your Proton Bridge IMAP creds here
   ```

   Make sure Proton Bridge is running (default IMAP 1143, STARTTLS).

2. Run backend & frontend (two terminals):

   ```bash
   # Backend
   python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

   # Frontend
   npm --prefix frontend install
   npm --prefix frontend run dev
   ```

   Open: `http://localhost:5173`

### Docker

```bash
make up
# Frontend: http://localhost:5173
```

By default the backend binds SQLite to `./state/inbox.sqlite3` on the host.

## Configuration

All via `.env` (see `env_example.env`):

* IMAP host/port/user/pass; `IMAP_USE_STARTTLS=true`
* `IMAP_MAILBOX` or `IMAP_MAILBOXES=INBOX,Newsletters,…`
* TLS verification toggle (`IMAP_TLS_VERIFY`) for Bridge testing
* Polling interval (`POLL_INTERVAL_SECONDS`)
* DB path (`DB_PATH=/data/inbox.sqlite3`)
* Ollama base URL (`OLLAMA_URL`)

## Developer tools

* **Repo snapshots** (great for PRs / reviews):

  ```bash
  make full-snapshot        # snapshot.txt (entire repo)
  make backend-snapshot     # backend only
  make frontend-snapshot    # frontend only
  make meta-snapshot        # everything except backend/frontend
  make pick-snapshot FILES="path1 path2"   # targeted
  ```
* **API surface** (compact function/method signatures):

  ```bash
  make api                  # -> api-snapshot.txt
  ```

## Security & privacy

* All network calls are **local** by default: Proton Bridge on localhost; Ollama on localhost.
* Mail is stored in **SQLite on your machine**; no third-party cloud.
* STARTTLS used for IMAP; certificate verification is configurable (enable it in real use).
* LLM prompt builder enforces **strict JSON** and redacts reasoning.

## Roadmap (short)

* ✉️ **Generate Draft** (append to IMAP Drafts)
* 🏷️ Smarter label taxonomy & rules
* 🔁 Incremental learning from your “memory” store
* 🧪 Better HTML → text extraction & attachment awareness

---

*If you just want to try it: bring up Proton Bridge, copy `.env`, `make up`, and open `http://localhost:5173`.*



## Old Setup (below is old version)

1. Create `.env` from `.env.example` and fill in your Proton Bridge IMAP creds.
2. Ensure Proton Bridge is running locally (IMAP 1143 STARTTLS).
3. Local dev:
   - Backend: `python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000`
   - Frontend: `npm --prefix frontend install && npm --prefix frontend run dev`

Or via Docker:

```bash
make up
open http://localhost:5173
```

## Snapshot

You can now snapshot different parts of the repo:

```bash
# Full repo (default)
make full-snapshot        # -> snapshot.txt

# Just the backend
make backend-snapshot     # -> snapshot-backend.txt

# Just the frontend
make frontend-snapshot    # -> snapshot-frontend.txt

# Everything except backend/frontend (scaffolding, configs, tools, etc.)
make meta-snapshot        # -> snapshot-meta.txt

# Back-compat alias
make rv-snapshot          # -> snapshot.txt

### API surface snapshot

Generate a compact “API view” of function/method signatures:

```bash
make api
# -> api-snapshot.txt

### Picked-file snapshot

Output just the files you specify (same format as the full snapshot):

```bash
# Inline list
make pick-snapshot FILES="backend/src/inbox_backend/app/db.py frontend/src/lib/api.ts"

# From list file
make pick-snapshot FILELIST=filelist.txt

# Or via stdin
printf "%s\n" backend/src/inbox_backend/app/main.py frontend/src/App.tsx | make pick-snapshot


## Data persistence

The backend writes its SQLite DB to `/data` inside the container. In `docker-compose.yml` this
is bind-mounted to `./state` on the host:

```yaml
volumes:
  - ./state:/data


## Next steps
- Add “Generate draft” button that APPENDs to IMAP Drafts.
