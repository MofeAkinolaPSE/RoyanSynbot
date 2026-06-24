# ── Stage 1: Build ─────────────────────────────────────────────────────────
FROM cgr.dev/chainguard/node:latest-dev AS builder

USER root
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@latest --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --no-frozen-lockfile
COPY . .
RUN pnpm run build:client

# ── Stage 2: Serve ──────────────────────────────────────────────────────────
FROM cgr.dev/chainguard/nginx:latest AS static
COPY --from=builder /app/dist/spa /usr/share/nginx/static
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 8080
