# syntax=docker/dockerfile:1
# Build from the repo root: docker build -f deploy/web.Dockerfile .

FROM node:24-slim AS build
RUN npm install -g pnpm@11.22.0
WORKDIR /client
COPY client/package.json client/pnpm-lock.yaml client/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY client/ ./
# Same origin as the site; Caddy forwards /api/* to the server
RUN VITE_API_URL=/api pnpm build

FROM caddy:2-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /client/build /srv/client
