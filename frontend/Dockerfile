# Multi-arch (linux/amd64, linux/arm64) Next.js standalone image.
# The default base comes from the ECR Public mirror of the Docker Official Images
# to avoid Docker Hub pull rate limits.
ARG BASE_IMAGE=public.ecr.aws/docker/library/node:20-alpine

FROM ${BASE_IMAGE} AS deps
WORKDIR /app
# Some Next.js SWC binaries on musl need glibc compatibility shims.
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM ${BASE_IMAGE} AS builder
WORKDIR /app
# NEXT_PUBLIC_* values are inlined into the client bundle at build time.
# The default serves the API from the same origin (nginx / CloudFront route /api/*).
ARG NEXT_PUBLIC_API_BASE=/api/v1
ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM ${BASE_IMAGE} AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -S -g 1001 nodejs && adduser -S -u 1001 -G nodejs nextjs
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
