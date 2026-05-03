FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8080

CMD ["edelrep", "serve", \
     "--storage-root", "/data/storage", \
     "--index-path", "/data/index.db", \
     "--host", "0.0.0.0", \
     "--port", "8080"]
