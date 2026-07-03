# ── Stage 1: Install dependencies ──────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Apply OS security patches before installing Python packages
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Stage 2: Runtime image ─────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Apply OS security patches to the runtime image
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY app.py .
COPY src/ ./src/
COPY config.yaml .
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
