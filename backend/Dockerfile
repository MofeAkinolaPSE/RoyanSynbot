# ── Stage 1: Install dependencies ──────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Apply OS security patches before installing Python packages
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

COPY requirements.txt .
# --timeout/--retries because this builds over a slow link: the default 15s read
# timeout kills the botocore download (15.7 MB at ~50 kB/s) partway through and
# fails the whole layer.
RUN pip install --no-cache-dir --user \
      --timeout 120 --retries 10 \
      -r requirements.txt

# ── Stage 2: Runtime image ─────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Apply OS security patches to the runtime image
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Bake the embedding model into the image so containers never need to reach
# Hugging Face Hub at runtime — eliminates the ~2-3min cold-start download
# and removes a runtime dependency on outbound internet access.
ENV FASTEMBED_CACHE_PATH=/backend/model_cache
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2')"
ENV HF_HUB_OFFLINE=1

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
