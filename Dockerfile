# Signal Hunt game engine — build from the signal-hunt/ directory (monorepo or satellite).
#   docker build -t signal-hunt-game:local .
FROM node:22-alpine AS frontend-builder
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml LICENSE README.md ./
COPY signal_hunt ./signal_hunt/
COPY tests ./tests/
RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir -e .
COPY --from=frontend-builder /src/dist /app/frontend/dist
RUN groupadd --system --gid 10001 signalhunt \
    && useradd --system --uid 10001 --gid signalhunt --home-dir /app signalhunt \
    && mkdir -p /app/data \
    && chown -R signalhunt:signalhunt /app
USER signalhunt:signalhunt
ENV SIGNAL_HUNT_PORT=8060
ENV SIGNAL_HUNT_DATA_DIR=/app/data
ENV SIGNAL_HUNT_STATIC_DIR=/app/frontend/dist
EXPOSE 8060
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8060/health || exit 1
CMD ["python", "-m", "signal_hunt.main"]
