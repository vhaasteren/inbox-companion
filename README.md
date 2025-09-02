# Inbox Companion (Milestone 0)

Minimal skeleton that:
- connects to Proton Bridge via IMAP STARTTLS using credentials from `.env`,
- exposes `/api/mail/preview` to list the latest subjects,
- renders them in a tiny React UI.

## Setup

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


## Data persistence

The backend writes its SQLite DB to `/data` inside the container. In `docker-compose.yml` this
is bind-mounted to `./state` on the host:

```yaml
volumes:
  - ./state:/data


## Next steps
- Add “Generate draft” button that APPENDs to IMAP Drafts.
