# Almamlaka TV document assistant: one Cloud Run service (PROJECT_PLAN §7.5 step 6).
# Stage 1 builds the React UI into web/dist; stage 2 runs FastAPI with the index, saved reports and UI.

FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    APP_ENV=prod LLM_MODE=live PORT=8080
WORKDIR /srv
RUN pip install --no-cache-dir uv==0.13.1
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev
COPY app/ app/
COPY vendor/ vendor/
COPY data/index/ data/index/
COPY data/reports/ data/reports/
# Page images for the evidence spotlight (app/sources_api.py): only the PNGs, ~100 KB in total.
COPY data/derived/pages/*.png data/derived/pages/
COPY --from=web /web/dist/ web/dist/
# The served index must be the one the manifest describes (PROJECT_PLAN §7.5 step 6).
RUN .venv/bin/python -c "import hashlib, json; m = json.load(open('data/index/manifest.json')); \
assert hashlib.sha256(open('data/index/chunks.jsonl', 'rb').read()).hexdigest() == m['chunks_sha256'], 'index hash mismatch'"
RUN useradd --create-home --uid 10001 app && chown -R app /srv
USER app
CMD ["sh", "-c", "exec .venv/bin/uvicorn app.server:app --host 0.0.0.0 --port ${PORT}"]
