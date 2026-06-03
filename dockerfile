FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md uv.lock ./
COPY app ./app
COPY main.py ./

RUN uv sync --no-dev

ENV PYTHONUNBUFFERED=1

ENV API_PORT=8000
EXPOSE 8000

CMD ["uv", "run", "python", "main.py"]
