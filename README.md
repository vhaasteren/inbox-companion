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

```bash
make rv-snapshot
# Outputs snapshot.txt at repo root
```

## Next steps
- Add SQLite + polling worker and store summaries/priorities.
- Add “Generate draft” button that APPENDs to IMAP Drafts.
