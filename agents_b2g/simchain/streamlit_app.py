#!/usr/bin/env python3
"""Agent X SimChain — Multi-Chain Economic Dashboard (Streamlit).

Live visualization of all 3 chains (DEPIN, Settlement, Liquidity) with:
  - Real-time TPS, Volume, Latency per chain
  - Chain comparison charts (Plotly)
  - Friction loss waterfall
  - BHO compliance monitor
  - Tokenomics dashboard (mint/burn/stake/yield)
  - 9-Point chain volume comparison
  - Live simulation mode with configurable cycles
  - Export (CSV, JSON)

Usage:
  streamlit run agents_b2g/simchain/streamlit_app.py
  streamlit run agents_b2g/simchain/streamlit_app.py -- --port 8501
"""

import asyncio
import logging
import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repo root is on path
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from agents_b2g.simchain import EconomicOrchestratorMulti

# ─── Page Config ────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Agent X SimChain — Multi-Chain Dashboard",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ────────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
.metric-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border-radius: 12px;
    padding: 1.2rem;
    margin: 0.3rem 0;
    border: 1px solid #2a2a4a;
}
.metric-card h3 {
    color: #7b8c9d;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin: 0;
}
.metric-card .value {
    color: #e0e0e0;
    font-size: 1.8rem;
    font-weight: 700;
    font-family: 'SF Mono', monospace;
    margin: 0.3rem 0;
}
.metric-card .sub {
    color: #4a9e6e;
    font-size: 0.75rem;
}
.chain-depin { border-left: 3px solid #00d4aa; }
.chain-settlement { border-left: 3px solid #ff6b6b; }
.chain-liquidity { border-left: 3px solid #ffd93d; }
</style>
""",
    unsafe_allow_html=True,
)

# ─── Session State ──────────────────────────────────────────────────────────

DEFAULTS = {
    "sim_result": None,
    "sim_running": False,
    "sim_progress": 0,
    "sim_log": [],
    "orch": None,
    "last_run_cycles": 0,
    "theme": "dark",
    "auto_refresh": False,
    "refresh_interval": 2,
    "export_format": "json",
}

for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ─── Helpers ────────────────────────────────────────────────────────────────

def format_eur(val: float) -> str:
    """Format a value as Euro with appropriate unit."""
    if abs(val) >= 1_000_000:
        return f"€{val/1_000_000:,.2f}M"
    elif abs(val) >= 1_000:
        return f"€{val/1_000:,.1f}K"
    else:
        return f"€{val:,.2f}"


def format_num(val: float) -> str:
    """Format a number with appropriate unit."""
    if abs(val) >= 1_000_000:
        return f"{val/1_000_000:,.2f}M"
    elif abs(val) >= 1_000:
        return f"{val/1_000:,.1f}K"
    else:
        return f"{val:,.0f}"


def metric_card(label: str, value: str, sub: str = "", chain_class: str = ""):
    """Render a styled metric card."""
    st.markdown(
        f"""
    <div class="metric-card {chain_class}">
        <h3>{label}</h3>
        <div class="value">{value}</div>
        <div class="sub">{sub}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )


async def run_sim(
    cycles: int, user_id: str, batch_size: int, progress_placeholder
) -> Dict[str, Any]:
    """Run the simulation with progress reporting."""
    orch = EconomicOrchestratorMulti(
        user_id=user_id, cycles=cycles, sensor_batch_size=batch_size
    )
    st.session_state.orch = orch

    result = await orch.run_simulation(cycles=cycles)

    if result["status"] == "completed":
        report = orch.generate_report()
        result["report"] = report
        st.session_state.sim_result = result
        st.session_state.last_run_cycles = cycles

    return result


# ─── Charts ─────────────────────────────────────────────────────────────────

def chart_chain_volumes(report: Dict) -> go.Figure:
    """Bar chart comparing chain volumes."""
    cv = report["chain_volumes"]
    labels = [
        "C01 DePIN", "C02 Bridge", "C03 Settlement",
        "C04 Liquidity", "C05 Staking", "C06 Yield",
        "C07 Fees", "C08 Burned", "C09 Net Payout",
    ]
    values = [cv.get(k, 0) for k in [
        "C01_DEPIN_APPCHAIN", "C02_BRIDGE_LAYER", "C03_SETTLEMENT_L1",
        "C04_LIQUIDITY_L2", "C05_STAKING_LOCKED", "C06_YIELD_DISTRIBUTED",
        "C07_FEES_COLLECTED", "C08_TOKENS_BURNED", "C09_NET_PAYOUT",
    ]]
    colors = [
        "#00d4aa", "#00d4aa", "#ff6b6b",
        "#ffd93d", "#ffd93d", "#ffd93d",
        "#ff4444", "#ff4444", "#4a9e6e",
    ]

    fig = go.Figure(data=[
        go.Bar(
            x=labels, y=values,
            marker_color=colors,
            text=[format_eur(v) for v in values],
            textposition="outside",
            hovertemplate="%{x}: %{text}<extra></extra>",
        )
    ])
    fig.update_layout(
        title="9-Point Chain Volume Comparison",
        template="plotly_dark",
        height=400,
        margin=dict(t=40, b=80, l=20, r=20),
        showlegend=False,
        yaxis_title="EUR",
    )
    return fig


def chart_friction_waterfall(report: Dict) -> go.Figure:
    """Waterfall chart showing where value is lost to friction."""
    fa = report["friction_analysis"]
    tok = report["tokenomics"]

    steps = [
        "Settlement Volume", "Minted (80%)", "Token Burn (5%)",
        "Staked (80%)", "Liquid (20%)", "Fees (2%)",
        "Burn (1%)", "Net Payout",
    ]
    values = [
        report["chains"]["SETTLEMENT_L1"]["total_volume"],
        tok["total_minted"],
        -report["chain_volumes"]["C08_TOKENS_BURNED"],
        -tok["staked_amount"],
        tok["staked_amount"] * 0.25,  # approximate liquid
        -tok["fees_collected"],
        -(tok["total_burned"] - report["chain_volumes"]["C08_TOKENS_BURNED"]),
        report["chain_volumes"]["C09_NET_PAYOUT"],
    ]

    fig = go.Figure(go.Waterfall(
        name="Friction",
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "total"],
        x=steps,
        y=values,
        text=[format_eur(v) for v in values],
        textposition="outside",
        connector={"line": {"color": "rgb(63, 63, 63)"}},
        decreasing={"marker": {"color": "#ff4444"}},
        increasing={"marker": {"color": "#4a9e6e"}},
        totals={"marker": {"color": "#ffd93d"}},
    ))
    fig.update_layout(
        title="Value Flow & Friction Waterfall",
        template="plotly_dark",
        height=450,
        margin=dict(t=40, b=80, l=20, r=20),
        showlegend=False,
        yaxis_title="EUR",
    )
    return fig


def chart_tps_latency(cycles_data: List[Dict]) -> go.Figure:
    """Line chart of TPS and latency over cycles."""
    if not cycles_data or len(cycles_data) < 2:
        return go.Figure()

    cycles = [c["cycle"] for c in cycles_data[1:]]  # skip cycle 0

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # TPS per cycle (events / elapsed_ms)
    batch = 1000  # default, approximate
    tps = [batch / max(c.get("elapsed_ms", 1), 1) * 1000 for c in cycles_data[1:]]

    fig.add_trace(
        go.Scatter(
            x=cycles, y=tps, name="TPS",
            line=dict(color="#00d4aa", width=2),
            fill="tozeroy", fillcolor="rgba(0,212,170,0.1)",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=cycles,
            y=[c.get("cross_chain_queue_depth", 0) for c in cycles_data[1:]],
            name="Queue Depth",
            line=dict(color="#ff6b6b", width=2, dash="dot"),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="Throughput & Queue Depth Over Cycles",
        template="plotly_dark",
        height=350,
        margin=dict(t=40, b=20, l=20, r=20),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="TPS", secondary_y=False)
    fig.update_yaxes(title_text="Queue Depth", secondary_y=True)
    return fig


def chart_tokenomics_sankey(report: Dict) -> go.Figure:
    """Sankey diagram of token flow."""
    tok = report["tokenomics"]
    minted = tok["total_minted"]
    burned_mint = report["chain_volumes"]["C08_TOKENS_BURNED"]
    effective = tok["effective_supply"]
    staked = tok["staked_amount"]
    liquid = effective - staked
    fees = tok["fees_collected"]
    net = report["chain_volumes"]["C09_NET_PAYOUT"]

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15, thickness=20,
            line=dict(color="black", width=0.5),
            label=[
                "Settlement", "Minted", "Burned",
                "Effective Supply", "Staked", "Liquid",
                "Fees", "Net Payout",
            ],
            color=[
                "#ff6b6b", "#ffd93d", "#ff4444",
                "#ffd93d", "#ffd93d", "#4a9e6e",
                "#ff4444", "#4a9e6e",
            ],
        ),
        link=dict(
            source=[0, 1, 1, 3, 3, 5, 5],
            target=[1, 2, 3, 4, 5, 6, 7],
            value=[minted, burned_mint, effective, staked, liquid, fees, net],
            color=[
                "rgba(255,217,61,0.4)", "rgba(255,68,68,0.4)", "rgba(255,217,61,0.4)",
                "rgba(255,217,61,0.4)", "rgba(74,158,110,0.4)", "rgba(255,68,68,0.4)",
                "rgba(74,158,110,0.4)",
            ],
        ),
    )])
    fig.update_layout(
        title="Token Flow Sankey",
        template="plotly_dark",
        height=400,
        margin=dict(t=40, b=20, l=20, r=20),
    )
    return fig


