FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 graphrag \
    && useradd --system --uid 10001 --gid graphrag --create-home graphrag

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

COPY alembic.ini ./
COPY migrations ./migrations

USER 10001:10001

CMD ["graphrag-api"]

