FROM python:3.11-slim-bookworm AS deps

RUN pip install uv --no-cache-dir

WORKDIR /app
COPY pyproject.toml .
RUN uv sync --no-dev


FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

COPY --from=deps /app/.venv ./.venv
COPY src ./src

ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv" \
    PYTHONPATH="/app/src" \
    PPE_URL=http://ppe-detection:8000 \
    FALL_URL=http://fall-detection:8000 \
    LOG_LEVEL=INFO \
    EVENT_BUFFER=200

RUN groupadd -r appgroup && useradd -r -g appgroup -u 1000 appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
