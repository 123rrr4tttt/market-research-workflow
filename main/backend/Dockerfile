FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534 AS backend-shared-base

# Python build-time bytecode uses content hashes instead of installation mtimes.
ARG SOURCE_DATE_EPOCH=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/opt/mrw/src

WORKDIR /app

# System deps for psycopg2, build tools, and health check tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /var/log/alternatives.log /var/log/apt/history.log \
       /var/log/apt/term.log /var/log/dpkg.log \
    && rm -f /var/cache/ldconfig/aux-cache

ARG INSTALL_OPTIONAL_ENHANCEMENTS=false

COPY ./main/backend/requirements.txt /app/requirements.txt
COPY ./main/backend/requirements-optional-enhancements.txt /app/requirements-optional-enhancements.txt
COPY ./main/backend/requirements-psutil-wheels.txt /app/requirements-psutil-wheels.txt
# Both roles consume the same verified prebuilt wheel; never build psutil from sdist.
RUN python -m pip download --index-url https://pypi.org/simple \
      --require-hashes --only-binary=:all: --no-deps \
      -r /app/requirements-psutil-wheels.txt --dest /opt/mrw-wheels \
    && python -m pip install --no-index --no-deps /opt/mrw-wheels/psutil-6.0.0-*.whl
RUN pip install -r /app/requirements.txt
RUN if [ "$INSTALL_OPTIONAL_ENHANCEMENTS" = "true" ]; then \
      pip install -r /app/requirements-optional-enhancements.txt; \
    fi
# setuptools owns its vendored jaraco.context and wheel copies; refresh that vendor set as one package.
RUN python -m pip install --no-deps "setuptools==80.10.2"

COPY ./src /opt/mrw/src
COPY ./main/backend /app

FROM backend-shared-base AS migration-runner

ENV MRW_CONTAINER_ROLE=migration-runner

ENTRYPOINT ["alembic"]
CMD ["upgrade", "head"]

FROM backend-shared-base AS backend-runtime

ENV MRW_CONTAINER_ROLE=backend-runtime

# 复制并设置启动脚本权限
COPY ./main/backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

# 使用entrypoint脚本处理初始化
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
