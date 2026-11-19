# Lernzentrum web (Next.js standalone) – build context: repository folder "lernzentrum/"
FROM node:22-alpine AS deps
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app/frontend
ENV NEXT_TELEMETRY_DISABLED=1
ARG API_URL=http://backend:8000
ENV API_URL=$API_URL
COPY --from=deps /app/frontend/node_modules ./node_modules
COPY frontend/ ./
COPY config/ /app/config/
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/frontend/.next/standalone ./
COPY --from=build /app/frontend/.next/static ./.next/static
COPY --from=build /app/frontend/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://127.0.0.1:3000/login >/dev/null || exit 1
CMD ["node", "server.js"]
