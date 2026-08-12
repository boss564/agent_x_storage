FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir nats-py wasmtime
COPY . .
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "-c", "print('Ephemeral listener ready — Session 3')"]
