# SafeGuard — Deployment Guide

Covers local development, image publishing to GHCR, and Kubernetes deployment.

- [Services & ports](#services--ports)
- [Local development (Docker Compose)](#local-development-docker-compose)
- [Environment variables](#environment-variables)
- [Container images (GHCR)](#container-images-ghcr)
- [CI/CD](#cicd)
- [Versioning & releases](#versioning--releases)
- [Kubernetes](#kubernetes)
- [Health endpoints](#health-endpoints)
- [Troubleshooting](#troubleshooting)

---

## Services & ports

| Service | Image | Container port | Local host port |
|---------|-------|----------------|-----------------|
| `app` | `ghcr.io/shrish2006/snapdragon/app` | 3000 | 3000 |
| `gateway` | `ghcr.io/shrish2006/snapdragon/gateway` | 8080 | 8080 |
| `ppe-detection` | `ghcr.io/shrish2006/snapdragon/ppe-detection` | 8000 | 8001 |
| `fall-detection` | `ghcr.io/shrish2006/snapdragon/fall-detection` | 8000 | 8002 |
| `mqtt` (Mosquitto) | `eclipse-mosquitto:2` | 1883 (MQTT), 9001 (WS-MQTT) | 1883, 9001 |

The ML services both listen on 8000 inside their containers; Compose maps them to
distinct host ports.

---

## Local development (Docker Compose)

Prerequisites: Docker Engine with Compose v2.

```bash
cp .env.example .env          # optional; defaults apply without it
docker compose up --build
```

`docker compose up` auto-merges `compose.override.yml`, giving a **hot-reload dev
stack**: the app runs `next dev`, the ML services run `uvicorn --reload`, and source is
bind-mounted (image-baked `node_modules` / `.venv` are preserved via anonymous volumes).

For a **production-like** run (built images, no reload, no bind mounts):

```bash
docker compose -f docker-compose.yml up --build
```

Common commands:

```bash
docker compose logs -f ppe-detection      # follow one service
docker compose ps                          # status + health
docker compose down                        # stop and remove
```

### GPU + camera (opt-in)

The PPE service falls back to CPU automatically. To use an NVIDIA GPU and a local
camera, install the NVIDIA Container Toolkit and uncomment the `devices:` / `deploy:`
block under `ppe-detection` in `docker-compose.yml`.

---

## Environment variables

All variables the code reads are documented in `.env.example`. Highlights:

| Variable | Used by | Notes |
|----------|---------|-------|
| `LOG_LEVEL` | all Python services (`ai_ml/config.py`) | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `LOG_FILE_PATH` | Python services | Empty = stdout (compose default). K8s uses a PVC path. |
| `CAMERA_INDEX` | ppe-detection | OpenCV camera index for `/stream` |
| `HF_HOME` | ppe-detection | Model cache dir (writable by the non-root user) |
| `HF_TOKEN` | ppe-detection | Only needed if the model repo goes private |
| `NEXT_PUBLIC_BACKEND_BASE_URL` | app | Browser-facing backend URL; swapped in at boot |
| `CORS_ALLOW_ORIGINS` | gateway | Comma-separated browser origins allowed to call the gateway directly (REST + WebSocket) — the dashboard talks to `NEXT_PUBLIC_BACKEND_BASE_URL` from the browser, so this must exactly match the app's deployed origin. Default `http://localhost:3000`. |
| `PPE_URL` / `FALL_URL` | gateway | Upstream ML service base URLs |
| `EVENT_BUS_BACKEND` | gateway | `memory` (default) or `redis` — see `gateway/example.env` for the full set of gateway-specific variables (event store backend, Redis/SQLite paths, telemetry validation) |
| `MQTT_BROKER_HOST` | gateway | Hostname of the Mosquitto broker (`mqtt` in Compose, `mosquitto` in K8s). Empty = MQTT disabled, gateway runs HTTP-only. |
| `MQTT_BROKER_PORT` | gateway | Default `1883`. |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | gateway | Broker credentials for the gateway service account. |
| `MQTT_TOPIC_PREFIX` | gateway | Topic namespace prefix (default `safeguard`). |

> **Next.js note:** `NEXT_PUBLIC_*` values are inlined at build time. The app image's
> `docker-entrypoint.sh` rewrites the baked default at container start, so the same
> image works across environments by changing this env var.

---

## Container images (GHCR)

Images are published to the GitHub Container Registry under the repo owner:

```
ghcr.io/shrish2006/snapdragon/app
ghcr.io/shrish2006/snapdragon/gateway
ghcr.io/shrish2006/snapdragon/ppe-detection
ghcr.io/shrish2006/snapdragon/fall-detection
```

### Pulling

Public images pull without auth. For private images, authenticate with a PAT that has
`read:packages`:

```bash
echo "$GITHUB_PAT" | docker login ghcr.io -u <github-username> --password-stdin
docker pull ghcr.io/shrish2006/snapdragon/app:latest
```

### Building & pushing manually

CI does this automatically, but to publish by hand:

```bash
docker build -t ghcr.io/shrish2006/snapdragon/app:dev ./app
docker build -t ghcr.io/shrish2006/snapdragon/gateway:dev ./gateway
docker build -f ai_ml/ppe_detection/Dockerfile -t ghcr.io/shrish2006/snapdragon/ppe-detection:dev ./ai_ml
docker build -f ai_ml/fall_detection/Dockerfile -t ghcr.io/shrish2006/snapdragon/fall-detection:dev ./ai_ml
docker push ghcr.io/shrish2006/snapdragon/app:dev
```

Note the ML build **context is `ai_ml/`** (the Dockerfiles copy `config.py` and the
service subfolder relative to it).

---

## CI/CD

Two GitHub Actions workflows:

- **`.github/workflows/ci.yml`** — on every PR and branch push:
  - `ruff` lint + `pytest` (Python)
  - `eslint` + `tsc --noEmit` (web)
  - `docker build` verification for all four images (no push), with GHA layer cache.
- **`.github/workflows/cd.yml`** — on branch pushes and `v*.*.*` tags:
  - builds all four images with buildx, multi-arch where practical
    (`app` + `fall-detection` build `amd64`+`arm64`; `ppe-detection` is `amd64`-only
    because torch cu124 has no arm64 wheels),
  - pushes to GHCR with tags derived by `docker/metadata-action`.

No secrets to configure — CD uses the built-in `GITHUB_TOKEN` with `packages: write`.

---

## Versioning & releases

Image tags are derived automatically:

| Git event | Tags published |
|-----------|----------------|
| push to default branch | `latest`, `sha-<short>` |
| push to other branch | `<branch>`, `sha-<short>` |
| push tag `v1.4.2` | `1.4.2`, `1.4`, `1`, `latest`, `sha-<short>` |

Cut a release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Then pin the release in Kubernetes (see below) and re-apply.

---

## Kubernetes

Manifests live in `k8s/` and are wired with a single `kustomization.yaml`.

### Prerequisites

- An ingress-nginx controller.
- (Optional) cert-manager with a `letsencrypt-prod` ClusterIssuer for TLS.
- (PPE GPU) an NVIDIA device plugin + `nvidia` RuntimeClass on a GPU node.
- DNS records for the ingress hosts pointing at the ingress load balancer:
  - `snapdragon.upayan.dev` → app
  - `api-snapdragon.upayan.dev` → gateway
  - `ppe-snapdragon.upayan.dev` → ppe-detection
  - `fall-snapdragon.upayan.dev` → fall-detection

### Deploy

```bash
kubectl apply -k k8s/
kubectl -n safeguard rollout status deploy/app
kubectl -n safeguard get pods,svc,ingress
```

`kubectl apply -k` applies in dependency order (Namespace and ConfigMap first).

### Secrets

The `HF_TOKEN` secret is **optional** (the model repo is public). If needed:

```bash
kubectl create secret generic safeguard-secrets \
  --namespace safeguard \
  --from-literal=HF_TOKEN=hf_xxx
```

`k8s/secret.example.yaml` is a template and is intentionally **not** part of the
kustomization, so `kubectl apply -k k8s/` never clobbers a real secret.

### Pinning an image version

`k8s/kustomization.yaml` controls image tags centrally. To deploy a release:

```bash
cd k8s
kustomize edit set image \
  ghcr.io/shrish2006/snapdragon/app=ghcr.io/shrish2006/snapdragon/app:v1.0.0 \
  ghcr.io/shrish2006/snapdragon/gateway=ghcr.io/shrish2006/snapdragon/gateway:v1.0.0 \
  ghcr.io/shrish2006/snapdragon/ppe-detection=ghcr.io/shrish2006/snapdragon/ppe-detection:v1.0.0 \
  ghcr.io/shrish2006/snapdragon/fall-detection=ghcr.io/shrish2006/snapdragon/fall-detection:v1.0.0
kubectl apply -k .
```

### Deployment strategy

- `app` and `fall-detection` use `RollingUpdate` (`maxUnavailable: 0`) for zero-downtime.
- `ppe-detection` uses `Recreate`: a single GPU cannot be shared by a surging second
  pod, so it is replaced in place.

### Rollback

```bash
kubectl -n safeguard rollout undo deploy/app
# or re-pin the previous tag / sha in kustomization and re-apply
```

---

## Health endpoints

| Service | Liveness | Readiness |
|---------|----------|-----------|
| app | `GET /api/health` | `GET /api/health` |
| gateway | `GET /health` | `GET /ready` (background tasks started; event bus reachable) |
| ppe-detection | `GET /health` | `GET /ready` (model loaded) |
| fall-detection | `GET /health` | `GET /health` |

All return `{"status":"ok"}` with HTTP 200. `ppe /ready` returns 503 until the model is
loaded, which gates traffic during the (slow) first startup. `gateway /ready` returns 503
until its background event-processing/subscription tasks are running, and again if the
event bus backend is Redis and Redis becomes unreachable.

Gateway also exposes `GET /metrics` (Prometheus text format: HTTP request counts/latency
by route, current WebSocket connection count).

---

## Troubleshooting

- **PPE pod stuck `Pending`** — no schedulable GPU node. Check the NVIDIA device plugin
  and the `nvidia` RuntimeClass, or run CPU-only (remove the GPU request/`runtimeClassName`).
- **PPE readiness fails for ~1–2 min on first boot** — expected; it is downloading the
  model. The readiness probe has a 60s initial delay + 6 retries.
- **`app` shows the wrong backend URL** — set `NEXT_PUBLIC_BACKEND_BASE_URL` (ConfigMap
  in k8s, `.env` in compose); the entrypoint rewrites it at start.
- **Ingress 404 / no TLS** — confirm the ingress-nginx controller is installed and DNS
  resolves to it; remove the cert-manager annotation + `tls:` block if cert-manager is
  absent.
- **Permission denied writing logs/cache in k8s** — ensure the pod `securityContext.fsGroup`
  is present (already set for ppe-detection); it makes mounted volumes writable by the
  non-root user.
