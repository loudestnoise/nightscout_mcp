FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY tests/ ./tests/

EXPOSE 8000

USER nobody

CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "src/log_config.yaml"]
