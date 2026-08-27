# Oracle Anomaly Swarm — D2 OS isolation skeleton (P5)
# Runtime: docker run --read-only --tmpfs /tmp --tmpfs /sandbox:rw \
#   --cap-drop ALL --security-opt no-new-privileges \
#   -e NATS_URL=nats://nats:4222 \
#   -v raas_sandbox:/sandbox:rw \
#   agentx-oracle-anomaly:p9
#
# Does NOT mount core, worm, or gateway volumes.

FROM python:3.12-slim

RUN useradd -u 10001 -r -s /usr/sbin/nologin redteam \
    && mkdir -p /app /sandbox \
    && chown -R redteam:redteam /app /sandbox

WORKDIR /app

RUN pip install --no-cache-dir 'nats-py>=2.6.0'

COPY plugins/oracle_anomaly_swarm/ /app/plugins/oracle_anomaly_swarm/
ENV PYTHONPATH=/app
ENV SANDBOX_DIR=/sandbox
ENV NATS_URL=nats://127.0.0.1:4222

USER redteam

CMD ["python", "-m", "plugins.oracle_anomaly_swarm.nats_bridge"]
