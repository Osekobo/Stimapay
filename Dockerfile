FROM node:20-bookworm-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 make g++ ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm ci --omit=dev

FROM node:20-bookworm-slim

ENV NODE_ENV=production
WORKDIR /app

RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /app/node_modules ./node_modules
COPY package*.json ./
COPY db.js mpesa.js server.js ./

RUN mkdir -p /app/data && chown -R appuser:appuser /app
VOLUME ["/app/data"]

USER appuser

EXPOSE 3000

CMD ["node", "server.js"]