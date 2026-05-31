FROM python:3.13-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

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