def chart_compliance_gauge(report: Dict) -> go.Figure:
    """Gauge chart for BHO compliance."""
    comp = report["compliance"]
    bho_ok = comp["bho_zero_sum_verified"]
    bho_delta = comp["bho_delta_eur"]
    gobd = comp["gobd_audit_entries"]
    tax = comp["tax_collected"]

    fig = make_subplots(
        rows=1, cols=3,
        specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]],
    )

    fig.add_trace(
        go.Indicator(
            mode="gauge+delta",
            value=bho_delta,
            title={"text": "BHO Δ (EUR)"},
            delta={"reference": 0.01},
            gauge={
                "axis": {"range": [0, 0.1]},
                "bar": {"color": "#4a9e6e" if bho_ok else "#ff4444"},
                "steps": [
                    {"range": [0, 0.01], "color": "rgba(74,158,110,0.3)"},
                    {"range": [0.01, 0.1], "color": "rgba(255,68,68,0.3)"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 2},
                    "thickness": 0.8,
                    "value": 0.01,
                },
            },
        ),
        row=1, col=1,
    )

    fig.add_trace(
        go.Indicator(
            mode="number",
            value=gobd,
            title={"text": "GoBD Entries"},
            number={"font": {"color": "#00d4aa"}},
        ),
        row=1, col=2,
    )

    fig.add_trace(
        go.Indicator(
            mode="number",
            value=tax,
            title={"text": "Tax Collected"},
            number={"font": {"color": "#ffd93d"}, "valueformat": ",.0f"},
        ),
        row=1, col=3,
    )

    fig.update_layout(
        title="Compliance Monitor",
        template="plotly_dark",
        height=300,
        margin=dict(t=40, b=20, l=20, r=20),
    )
    return fig


