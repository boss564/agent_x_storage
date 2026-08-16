# Agent X — Production Docker Image
# Multi-stage build for minimal image size (~200MB)
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code (excluding heavy data dirs)
COPY core/ ./core/
COPY api/ ./api/
COPY api_agents/ ./api_agents/
COPY agents_b2g/ ./agents_b2g/
COPY agent_x_orchestrator.py .
COPY agent_x_lending_*.py .
COPY agent_x_klasse_*.py .
COPY agent_x_gas_optimizer.py .
COPY agent_x_bundle_executor.py .
COPY agent_x_offchain_scout.py .
COPY agent_x_aave_subscriber.py .
COPY agent_x_metrics.py .
COPY agent_x_dashboard.py .
COPY agent_x_backtest.py .
COPY test_all_modules.py .
COPY agent_x_live_test.py .
COPY agent_x_chainlink_client.py .
COPY agent_x_pyth_client.py .
COPY agent_x_governance_client.py .
COPY agent_x_vesting_client.py .
COPY agent_x_beacon_client.py .
COPY agent_x_solana_client.py .
COPY agent_x_flashbots_client.py .
COPY agent_x_jito_client.py .
COPY agent_x_storage.py .
COPY agent_x_seafile.py .
COPY agent_x_archiver.py .
COPY agent_x_storage_guardian.py .
COPY storage_client.py .
COPY __init__.py .

# Ensure PATH includes user packages
ENV PATH="/root/.local/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Honest health: agent process alive (not just the 'sh -c || true' wrapper).
# python:*-slim has no procps/pgrep — read /proc cmdline directly.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import os,sys; sys.exit(0 if any(b'agents_b2g' in open(f'/proc/{p}/cmdline','rb').read() for p in os.listdir('/proc') if p.isdigit()) else 1)"

EXPOSE 8080
# ENTRYPOINT runs the compose 'command', then idles to keep container alive
ENTRYPOINT ["sh", "-c", "\"$@\" || true; echo 'Agent initialized'; tail -f /dev/null", "--"]
