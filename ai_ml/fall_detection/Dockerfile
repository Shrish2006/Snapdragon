# Build context: AI_ML/
# docker build -f fall_detection/Dockerfile -t safeguard/fall-detection:latest .

FROM python:3.11-slim-bookworm AS deps

RUN pip install uv --no-cache-dir

WORKDIR /app/fall_detection
COPY fall_detection/pyproject.toml .
RUN uv sync --no-dev --no-group train


FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app/fall_detection

COPY --from=deps /app/fall_detection/.venv ./.venv
COPY fall_detection/app.py .

ENV PATH="/app/fall_detection/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/fall_detection/.venv"

RUN groupadd -r appgroup && useradd -g appgroup -u 1000 appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