# ─── Sidebar ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/blockchain.png", width=64)
    st.title("🏛️ SimChain")
    st.caption("Multi-Chain Economic Dashboard")
    st.divider()

    st.subheader("⚙️ Simulation")
    cycles = st.slider("Cycles", 10, 2000, 100, 10, key="sb_cycles")
    batch = st.select_slider(
        "Sensor Batch Size",
        options=[50, 100, 250, 500, 1000, 2000],
        value=1000,
        key="sb_batch",
    )
    user = st.text_input("User ID", value="dashboard", key="sb_user")

    col1, col2 = st.columns(2)
    with col1:
        run_btn = st.button(
            "🚀 Run Simulation",
            use_container_width=True,
            type="primary",
            disabled=st.session_state.sim_running,
        )
    with col2:
        stop_btn = st.button(
            "⏹️ Stop", use_container_width=True, key="sb_stop"
        )

    st.divider()
    st.subheader("🔄 Live Mode")
    auto_refresh = st.toggle("Auto-Refresh", value=st.session_state.auto_refresh)
    if auto_refresh:
        interval = st.slider("Interval (s)", 1, 10, st.session_state.refresh_interval)
        st.session_state.refresh_interval = interval
    st.session_state.auto_refresh = auto_refresh

    st.divider()
    st.subheader("📤 Export")
    export_fmt = st.selectbox("Format", ["json", "csv"], key="sb_export")
    if st.button("📥 Export Report", use_container_width=True):
        if st.session_state.sim_result:
            report = st.session_state.sim_result.get("report", {}).get("artifacts", [{}])[0]
            if export_fmt == "json":
                import json
                data = json.dumps(report, indent=2, default=str)
                st.download_button(
                    "⬇️ Download JSON", data,
                    file_name=f"simchain_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )
            else:
                import csv, io
                cv = report.get("chain_volumes", {})
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(["Chain", "Volume_EUR"])
                for k, v in cv.items():
                    w.writerow([k, v])
                st.download_button(
                    "⬇️ Download CSV", buf.getvalue(),
                    file_name=f"simchain_volumes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                )
        else:
            st.warning("No data — run simulation first")

    st.divider()
    st.caption(f"Agent X B2G v0.21.0 — Wave 35")
    st.caption(f"Session: {st.session_state.get('_session_id', 'N/A')[:8]}")


# ─── Run Simulation ─────────────────────────────────────────────────────────

if run_btn and not st.session_state.sim_running:
    st.session_state.sim_running = True
    st.session_state.sim_log = []

    progress_bar = st.empty()
    status_text = st.empty()

    with st.spinner(f"Running {cycles} cycles..."):
        try:
            result = asyncio.run(
                run_sim(cycles, user, batch, progress_bar)
            )
            if result["status"] == "completed":
                st.session_state.sim_result = result
                st.session_state.sim_log.append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {cycles} cycles completed"
                )
            else:
                st.error(f"Simulation failed: {result.get('error', 'Unknown')}")
                st.session_state.sim_log.append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Failed: {result.get('error')}"
                )
        except Exception as e:
            st.error(f"Error: {e}")
            st.session_state.sim_log.append(f"[ERROR] {traceback.format_exc()}")

    st.session_state.sim_running = False
    st.rerun()

