FROM node:24.20.0-slim AS miniapp-builder

WORKDIR /build/miniapp
COPY miniapp/package.json miniapp/package-lock.json ./
RUN npm ci
COPY miniapp/ ./
RUN npm run build


FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY --chown=app:app . .
COPY --from=miniapp-builder --chown=app:app /build/miniapp/dist ./miniapp/dist

USER app

CMD ["sh", "-c", "python -m alembic upgrade head && exec python main.py"]
