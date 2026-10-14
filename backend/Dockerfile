# syntax=docker/dockerfile:1.7
ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm
FROM ${PYTHON_IMAGE} AS builder
RUN python -m pip install --no-cache-dir uv==0.13.1
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-default-groups --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH DATA_DIR=/var/data/crebry EMBEDDING_PROVIDER=gemini \
    ANONYMIZED_TELEMETRY=False TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MALLOC_ARENA_MAX=2
RUN apt-get update && apt-get install --no-install-recommends -y libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 10001 crebry && useradd --uid 10001 --gid crebry --no-create-home crebry && \
    mkdir -p /var/data/crebry && chown crebry:crebry /var/data/crebry
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=crebry:crebry app ./app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/api/health', timeout=4)"
CMD ["python", "-m", "app.bootstrap"]
