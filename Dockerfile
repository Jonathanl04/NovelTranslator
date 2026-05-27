FROM node:24-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && scrapling install

COPY app.py ./
COPY novel_translator/ ./novel_translator/
COPY scraper/ ./scraper/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /data/logs \
    && chown -R appuser:appuser /app /data

USER appuser
RUN patchright install chromium

EXPOSE 8765

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8765"]
