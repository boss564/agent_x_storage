# MEV/Latency Red-Team — D2 OS isolation skeleton
# Runtime: docker run --read-only --tmpfs /tmp --tmpfs /sandbox:rw \
#   --cap-drop ALL --security-opt no-new-privileges \
#   -e NATS_URL=nats://nats:4222 \
#   -v raas_sandbox:/sandbox:rw \
#   agentx-mev-redteam:p9
#
# Does NOT mount core, worm, or gateway volumes.

FROM python:3.12-slim

RUN useradd -u 10001 -r -s /usr/sbin/nologin redteam \
    && mkdir -p /app /sandbox \
    && chown -R redteam:redteam /app /sandbox

WORKDIR /app

# Minimal deps for NATS worker (no z3, no gateway)
RUN pip install --no-cache-dir 'nats-py>=2.6.0'

COPY plugins/mev_latency_redteam/ /app/plugins/mev_latency_redteam/
ENV PYTHONPATH=/app
ENV SANDBOX_DIR=/sandbox
ENV NATS_URL=nats://127.0.0.1:4222

USER redteam

# Default: NATS worker (request/reply on edge.P2.redteam.sandbox)
CMD ["python", "-m", "plugins.mev_latency_redteam.nats_bridge"]
