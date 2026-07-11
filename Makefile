# SafeGuard — project-wide build, test, and deploy commands.
# See ci.yml for CI-equivalent steps; this file is the local-dev analogue.
# GNU Make only — no other make implementations tested.

IMAGE_REGISTRY ?= ghcr.io/shrish2006/snapdragon
IMAGE_TAG      ?= latest
COMPOSE_FILE   ?= docker-compose.yml

# ── Python (gateway + ai_ml) ────────────────────────────────────────────

.PHONY: install-gateway
install-gateway:  ## Install gateway Python dependencies (uv sync)
	uv sync --project gateway

.PHONY: lint-python
lint-python:      ## Ruff check all Python sources
	python -m ruff check gateway ai_ml tests

format-python:    ## Ruff format all Python sources
	python -m ruff format gateway ai_ml tests

.PHONY: test-python
test-python:      ## Run all Python tests (pytest)
	python -m pytest

.PHONY: test-gateway
test-gateway:     ## Run only gateway tests
	python -m pytest tests/gateway/

.PHONY: run-gateway
run-gateway:      ## Start the gateway locally (uvicorn, hot-reload)
	uv run --project gateway \
	  uvicorn gateway.main:app --host 0.0.0.0 --port 8080 --reload

.PHONY: seed
seed:             ## Seed dev database with realistic sample data (via gateway API)
	@echo "Usage: make seed [ARGS=...]"
	@echo "  Default: sends telemetry to http://localhost:8080"
	@echo "  make seed ARGS='--direct-db'        # skip API, insert events directly"
	@echo "  make seed ARGS='--direct-db --clear' # wipe + reseed"
	PYTHONPATH=gateway/src python scripts/seed.py $(ARGS)

# ── Web (app/) ─────────────────────────────────────────────────────────

.PHONY: install-app
install-app:      ## Install app Node.js dependencies (pnpm)
	cd app && pnpm install --frozen-lockfile

.PHONY: dev-app
dev-app:          ## Start app dev server (Next.js, hot-reload)
	cd app && pnpm dev

.PHONY: build-app
build-app:        ## Build app for production (Next.js)
	cd app && pnpm build

.PHONY: lint-app
lint-app:         ## ESLint check the app
	cd app && pnpm lint

.PHONY: typecheck-app
typecheck-app:    ## TypeScript type-check the app
	cd app && pnpm exec tsc --noEmit

# ── Docker images ──────────────────────────────────────────────────────

.PHONY: build-gateway
build-gateway:    ## Build gateway Docker image
	docker build -t $(IMAGE_REGISTRY)/gateway:$(IMAGE_TAG) ./gateway

.PHONY: build-app-image
build-app-image:  ## Build app Docker image
	docker build -t $(IMAGE_REGISTRY)/app:$(IMAGE_TAG) ./app

.PHONY: build-ppe
build-ppe:        ## Build ppe-detection Docker image
	docker build -t $(IMAGE_REGISTRY)/ppe-detection:$(IMAGE_TAG) -f ai_ml/ppe_detection/Dockerfile ./ai_ml

.PHONY: build-fall
build-fall:       ## Build fall-detection Docker image
	docker build -t $(IMAGE_REGISTRY)/fall-detection:$(IMAGE_TAG) -f ai_ml/fall_detection/Dockerfile ./ai_ml

.PHONY: build
build: build-gateway build-app-image build-ppe build-fall  ## Build all Docker images

.PHONY: push-gateway
push-gateway:     ## Push gateway image to registry
	docker push $(IMAGE_REGISTRY)/gateway:$(IMAGE_TAG)

.PHONY: push-app
push-app:         ## Push app image to registry
	docker push $(IMAGE_REGISTRY)/app:$(IMAGE_TAG)

# ── Docker Compose ─────────────────────────────────────────────────────

.PHONY: up
up:               ## Start all services (detached)
	docker compose -f $(COMPOSE_FILE) up --build -d

.PHONY: down
down:             ## Stop all services
	docker compose -f $(COMPOSE_FILE) down

.PHONY: logs
logs:             ## Tail logs from all services
	docker compose -f $(COMPOSE_FILE) logs -f

.PHONY: ps
ps:               ## List service status
	docker compose -f $(COMPOSE_FILE) ps

.PHONY: restart
restart:          ## Rebuild and restart all services
	docker compose -f $(COMPOSE_FILE) up --build -d --force-recreate

# ── Kubernetes (kubectl) ───────────────────────────────────────────────

K8S_DIR ?= k8s

.PHONY: k8s-apply
k8s-apply:        ## Apply all k8s manifests (kustomize)
	kubectl apply -k $(K8S_DIR)

.PHONY: k8s-delete
k8s-delete:       ## Delete all resources defined in k8s/
	kubectl delete -k $(K8S_DIR)

.PHONY: k8s-status
k8s-status:       ## Show safeguard namespace pod status
	kubectl get pods -n safeguard -o wide

# ── Quality gates ──────────────────────────────────────────────────────

.PHONY: lint
lint: lint-python lint-app             ## Run all linters

.PHONY: test
test: test-python                      ## Run all tests

.PHONY: check
check: lint-python test-python         ## Python quality gate (lint + test)

.PHONY: quality
quality: lint-python lint-app test-python typecheck-app  ## Full quality gate

# ── Housekeeping ───────────────────────────────────────────────────────

.PHONY: clean
clean:            ## Remove Python & Node caches
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true

.PHONY: help
help:             ## Show this help
	@grep -Eh '^[a-z.A-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
