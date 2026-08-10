# Agent X — Z3 Theorem Prover Service
# Mathematischer BHO-Invariant-Beweis via Z3 Real-Arithmetik
#
# Build:
#   docker build -f services/z3_solver/Dockerfile.z3 -t agentx-z3:latest .
#
# Run:
#   docker run -p 8000:8000 agentx-z3:latest

FROM python:3.11-slim

# System-Abhängigkeiten (nur libstdc++ für Z3-Binaries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Z3-Service-Dependencies
COPY services/z3_solver/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Service-Code
COPY services/z3_solver/main.py /app/main.py

# Healthcheck: Z3-Kernel antwortet
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import z3; s=z3.Solver(); x=z3.Int('x'); s.add(x>0); assert s.check()==z3.sat" || exit 1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
