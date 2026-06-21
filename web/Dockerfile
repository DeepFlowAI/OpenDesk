ARG NODE_BASE_IMAGE=node:22-alpine
FROM ${NODE_BASE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

FROM ${NODE_BASE_IMAGE} AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV APP_ENV=production
# Build stamp: baked into the client bundle (NEXT_PUBLIC_APP_VERSION) and
# written to public/version.json. The frontend polls version.json and compares
# it to the baked value to detect a new deploy and prompt users to refresh.
ARG APP_VERSION=dev
ENV NEXT_PUBLIC_APP_VERSION=$APP_VERSION
RUN node -e "require('fs').writeFileSync('public/version.json', JSON.stringify({version: process.env.NEXT_PUBLIC_APP_VERSION || 'dev'}))"
RUN npm run build

FROM ${NODE_BASE_IMAGE} AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV APP_ENV=production
# Next.js standalone binds to $HOSTNAME; default to all interfaces so the
# server is reachable on both loopback (health probes) and the container IP
# (nginx). Without this, Docker's auto HOSTNAME=<container-id> leaves it off
# 127.0.0.1.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
# Standalone output: a minimal server.js + traced node_modules. `public` and
# `.next/static` are not bundled into standalone, so copy them separately.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
