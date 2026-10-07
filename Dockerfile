FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SWARMMOJO_DATA_DIR=/app/data/prefrontal \
    SWARMMOJO_STATE_DIR=/app/data/state

COPY requirements-ci.txt requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements-ci.txt

COPY . .

ENTRYPOINT ["python", "swarmmojo.py"]
CMD ["mcp"]
