FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
COPY config ./config
COPY scripts ./scripts
COPY data/README.md data/feed_template.csv data/fx_rates.example.json ./data/
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data /app/outputs/live
EXPOSE 8787
CMD ["python", "scripts/run_live_daemon.py", "--capital", "10000", "--interval", "300", "--health-port", "8787"]
