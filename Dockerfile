FROM python:3.12-slim-bookworm

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir -e .

COPY scripts ./scripts
COPY Makefile ./

ENV PYTHONUNBUFFERED=1
CMD ["bunker", "status"]