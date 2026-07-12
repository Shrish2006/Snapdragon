# Build context: AI_ML/
# docker build -f ppe_detection/Dockerfile -t safeguard/ppe-detection:latest .

FROM python:3.11-slim-bookworm AS deps

RUN pip install uv --no-cache-dir

WORKDIR /app/ppe_detection
COPY ppe_detection/pyproject.toml .
RUN uv sync --no-dev --no-group gpu


FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/ppe_detection

COPY --from=deps /app/ppe_detection/.venv ./.venv

COPY config.py /app/config.py
COPY ppe_detection/drawing.py .
COPY ppe_detection/camera.py .
COPY ppe_detection/inference.py .
COPY ppe_detection/app.py .
COPY ppe_detection/yolov8n-pose.onnx .
COPY ppe_detection/best.onnx .
COPY ppe_detection/roi.json .

ENV PYTHONPATH=/app
ENV PATH="/app/ppe_detection/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/ppe_detection/.venv"

RUN groupadd -r appgroup && useradd -g appgroup -u 1000 appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
