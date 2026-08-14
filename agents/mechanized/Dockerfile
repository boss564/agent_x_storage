FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy the entire repo so agents.* imports work
COPY . .

RUN pip install --no-cache-dir nats-py

ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

EXPOSE 8082

ENTRYPOINT ["python", "-m", "agents.mechanized.handler"]