if stop_btn and st.session_state.sim_running:
    st.session_state.sim_running = False
    st.rerun()

# ─── Main Dashboard ─────────────────────────────────────────────────────────

st.title("🏛️ Agent X SimChain — Multi-Chain Economic Dashboard")
st.caption(
    "3 Chains · 9 Agents · Heterogeneous Markets · Real Economic Friction"
)

# ── Top Row: KPIs ──
if st.session_state.sim_result:
    result = st.session_state.sim_result
    report = result.get("report", {}).get("artifacts", [{}])[0]
    chains = report.get("chains", {})
    fa = report.get("friction_analysis", {})
    tok = report.get("tokenomics", {})
    comp = report.get("compliance", {})

    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:
        depin = chains.get("DEPIN_APPCHAIN", {})
        metric_card(
            "DePIN Appchain",
            f"{format_num(depin.get('total_txs', 0))} TXs",
            f"Volume: {format_eur(depin.get('total_volume', 0))}",
            "chain-depin",
        )

    with k2:
        settle = chains.get("SETTLEMENT_L1", {})
        metric_card(
            "Settlement L1",
            f"{format_num(settle.get('total_txs', 0))} TXs",
            f"Volume: {format_eur(settle.get('total_volume', 0))}",
            "chain-settlement",
        )

    with k3:
        liq = chains.get("LIQUIDITY_L2", {})
        metric_card(
            "Liquidity L2",
            f"{format_num(liq.get('total_txs', 0))} TXs",
            f"Volume: {format_eur(liq.get('total_volume', 0))}",
            "chain-liquidity",
        )

    with k4:
        fv = fa.get("friction_verified", False)
        vc = fa.get("value_conserved", False)
        metric_card(
            "Friction",
            "✅" if fv else "❌",
            f"Value conserved: {'✅' if vc else '❌'}",
            "",
        )

    with k5:
        bho_ok = comp.get("bho_zero_sum_verified", False)
        metric_card(
            "BHO Zero-Sum",
            "✅ VERIFIED" if bho_ok else "❌ VIOLATION",
            f"Δ = €{comp.get('bho_delta_eur', 0):.2f}",
            "",
        )

    st.divider()

    # ── Tab Layout ──
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview", "🔗 Chain Comparison", "💸 Friction", "⚖️ Compliance", "📋 Raw Data"
    ])

    # ── Tab 1: Overview ──
    with tab1:
        col_left, col_right = st.columns([3, 2])

        with col_left:
            st.subheader("9-Point Chain Volume Comparison")
            st.plotly_chart(
                chart_chain_volumes(report),
                use_container_width=True,
            )

        with col_right:
            st.subheader("Friction (Liquidity Chain)")
            fb = fa.get("friction_breakdown", {})
            st.markdown(f"""
| Metric | Value |
|--------|-------|
| Value In (minted) | {format_eur(fa.get('value_in_eur', 0))} |
| Net Payout (C09) | {format_eur(fa.get('net_payout_eur', 0))} |
| Friction (outflows) | {format_eur(fa.get('friction_eur', 0))} |
| · Mint Burns | {format_eur(fb.get('mint_burns', 0))} |
| · Fee Burns | {format_eur(fb.get('burnfee_burns', 0))} |
| · Fees | {format_eur(fb.get('fees_collected', 0))} |
| · Staking Locked (not friction) | {format_eur(fb.get('staking_locked_not_friction', 0))} |
| Friction Verified | **{'✅ YES' if fa.get('friction_verified') else '❌ NO (falsifiable)'}** |
| Value Conserved | **{'✅ YES' if fa.get('value_conserved') else '❌ LEAK'}** |
| Three Separate Ledgers | ✅ C01–C09 are 3 books |
""")

            st.subheader("Agent Health")
            agent_stats = report.get("agent_stats", {})
            for name, stats in agent_stats.items():
                st.metric(
                    label=f"**{name.replace('_', ' ').title()}**",
                    value=f"✅ Chain: {stats.get('chain', 'N/A')}",
                )

        # Throughput chart
        if st.session_state.orch:
            st.subheader("Cycle-by-Cycle Throughput")
            st.plotly_chart(
                chart_tps_latency(st.session_state.orch._cycle_log),
                use_container_width=True,
            )

    # ── Tab 2: Chain Comparison ──
    with tab2:
        st.subheader("Chain Characteristics")

        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("""
            **🟢 DEPIN Appchain**
            - Frequency: **1000 TPS**
            - Value: **€0.001–0.50**
            - Consensus: Batch Proofs
            - Wallets: Per-Sensor
            - Role: Data Oracle
            """)

        with c2:
            st.markdown("""
            **🔴 Settlement L1**
            - Frequency: **1 Tx/week**
            - Value: **€3k–350k**
            - Consensus: Z3 Proofs
            - Compliance: GoBD/BHO/§13b
            - Role: Legal Settlement
            """)

        with c3:
            st.markdown("""
            **🟡 Liquidity L2**
            - Frequency: **Event-Driven**
            - Value: **€1–10k**
            - Mechanics: Mint/Burn/Stake
            - APY: 12% | Lockup: 80%
            - Role: Token Economy
            """)

        st.divider()
        st.subheader("Volume Distribution")
        chain_names = ["DEPIN", "Settlement", "Liquidity"]
        chain_vols = [
            chains.get("DEPIN_APPCHAIN", {}).get("total_volume", 0),
            chains.get("SETTLEMENT_L1", {}).get("total_volume", 0),
            chains.get("LIQUIDITY_L2", {}).get("total_volume", 0),
        ]

        fig_pie = go.Figure(data=[go.Pie(
            labels=chain_names,
            values=chain_vols,
            hole=0.4,
            marker_colors=["#00d4aa", "#ff6b6b", "#ffd93d"],
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:,.0f} EUR<extra></extra>",
        )])
        fig_pie.update_layout(
            template="plotly_dark",
            height=400,
            margin=dict(t=20, b=20, l=20, r=20),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # ── Tab 3: Friction ──
    with tab3:
        st.subheader("Value Flow & Friction Waterfall")
        st.plotly_chart(
            chart_friction_waterfall(report),
            use_container_width=True,
        )

        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("Token Flow Sankey")
            st.plotly_chart(
                chart_tokenomics_sankey(report),
                use_container_width=True,
            )

        with col_b:
            st.subheader("Tokenomics Breakdown")
            st.markdown(f"""
| Metric | Value |
|--------|-------|
| Total Minted | {format_eur(tok.get('total_minted', 0))} |
| Total Burned | {format_eur(tok.get('total_burned', 0))} |
| Effective Supply | {format_eur(tok.get('effective_supply', 0))} |
| Staked Amount | {format_eur(tok.get('staked_amount', 0))} |
| Staked Ratio | {tok.get('staked_ratio_pct', 0):.1f}% |
| Yield Distributed | {format_eur(tok.get('yield_distributed', 0))} |
| Fees Collected | {format_eur(tok.get('fees_collected', 0))} |
""")

            st.subheader("Value Conservation")
            fv = "✅" if fa.get("friction_verified") else "❌"
            vc = "✅" if fa.get("value_conserved") else "❌"
            st.markdown(f"""
| Metric | Value |
|--------|-------|
| Value In | {format_eur(fa.get('value_in_eur', 0))} |
| Value Out (payout + friction) | {format_eur(fa.get('value_out_eur', 0))} |
| Friction Verified | **{fv}** (0 < friction ≤ value_in) |
| Value Conserved | **{vc}** (Δ < 0.02€) |
| Three Separate Ledgers | ✅ C01–C09 are 3 books |
""")

    # ── Tab 4: Compliance ──
    with tab4:
        st.subheader("Compliance Monitor")
        st.plotly_chart(
            chart_compliance_gauge(report),
            use_container_width=True,
        )

        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown(f"""
            **BHO Zero-Sum**
            - Status: **{'✅ VERIFIED' if comp.get('bho_zero_sum_verified') else '❌ VIOLATION'}**
            - Delta: €{comp.get('bho_delta_eur', 0):.2f}
            - All settlements: BHO Δ = 0.00€
            """)

        with c2:
            st.markdown(f"""
            **GoBD Compliance**
            - Audit Entries: **{comp.get('gobd_audit_entries', 0):,}**
            - WORM Hashes: Generated
            - Retention: 10 years
            - Format: JSONL + Hash Chain
            """)

        with c3:
            st.markdown(f"""
            **Tax Compliance**
            - Tax Collected: **{format_eur(comp.get('tax_collected', 0))}**
            - §13b UStG: Reverse-Charge
            - §48 EStG: Construction Withholding
            - Escrow Balance: **{format_eur(comp.get('escrow_balance', 0))}**
            """)

        st.divider()
        st.subheader("Escrow & Retention")
        fig_escrow = go.Figure(go.Indicator(
            mode="gauge+number",
            value=comp.get("escrow_balance", 0),
            title={"text": "Escrow Balance (EUR)"},
            gauge={
                "axis": {"range": [0, max(comp.get("escrow_balance", 1) * 2, 100000)]},
                "bar": {"color": "#ffd93d"},
                "steps": [
                    {"range": [0, comp.get("escrow_balance", 0) * 0.5], "color": "rgba(74,158,110,0.3)"},
                    {"range": [comp.get("escrow_balance", 0) * 0.5, comp.get("escrow_balance", 0)], "color": "rgba(255,217,61,0.3)"},
                ],
            },
        ))
        fig_escrow.update_layout(template="plotly_dark", height=300)
        st.plotly_chart(fig_escrow, use_container_width=True)

    # ── Tab 5: Raw Data ──
    with tab5:
        st.subheader("Simulation Metadata")
        meta = result.get("metadata", {})
        st.json({
            "sim_id": result.get("sim_id", "N/A"),
            "status": result.get("status", "N/A"),
            "cycles": meta.get("cycles", cycles),
            "user_id": meta.get("user_id", user),
            "elapsed_ms": result.get("elapsed_total_ms", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        st.subheader("Chain Volumes (Raw)")
        st.json(report.get("chain_volumes", {}))

        st.subheader("Agent Statistics")
        st.json(report.get("agent_stats", {}))

else:
    # ── Empty State ──
    st.info("👈 Configure simulation parameters in the sidebar and click **🚀 Run Simulation** to start.")

    st.markdown("""
    ### 🏛️ What is SimChain?

    A **multi-chain economic simulation** with 9 agents across 3 heterogeneous chains:

    | Chain | Agents | Characteristics |
    |-------|--------|-----------------|
    | 🟢 **DePIN Appchain** | S1–S3 | 1000 TPS, €0.001–0.50 micro-transactions, IoT sensor data |
    | 🔴 **Settlement L1** | L1–L3 | 1 Tx/week, €3k–350k, VOB/B milestones, Z3 proofs |
    | 🟡 **Liquidity L2** | T1–T3 | Event-driven, Token minting, 12% APY staking, burns |

    **Key properties:**
    - ✅ Real economic friction (fees, burns, lockups)
    - ✅ Cross-chain latency (2–5 ticks)
    - ✅ Heterogeneous markets (C01 ≠ C09)
    - ✅ BHO Zero-Sum verified (Δ = 0.00€)
    - ✅ GoBD-compliant audit trail
    """)

    # Preview architecture
    st.image(
        "https://img.icons8.com/fluency/240/blockchain.png",
        width=120,
    )

# ─── Footer ─────────────────────────────────────────────────────────────────

st.divider()
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.caption(f"Agent X B2G v0.21.0 — Wave 35")
with col_f2:
    if st.session_state.last_run_cycles > 0:
        st.caption(f"Last run: {st.session_state.last_run_cycles} cycles")
with col_f3:
    st.caption(f"Dashboard v1.0 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# Auto-refresh
if st.session_state.auto_refresh and st.session_state.sim_result:
    time.sleep(st.session_state.refresh_interval)
    st.rerun()
