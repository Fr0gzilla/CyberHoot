# syntax=docker/dockerfile:1.7
# Image multi-étapes : la feuille de style est compilée à part, l'image finale ne contient
# ni Node ni outils de compilation, et l'application tourne sous un compte sans privilège.

FROM node:22-alpine AS css
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY tailwind.config.js ./
COPY assets ./assets
COPY app/templates ./app/templates
COPY app/static/js ./app/static/js
RUN npm run build:css

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt

# Étape de vérification : mêmes dépendances + outils de test (make verify dans Docker, CI).
FROM base AS test
COPY requirements-dev.txt ./
RUN pip install --require-hashes -r requirements-dev.txt
COPY . .
COPY --from=css /build/app/static/css/app.css ./app/static/css/app.css
CMD ["sh", "-c", "ruff check . && ruff format --check . && mypy && bandit -q -c pyproject.toml -r app && pytest --cov --cov-report=term-missing"]

FROM base AS production
RUN groupadd --system --gid 10001 cyberhoot \
    && useradd --system --uid 10001 --gid cyberhoot --no-create-home --shell /usr/sbin/nologin cyberhoot
COPY --chown=root:root app ./app
COPY --chown=root:root migrations ./migrations
COPY --chown=root:root alembic.ini wsgi.py gunicorn.conf.py docker/entrypoint.sh ./
COPY --from=css --chown=root:root /build/app/static/css/app.css ./app/static/css/app.css
RUN chmod 0755 entrypoint.sh
USER cyberhoot
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"
ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
