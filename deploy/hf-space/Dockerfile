# Single-container demo for a PRIVATE Hugging Face Space (Docker SDK, port 7860).
# API (uvicorn, 127.0.0.1:8000) + web (Next standalone, 0.0.0.0:7860). Demo data is re-seeded on every start.
FROM node:22-slim AS web
WORKDIR /repo/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY config/ /repo/config/
COPY legal/ /repo/legal/
COPY frontend/ ./
ENV BACKEND_URL=http://127.0.0.1:8000 FRAME_ANCESTORS="https://huggingface.co" NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-deu && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY --chown=user backend/ backend/
COPY --chown=user config/ config/
COPY --from=web --chown=user /repo/frontend/.next/standalone web/
COPY --from=web --chown=user /repo/frontend/.next/static web/.next/static
COPY --from=web --chown=user /repo/frontend/public web/public
COPY --chown=user deploy/hf-space/start.sh start.sh
USER user
ENV FP_CONFIG_DIR=/home/user/app/config DEMO_MODE=true ENV=development COOKIE_SECURE=true \
    DATABASE_URL=sqlite:////tmp/tracelow/tracelow.db UPLOAD_DIR=/tmp/tracelow/uploads PORT=7860 HOSTNAME=0.0.0.0
EXPOSE 7860
CMD ["sh", "start.sh"]
