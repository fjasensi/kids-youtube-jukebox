FROM denoland/deno:bin-2.5.6 AS deno

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DENO_NO_UPDATE_CHECK=1 \
    DENO_NO_PROMPT=1 \
    APP_PORT=8000

WORKDIR /app

COPY --from=deno /deno /usr/local/bin/deno

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 jukebox \
    && chown -R jukebox:jukebox /app
USER jukebox

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
