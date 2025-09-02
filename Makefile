SHELL := /bin/bash

.PHONY: help dev up down logs rv-snapshot full-snapshot backend-snapshot frontend-snapshot meta-snapshot api pick-snapshot

help:
	@echo "Targets:"
	@echo "  dev                - run backend (uvicorn) and frontend (vite) locally"
	@echo "  up                 - docker compose up (prod-like)"
	@echo "  down               - docker compose down"
	@echo "  logs               - docker compose logs -f"
	@echo "  full-snapshot      - write full repo snapshot to snapshot.txt"
	@echo "  backend-snapshot   - write backend-only snapshot to snapshot-backend.txt"
	@echo "  frontend-snapshot  - write frontend-only snapshot to snapshot-frontend.txt"
	@echo "  meta-snapshot      - write 'meta' snapshot (everything except backend/frontend) to snapshot-meta.txt"
	@echo "  api                - write function signature snapshot to api-snapshot.txt"
	@echo "  rv-snapshot        - alias of full-snapshot"

# Local developer workflow (outside docker)
# Backend: python -m uvicorn backend.app.main:app --reload
# Frontend: npm --prefix frontend run dev

DEV_BACKEND ?= backend

dev:
	@echo "[dev] starting backend and frontend (run in separate terminals)"
	@echo "[dev] 1) Backend: python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000"
	@echo "[dev] 2) Frontend: npm --prefix frontend install && npm --prefix frontend run dev"

up:
	docker compose up -d --build
	docker compose ps

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

# --- Snapshots ---------------------------------------------------------------
# Notes:
# - SNAPSHOT_EXCLUDES: space-separated tokens (dirs or globs) to exclude
# - SNAPSHOT_PATHS:    space-separated roots to include (limits snapshot to these)
# - INCLUDE_UNTRACKED=1 keeps untracked-but-not-ignored files
#
# We keep *.patch excluded by default here to avoid accidental leakage.

full-snapshot:
	@SNAPSHOT_EXCLUDES="node_modules .venv dist out state *.patch" \
		tools/repo_view/snapshot.sh > snapshot.txt
	@echo "[rv] wrote snapshot.txt"

backend-snapshot:
	@SNAPSHOT_PATHS="backend" SNAPSHOT_EXCLUDES="node_modules .venv dist out *.patch" \
		tools/repo_view/snapshot.sh > snapshot-backend.txt
	@echo "[rv] wrote snapshot-backend.txt"

frontend-snapshot:
	@SNAPSHOT_PATHS="frontend" SNAPSHOT_EXCLUDES="node_modules .venv dist out *.patch" \
		tools/repo_view/snapshot.sh > snapshot-frontend.txt
	@echo "[rv] wrote snapshot-frontend.txt"

meta-snapshot:
	@SNAPSHOT_EXCLUDES="node_modules .venv dist out *.patch backend frontend" \
		tools/repo_view/snapshot.sh > snapshot-meta.txt
	@echo "[rv] wrote snapshot-meta.txt"

# Backwards-compatible alias
rv-snapshot: full-snapshot

# --- API surface snapshot ----------------------------------------------------
# Requirements:
# - Backend: Python 3.11+ (we use ast.unparse; your Dockerfile uses 3.12)
# - Frontend: Node 20+ and devDependency "typescript" (already in frontend/package.json)
#
# The target runs both extractors and merges outputs into api-snapshot.txt.

## pick-snapshot
## Usage:
##   make pick-snapshot FILES="a b c"
##   make pick-snapshot FILELIST=paths.txt
##   echo -e "a\nb\nc" | make pick-snapshot
api:
	@python3 tools/api_surface/py_api.py backend/src > .api-backend.tmp || true
	@bash -lc 'if [ ! -f frontend/node_modules/typescript/lib/typescript.js ]; then \
		echo "[api] installing TypeScript in frontend/…"; \
		npm --prefix frontend install --silent --no-audit --no-fund; \
	fi'
	@node tools/api_surface/ts_api.mjs frontend/src > .api-frontend.tmp || true
	@{ \
		echo "### Backend API (Python)"; \
		if [ -s .api-backend.tmp ]; then cat .api-backend.tmp; else echo "(no output)"; fi; \
		echo; echo "### Frontend API (TypeScript)"; \
		if [ -s .api-frontend.tmp ]; then cat .api-frontend.tmp; else echo "(no output)"; fi; \
	} > api-snapshot.txt
	@rm -f .api-backend.tmp .api-frontend.tmp
	@echo "[rv] wrote api-snapshot.txt"

pick-snapshot:
	@tools/repo_view/partial_snapshot.sh ${FILES} > snapshot-pick.txt || true
	@echo "[rv] wrote snapshot-pick.txt"
