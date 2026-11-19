# Lernzentrum API – build context: repository folder "lernzentrum/"
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Berlin LZ_DATA_DIR=/data
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-deu tzdata curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/
COPY config/ /app/config/
RUN useradd -u 10001 -m lz && mkdir -p /data && chown -R lz /data
USER lz
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fs http://127.0.0.1:8000/api/health || exit 1
# PostgreSQL: run migrations first; SQLite (single container) creates tables on start
CMD ["sh", "-c", "case \"$LZ_DATABASE_URL\" in postgres*) alembic upgrade head;; esac && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
