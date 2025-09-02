SHELL := /bin/bash

.PHONY: help dev up down logs rv-snapshot

help:
	@echo "Targets:"
	@echo "  dev         - run backend (uvicorn) and frontend (vite) locally"
	@echo "  up          - docker compose up (prod-like)"
	@echo "  down        - docker compose down"
	@echo "  logs        - docker compose logs -f"
	@echo "  rv-snapshot - write text snapshot to snapshot.txt"

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

rv-snapshot:
	@SNAPSHOT_EXCLUDES="node_modules .venv dist out" tools/repo_view/snapshot.sh > snapshot.txt
	@echo "[rv] wrote snapshot.txt"

