# Between Visits dashboard, production image (WS0 R5). Build context = repo root:
#   docker build -f frontend/Dockerfile --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 -t between-visits-web .
# The production build has no Next.js dev overlay or dev badge. The root .dockerignore keeps .env files
# (including frontend/.env.local) out of the build context.

FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_* values are inlined into the browser bundle by `next build`, so the API URL is a build
# argument, not a runtime variable: changing it means rebuilding the image.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./
RUN npm run build

# Runtime: only the standalone server (output: "standalone" in next.config.ts) and the static assets.
# `node server.js` is the production server (`next start`) of a standalone build; Next.js asks for it instead
# of `next start` with output: "standalone", and it needs no node_modules beyond the traced ones.
FROM node:22-bookworm-slim AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
