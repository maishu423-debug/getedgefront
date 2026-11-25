# Build context: repository root.  docker build -f apps/web/Dockerfile .
# Pinned: Node 24.22.2 on Debian 12 (bookworm).
FROM node:24.22.2-bookworm-slim AS base
RUN npm install -g pnpm@10.34.9
WORKDIR /repo

FROM base AS build
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @edgefront/web...
COPY apps/web apps/web
# Station registry copy for generateStaticParams + the 404 check (build never needs the API).
COPY data/stations.yaml data/stations.yaml
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @edgefront/web build

FROM node:24.22.2-bookworm-slim AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=:: \
    PORT=3000
RUN useradd --system --uid 10001 app
# Standalone output keeps the monorepo path: server lives at apps/web/server.js.
COPY --from=build --chown=app /repo/apps/web/.next/standalone ./
COPY --from=build --chown=app /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=app /repo/apps/web/public ./apps/web/public
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT+'/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/web/server.js"]
