FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy the entire repo so agents_b2g.* imports work
COPY . .

RUN pip install --no-cache-dir nats-py aiohttp

ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

ENTRYPOINT ["python", "-m", "agents.surface.run_agent"]
