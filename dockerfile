FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY app ./app
COPY main.py ./

RUN uv sync --no-dev

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "python", "main.py"]
