FROM python:3.13-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NOVEL_TRANSLATOR_BOOKTO_REAL_CHROME=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSLO https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && scrapling install

USER appuser
RUN patchright install chromium
USER root

FROM node:24-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM runtime-base

RUN mkdir -p /data/logs \
    && chown -R appuser:appuser /data

COPY --chown=appuser:appuser app.py ./
COPY --chown=appuser:appuser novel_translator/ ./novel_translator/
COPY --chown=appuser:appuser scraper/ ./scraper/
COPY --chown=appuser:appuser --from=frontend-build /app/frontend/dist ./frontend/dist

USER appuser

EXPOSE 8765

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8765"]
