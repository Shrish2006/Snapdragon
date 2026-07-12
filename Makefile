# SafeGuard — project-wide build, test, and deploy commands.
# GNU Make. Works on Linux and Windows (Git Bash / WSL).
#
# Dev mode (docker compose with no -f flags) auto-merges
#   docker-compose.yml + compose.override.yml
# giving you hot-reload, volume mounts, DEBUG logs.
#
# Prod targets pass -f docker-compose.yml explicitly — no overrides.

IMAGE_REGISTRY ?= ghcr.io/shrish2006/snapdragon
IMAGE_TAG      ?= latest

# ═══════════════════════════════════════════════════════════════════════
# Dev environment (docker compose auto-merges compose.override.yml)
# ═══════════════════════════════════════════════════════════════════════

.PHONY: dev
dev:  ## Start full dev stack (hot-reload, volume mounts, DEBUG logs)
	docker compose up --build -d

.PHONY: dev-down
dev-down:  ## Stop dev stack
	docker compose down

.PHONY: dev-logs
dev-logs:  ## Tail dev stack logs
	docker compose logs -f

.PHONY: dev-restart
dev-restart:  ## Rebuild and restart dev stack
	docker compose up --build -d --force-recreate

.PHONY: dev-ps
dev-ps:  ## List dev service status
	docker compose ps

.PHONY: dev-sh-gateway
dev-sh-gateway:  ## Open shell in dev gateway container
	docker compose exec gateway bash

.PHONY: dev-sh-app
dev-sh-app:  ## Open shell in dev app container
	docker compose exec app sh


# ── Light dev (no ML containers, mock clients + seed data) ──────────

.PHONY: dev-light
dev-light:  ## Start app + gateway in dev mode, skip ML (mock + seed)
	docker compose -f docker-compose.light.yml up --build -d
	@echo "Waiting for gateway to accept connections..."
	-@until docker compose -f docker-compose.light.yml exec -T gateway \
		python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" \
		2>/dev/null; do sleep 1; done
	uv run --project gateway python scripts/seed.py

.PHONY: dev-light-down
dev-light-down:  ## Stop light dev stack
	docker compose -f docker-compose.light.yml down

.PHONY: dev-light-logs
dev-light-logs:  ## Tail light dev stack logs
	docker compose -f docker-compose.light.yml logs -f

.PHONY: dev-light-restart
dev-light-restart:  ## Rebuild and restart light dev stack
	docker compose -f docker-compose.light.yml up --build -d --force-recreate
	@echo "Waiting for gateway..."
	-@until docker compose -f docker-compose.light.yml exec -T gateway \
		python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" \
		2>/dev/null; do sleep 1; done
	uv run --project gateway python scripts/seed.py
# ═══════════════════════════════════════════════════════════════════════
# Database
# ═══════════════════════════════════════════════════════════════════════

.PHONY: db-up
db-up:  ## Start postgres + redis only (for local gateway development)
	docker compose up -d postgres redis

.PHONY: db-init
db-init: db-up  ## Start postgres, wait for healthy, then run schema init
	@echo "Waiting for postgres to accept connections..."
	-@until docker compose exec -T postgres pg_isready -U safeguard 2>/dev/null; do sleep 1; done
	docker compose run --rm --no-deps gateway \
		python -c "import asyncio; from gateway.infrastructure.persistence.postgres import PostgresEventStore; asyncio.run(PostgresEventStore('postgresql://safeguard:safeguard@postgres:5432/safeguard').initialize()); print('Schema ready.')"

.PHONY: db-reset
db-reset:  ## Destroy and recreate postgres volume (all data lost)
	docker compose down -v postgres
	docker compose up -d postgres
	@echo "Postgres restarted with fresh volume. Run 'make db-init' or 'make dev' to create schema."

.PHONY: seed
seed:  ## Seed dev database with sample telemetry (default: via gateway API)
	uv run --project gateway python scripts/seed.py $(ARGS)

.PHONY: seed-db
seed-db:  ## Seed directly into Postgres (bypasses gateway API)
	uv run --project gateway python scripts/seed.py --direct-db

.PHONY: seed-reset
seed-reset:  ## Wipe and reseed dev database
	uv run --project gateway python scripts/seed.py --direct-db --clear

# ═══════════════════════════════════════════════════════════════════════
# Local development (outside Docker — run services directly on host)
# ═══════════════════════════════════════════════════════════════════════

.PHONY: install
install: install-gateway install-app  ## Install all dependencies

.PHONY: install-gateway
install-gateway:  ## Install gateway Python dependencies (uv sync)
	uv sync --project gateway

.PHONY: install-app
install-app:  ## Install app Node.js dependencies (pnpm)
	cd app && pnpm install --frozen-lockfile

