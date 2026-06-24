# ── Stage 1: Build ─────────────────────────────────────────────────────────
FROM cgr.dev/chainguard/node:latest-dev AS builder

USER root
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ── Stage 2: Serve ──────────────────────────────────────────────────────────
FROM cgr.dev/chainguard/nginx:latest
COPY --from=builder /app/dist /usr/share/nginx/portal
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
