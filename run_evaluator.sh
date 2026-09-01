#!/bin/bash
# Hetzner co-located shadow evaluator — post G1 PASS only (SHADOW_EVAL_G1_PASS=1).
# Pre-Reg: docs/SHADOW_EVALUATOR_PREREG.md · Do not run before News 24h gate PASS.
set -euo pipefail
cd /root/agent_x_storage
export PYTHONPATH=.
exec /root/agent_x_storage/venv/bin/python scripts/shadow_evaluator.py --once \
  --edges "${PAPER_EDGES_PATH:-data/audit/paper_edges.jsonl}" \
  --out "${SHADOW_EVAL_OUT:-data/audit/shadow_eval.jsonl}" \
  --news "${NEWS_PHASE_PATH:-data/phase_signals/news_sentiment.jsonl}" \
  --gap "${GAP_PHASE_PATH:-data/phase_signals/price_gap.jsonl}"