.PHONY: run-gateway
run-gateway:  ## Start gateway locally (uvicorn, hot-reload)
	uv run --project gateway uvicorn gateway.main:app --host 0.0.0.0 --port 8080 --reload

.PHONY: run-app
run-app:  ## Start app dev server (Next.js, hot-reload)
	cd app && pnpm dev

# ═══════════════════════════════════════════════════════════════════════
# Production compose (explicit -f, no override file)
# ═══════════════════════════════════════════════════════════════════════

.PHONY: up
up:  ## Start all services (production mode)
	docker compose -f docker-compose.yml up --build -d

.PHONY: down
down:  ## Stop all services
	docker compose -f docker-compose.yml down

.PHONY: logs
logs:  ## Tail logs from all services
	docker compose -f docker-compose.yml logs -f

.PHONY: ps
ps:  ## List service status
	docker compose -f docker-compose.yml ps

.PHONY: restart
restart:  ## Rebuild and restart all services
	docker compose -f docker-compose.yml up --build -d --force-recreate

# ═══════════════════════════════════════════════════════════════════════
# Docker images
# ═══════════════════════════════════════════════════════════════════════

.PHONY: build
build: build-gateway build-app build-ml  ## Build all Docker images

.PHONY: build-gateway
build-gateway:  ## Build gateway Docker image
	docker build -t $(IMAGE_REGISTRY)/gateway:$(IMAGE_TAG) ./gateway

.PHONY: build-app
build-app:  ## Build app Docker image
	docker build -t $(IMAGE_REGISTRY)/app:$(IMAGE_TAG) ./app

.PHONY: build-ppe
build-ppe:  ## Build ppe-detection Docker image
	docker build -t $(IMAGE_REGISTRY)/ppe-detection:$(IMAGE_TAG) -f ai_ml/ppe_detection/Dockerfile ./ai_ml

.PHONY: build-fall
build-fall:  ## Build fall-detection Docker image
	docker build -t $(IMAGE_REGISTRY)/fall-detection:$(IMAGE_TAG) -f ai_ml/fall_detection/Dockerfile ./ai_ml

.PHONY: build-ml
build-ml: build-ppe build-fall  ## Build both ML service images

.PHONY: push-gateway
push-gateway:  ## Push gateway image to registry
	docker push $(IMAGE_REGISTRY)/gateway:$(IMAGE_TAG)

.PHONY: push-app
push-app:  ## Push app image to registry
	docker push $(IMAGE_REGISTRY)/app:$(IMAGE_TAG)

# ═══════════════════════════════════════════════════════════════════════
# Quality gates
# ═══════════════════════════════════════════════════════════════════════

.PHONY: lint
lint: lint-python lint-app  ## Run all linters

.PHONY: lint-python
lint-python:  ## Ruff check all Python sources
	python -m ruff check gateway ai_ml tests scripts

.PHONY: lint-app
lint-app:  ## ESLint check the app
	cd app && pnpm lint

.PHONY: format
format: format-python format-app  ## Format all sources

.PHONY: format-python
format-python:  ## Ruff format all Python sources
	python -m ruff format gateway ai_ml tests scripts

.PHONY: format-app
format-app:  ## Prettier format the app
	cd app && pnpm format

.PHONY: typecheck
typecheck:  ## TypeScript type-check the app
	cd app && pnpm exec tsc --noEmit

.PHONY: test
test:  ## Run all tests
	python -m pytest

.PHONY: test-gateway
test-gateway:  ## Run gateway tests only
	python -m pytest tests/gateway/

.PHONY: check
check: lint-python test  ## Python quality gate (lint + test)

.PHONY: quality
quality: lint test typecheck  ## Full quality gate

# ═══════════════════════════════════════════════════════════════════════
# Housekeeping
# ═══════════════════════════════════════════════════════════════════════

.PHONY: clean
clean:  ## Remove containers/volumes, Python caches, build artifacts
	-docker compose down -v --rmi local
	python -c "import shutil,pathlib; [shutil.rmtree(p,ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [shutil.rmtree(p,ignore_errors=True) for p in [pathlib.Path('.pytest_cache'),pathlib.Path('.ruff_cache')]]"

.PHONY: nuke
nuke:  ## Nuclear clean: remove ALL Docker resources and generated files
	-docker compose down -v --rmi all --remove-orphans
	python -c "import shutil,pathlib; r=pathlib.Path('.'); [shutil.rmtree(d,ignore_errors=True) for d in list(r.rglob('__pycache__'))+list(r.rglob('.next'))+list(r.rglob('node_modules'))+[p for p in r.rglob('.venv') if p != r]]"

.PHONY: help
help:  ## Show this help
	@grep -Eh '^[a-zA-Z._-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
