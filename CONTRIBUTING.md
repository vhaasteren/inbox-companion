# Contributing to Inbox Companion

Thanks for your interest in improving **Inbox Companion** — a local-first, privacy-first email assistant powered by local LLMs.

We welcome issues, PRs, ideas, and docs fixes. If you get stuck, open an issue with as much context as you can (logs, screenshots, steps).

---

## Quick start (dev)

### Prerequisites

* **Proton Bridge** running and logged in (IMAP over STARTTLS)
* **Python 3.11+**, **Node 18+**
* (Optional) **Docker** and **Docker Compose**
* (Optional) **Ollama** (or any OpenAI-compatible endpoint)

### Setup

```bash
# 1) Clone
git clone https://github.com/vhaasteren/inbox-companion.git
cd inbox-companion

# 2) Env
cp env_example.env .env
# Edit .env to match your Proton Bridge + LLM setup

# 3) Backend (dev)
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

# 4) Frontend (dev)
npm --prefix frontend install
npm --prefix frontend run dev
# App: http://localhost:5173  Backend: http://localhost:8000
```

### Docker (one command)

```bash
make up
# DB persists at ./state/inbox.sqlite3
```

---

## Where to help first

We label bite-sized issues as **`good-first-issue`** and broader ones as **`help-wanted`**. A few high-impact areas:

* Generate Drafts to IMAP **Drafts** (outbound)
* Better HTML→text extraction + attachments awareness
* Provider adapters (OX, Gmail, Yahoo)
* Testing & CI hardening
* UI polish and accessibility

---

## Project architecture (bird’s-eye)

* **Backend:** FastAPI + SQLAlchemy + APScheduler
  SQLite tables: `message`, `message_body`, `message_analysis`, `label`, `message_label`, `memory_item`.
  IMAP (Proton Bridge), FTS5 search, LLM calls (Ollama / OpenAI-compatible), background jobs.
* **Frontend:** React + Vite + Tailwind (Recent, Search, Backlog views).
* **State:** SQLite in `./state`, bind-mounted in Docker.

See the README for endpoints & example payloads.

---

## Coding standards

### Python

This is more like a wishlist for now, we did not actually adhere to this

* Format with **black**; lint with **ruff** (or flake8 if you prefer).
* Type hints encouraged; run **mypy** where practical.
* Docstrings: PEP-257 style; keep them concise and useful.


### TypeScript / React

Wishlist:

* Format with **prettier**, lint with **eslint**.


### Commit style

* Clear, imperative commit messages:
  `feat(backend): add summarize_missing job API`
  `fix(frontend): debounce search input`
* Small PRs over large ones. Include before/after screenshots for UI changes.

---

## Tests

* (If you add tests) put them under `backend/tests/` and `frontend/src/__tests__/`.
* Prefer unit tests for pure logic and light integration tests for endpoints.
* Keep fixtures small and anonymized.

---

## Running the LLM

* Default: **Ollama** at `http://host.docker.internal:11434` (configurable in `.env`).
* You can also point to any **OpenAI-compatible** endpoint that implements `/v1/chat/completions`.
* Keep responses within the JSON contract used by the backend; errors should not crash the job.

---

## Snapshots & API surface (for collaborating)

When proposing non-trivial changes, it helps to attach fresh snapshots:

```bash
make full-snapshot        # → snapshot.txt (entire repo)
make api                  # → api-snapshot.txt (function/class signatures)
```

These artifacts let reviewers (and AI assistants) reason about structure without pulling the entire tree.

---

## Issue guidelines

* **Bugs:** steps to reproduce, expected/actual, logs (backend stdout), screenshots.
* **Features:** motivation, rough UX, minimal API sketch.
* **Performance:** dataset size, timings, hardware.

We’re friendly to drafts — open early, refine together.

---

## Pull request checklist

Not strict about this until we enforce code quality

* [ ] Code runs locally (backend +/or frontend)
* [ ] Lints/formatters pass
* [ ] Tests added/updated (where it makes sense)
* [ ] README/Docs updated if behavior or config changed
* [ ] Screenshots for UI changes

---

## Community

* Please be respectful.
* Consider enabling **GitHub Discussions** for Q\&A/ideas if you want (repo Settings → Features → “Set up discussions”). ([GitHub Docs][4])

---

## License

By contributing, you agree your contributions are licensed under the project’s **MIT** license.

---

If you want, I can also:

* open a few **`good-first-issue`** candidates (based on your current code),
* draft a **Show HN** post,
* and sketch a minimal **CI** (lint + type-check) workflow you can paste into `.github/workflows/ci.yml`.

[1]: https://docs.github.com/articles/classifying-your-repository-with-topics?utm_source=chatgpt.com "Classifying your repository with topics"
[2]: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository?utm_source=chatgpt.com "Customizing your repository"
[3]: https://docs.github.com/en/get-started/exploring-projects-on-github/saving-repositories-with-stars?utm_source=chatgpt.com "Saving repositories with stars"
[4]: https://docs.github.com/discussions/quickstart?utm_source=chatgpt.com "Quickstart for GitHub Discussions"

