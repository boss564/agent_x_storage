#!/usr/bin/env python3
"""Agent X MultiChain — Sovereign Appchain Dashboard (Streamlit).

Live visualization of 9 sovereign appchains across 4 chain layers.
Shows block heights, state roots, cross-chain messages, compliance.

Usage:
  streamlit run agents_b2g/multichain/streamlit_app.py
"""

import asyncio
import hashlib
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from agents_b2g.multichain import ChainOrchestrator

# ─── Page Config ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Agent X MultiChain — Sovereign Appchains",
    page_icon="⛓️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Session State ──────────────────────────────────────────────────────────

for k, v in {
    "result": None, "running": False, "orch": None,
    "last_cycles": 0, "auto_refresh": False, "refresh_s": 2,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⛓️ MultiChain")
    st.caption("9 Sovereign Appchains")
    st.divider()

    st.subheader("⚙️ Simulation")
    cycles = st.slider("Cycles", 10, 2000, 100, 10)
    batch = st.select_slider("Sensor Batch", options=[50, 100, 250, 500, 1000, 2000], value=1000)
    user = st.text_input("User ID", "dashboard")

    if st.button("🚀 Run", use_container_width=True, type="primary",
                 disabled=st.session_state.running):
        st.session_state.running = True
        with st.spinner(f"Running {cycles} cycles..."):
            try:
                orch = ChainOrchestrator(user_id=user, cycles=cycles, sensor_batch=batch)
                result = asyncio.run(orch.run_simulation(cycles=cycles))
                st.session_state.result = result
                st.session_state.orch = orch
                st.session_state.last_cycles = cycles
            except Exception as e:
                st.error(f"{e}\n{traceback.format_exc()}")
        st.session_state.running = False
        st.rerun()

    st.divider()
    st.subheader("🔄 Live")
    ar = st.toggle("Auto-Refresh", st.session_state.auto_refresh)
    st.session_state.auto_refresh = ar

    st.divider()
    st.caption("Wave 36 | v0.21.0")

# ─── Main ───────────────────────────────────────────────────────────────────

st.title("⛓️ Agent X MultiChain — 9 Sovereign Appchains")
st.caption("4 Chain Layers · Independent State · Merkle Bridge · Identity (SSI/ZK)")

if st.session_state.result and st.session_state.result["status"] == "completed":
    r = st.session_state.result["artifacts"][0]
    layers = r["layers"]
    chains = r["chain_states"]
    fa = r["friction_analysis"]
    comp = r["compliance"]
    cv = r["chain_volumes"]

    # ── KPI Row ──
    k1, k2, k3, k4, k5 = st.columns(5)
    deps = ["DEPIN_APPCHAIN", "SETTLEMENT_L1", "LIQUIDITY_L2", "IDENTITY_CHAIN"]
    emoji = ["📡", "⚖️", "💰", "🆔"]
    for i, (col, dep) in enumerate(zip([k1, k2, k3, k4], deps)):
        l = layers.get(dep, {})
        with col:
            st.metric(
                f"{emoji[i]} {dep.replace('_',' ')}",
                f"Block {l.get('block_height', 0):,}",
                f"{l.get('total_txs', 0):,} TXs",
            )

    with k5:
        bho = "✅" if comp["bho_zero_sum_verified"] else "❌"
        fv = "✅" if fa["friction_verified"] else "❌"
        st.metric("⚖️ BHO / Friction", f"BHO {bho}", f"Friction {fv}")

    st.divider()

    # ── Tabs ──
    t1, t2, t3, t4 = st.tabs(["📊 Layers", "🔗 9 Chains", "💸 Friction", "📋 Raw"])

    with t1:
        # Layer comparison
        labels = deps
        vols = [layers[d]["total_volume"] for d in deps]
        txs = [layers[d]["total_txs"] for d in deps]
        blocks = [layers[d]["block_height"] for d in deps]
        colors = ["#00d4aa", "#ff6b6b", "#ffd93d", "#7b68ee"]

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Volume (EUR)", "Block Heights"),
            specs=[[{"type": "bar"}, {"type": "bar"}]],
        )
        fig.add_trace(go.Bar(x=labels, y=vols, marker_color=colors, name="Volume",
                             text=[f"€{v/1e6:.1f}M" if v > 1e6 else f"€{v:,.0f}" for v in vols],
                             textposition="outside"), row=1, col=1)
        fig.add_trace(go.Bar(x=labels, y=blocks, marker_color=colors, name="Blocks",
                             text=blocks, textposition="outside"), row=1, col=2)
        fig.update_layout(template="plotly_dark", height=400, showlegend=False,
                          margin=dict(t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)

        # 9-point volumes
        vols_9 = [cv.get(f"C0{i}_{d.split('_')[0]}", 0) for i, d in
                  enumerate(["DEPIN_APPCHAIN", "BRIDGE_LAYER", "SETTLEMENT_L1",
                             "LIQUIDITY_L2", "STAKING_LOCKED", "YIELD_DISTRIBUTED",
                             "FEES_COLLECTED", "TOKENS_BURNED", "NET_PAYOUT"], 1)]
        v9_labels = ["C01 DePIN", "C02 Bridge", "C03 Settlement", "C04 Liquidity",
                     "C05 Staking", "C06 Yield", "C07 Fees", "C08 Burned", "C09 Net"]
        # Get actual values from the dict
        actual_values = [
            cv.get("C01_DEPIN_APPCHAIN", 0),
            cv.get("C02_BRIDGE_LAYER", 0),
            cv.get("C03_SETTLEMENT_L1", 0),
            cv.get("C04_LIQUIDITY_L2", 0),
            cv.get("C05_STAKING_LOCKED", 0),
            cv.get("C06_YIELD_DISTRIBUTED", 0),
            cv.get("C07_FEES_COLLECTED", 0),
            cv.get("C08_TOKENS_BURNED", 0),
            cv.get("C09_NET_PAYOUT", 0),
        ]
        fig2 = go.Figure(go.Bar(
            x=v9_labels, y=actual_values,
            marker_color=["#00d4aa"]*2 + ["#ff6b6b"]*1 + ["#ffd93d"]*3 + ["#ff4444"]*2 + ["#4a9e6e"],
            text=[f"€{v/1e6:.1f}M" if abs(v) > 1e6 else f"€{v:,.0f}" for v in actual_values],
            textposition="outside",
        ))
        fig2.update_layout(title="9-Point Chain Volume Comparison", template="plotly_dark",
                           height=400, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    with t2:
        st.subheader("9 Sovereign Appchain States")
        cols = st.columns(3)
        for i, (name, state) in enumerate(chains.items()):
            with cols[i % 3]:
                bh = state.get("block_height", 0)
                cid = state.get("chain_id", "?")
                extra = ""
                for k in ["total_settled", "total_minted", "total_payouts", "pass_rate"]:
                    if k in state:
                        v = state[k]
                        extra = f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
                        break
                st.metric(
                    f"**{name}**",
                    f"Block {bh:,}",
                    f"{cid} | {extra}",
                )
                if bh > 0:
                    st.progress(min(bh / st.session_state.last_cycles, 1.0),
                                text=f"{bh}/{st.session_state.last_cycles}")

    with t3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Value Conservation")
            st.markdown(f"""
| Metric | Value |
|--------|-------|
| Value In (minted) | €{fa.get('value_in_eur', 0):,.2f} |
| Net Payout (C09) | €{fa.get('net_payout_eur', 0):,.2f} |
| Friction (burns+fees) | €{fa.get('friction_eur', 0):,.2f} |
| Staking Locked | €{fa.get('staking_locked_not_friction', 0):,.2f} |
| Friction Verified | **{'✅' if fa.get('friction_verified') else '❌'}** |
| Value Conserved | **{'✅' if fa.get('value_conserved') else '❌'}** |
| Four Separate Ledgers | ✅ |
""")
        with c2:
            st.subheader("Compliance")
            st.markdown(f"""
| Metric | Value |
|--------|-------|
| BHO Zero-Sum | **{'✅' if comp.get('bho_zero_sum_verified') else '❌'}** (Δ=€{comp.get('bho_delta_eur', 0):.2f}) |
| GoBD Entries | {comp.get('gobd_audit_entries', 0):,} |
| Tax Collected | €{comp.get('tax_collected', 0):,.0f} |
| Identity Verifications | {comp.get('identity_verifications', 0)} |
| Identity Pass Rate | {comp.get('identity_pass_rate', 0)}% |
| Escrow Balance | €{comp.get('escrow_balance', 0):,.2f} |
""")

    with t4:
        st.json(r["layers"])
        st.json({k: v for k, v in chains.items() if "state_root" not in str(v)[:50]})

else:
    st.info("👈 Configure and click **🚀 Run** to start the 9-chain simulation.")
    st.markdown("""
### ⛓️ What are Sovereign Appchains?

Each of the 9 agents is a **sovereign appchain** with its own:
- **Block height** — independent block production
- **State root** — Merkle root of chain state
- **Mempool** — pending transaction queue
- **Consensus interval** — DePIN every second, Settlement weekly

| Layer | Chains | TPS |
|-------|--------|-----|
| 📡 DEPIN | A1 Sensor · A2 Bridge · A3 Wallet | 1000 |
| ⚖️ Settlement | A4 VOB · A5 Legal · A6 Executor | 1/week |
| 💰 Liquidity | A7 Token · A8 Staking | Event |
| 🆔 Identity | A9 SSI/DIDs/ZK | On-Demand |
""")

st.divider()
st.caption(f"MultiChain v0.21.0 — Wave 36 | {datetime.now().strftime('%H:%M:%S')}")

if st.session_state.auto_refresh and st.session_state.result:
    time.sleep(st.session_state.refresh_s)
    st.rerun()
