# Risk prefilter — D2 OS isolation skeleton (queue priority only)
# Runtime: docker run --read-only --tmpfs /tmp \
#   --cap-drop ALL --security-opt no-new-privileges \
#   -e NATS_URL=nats://nats:4222 \
#   -e PREFILTER_MODEL_PATH=/models/prefilter_gbt.pkl \
#   -v prefilter_models:/models:ro \
#   agentx-risk-prefilter:p9
#
# Does NOT mount core, worm, or gateway volumes.

FROM python:3.12-slim

RUN useradd -u 10001 -r -s /usr/sbin/nologin redteam \
    && mkdir -p /app /models \
    && chown -R redteam:redteam /app /models

WORKDIR /app

RUN pip install --no-cache-dir 'nats-py>=2.6.0' 'numpy>=1.26' 'scikit-learn>=1.3'

COPY plugins/risk_prefilter/ /app/plugins/risk_prefilter/
ENV PYTHONPATH=/app
ENV NATS_URL=nats://127.0.0.1:4222
ENV PREFILTER_MODEL_PATH=/models/prefilter_gbt.pkl

USER redteam

CMD ["python", "-m", "plugins.risk_prefilter.nats_bridge"]
