#!/usr/bin/env python3
"""Streamlit Kämmerer-Dashboard — Agent X Final Veredelung.

Start:  streamlit run agents_b2g/finale/streamlit_app.py

Zeigt BHO-Nullsummen-Balken, Z3-Proof-Status, Audit-Trail-Timeline
und System-Health in Echtzeit.

Author: Agent X — Final Veredelung (Wave 34)
"""

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import streamlit as st
try:
    import plotly.graph_objects as go
    PLOTLY = True
except ImportError:
    go = None  # type: ignore
    PLOTLY = False
from datetime import datetime

from agents_b2g.finale import FinaleOrchestrator

# ── Page config ──────────────────────────────────────────────────
st.set_page_config(
    page_title="Agent X — Kämmerer-Dashboard",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Initialize orchestrator ──────────────────────────────────────
@st.cache_resource
def get_orchestrator():
    return FinaleOrchestrator(user_id="kaemmerer_mueller")

orch = get_orchestrator()

# ── Sidebar ─────────────────────────────────────────────────────
st.sidebar.title("🏛️ Agent X")
st.sidebar.markdown("**Kämmerer-Dashboard**")
st.sidebar.markdown("---")

# Mode selector
mode = st.sidebar.radio(
    "Modus",
    ["📊 Live-Dashboard", "🔄 Wirtschaftskreislauf", "📦 Audit-Paket", "🔐 Audit-Kette", "ℹ️ System-Info"],
)

# Demo transaction form
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧪 Demo-Transaktion")

with st.sidebar.form("demo_tx"):
    contract_id = st.text_input("Vertrags-ID", "VOB-2026-MUC-8812")
    sector = st.selectbox("Sektor", ["BAU", "HEALTH", "CUSTOMS", "SUBSIDY", "JUSTICE"])
    gross_amount = st.number_input("Brutto (€)", 1000.0, 500000.0, 45000.0, 1000.0)
    contractor = st.text_input("Auftragnehmer", "meier-bau.firma.b2g")
    milestone = st.text_input("Meilenstein", "MILESTONE_05")
    submitted = st.form_submit_button("🚀 Audit-Paket generieren")

# ── Main area ───────────────────────────────────────────────────
st.title("🏛️ Kämmerer-Dashboard")
st.caption(f"BHO-Nullsumme · Z3-Proof · GoBD-Audit-Trail — {datetime.now().strftime('%d.%m.%Y %H:%M')}")

# ── Mode: Live-Dashboard ────────────────────────────────────────
if mode == "📊 Live-Dashboard":
    # Health metrics row
    status = orch.run_health_and_status()
    s = status["artifacts"][0]

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("System Health", f"{s['health']['health_score']}/100",
                  delta=f"Grade {s['health']['health_grade']}")
    with col2:
        st.metric("Audit Einträge", s['audit_stats']['total_entries'])
    with col3:
        vol = s['audit_stats']['total_amount_eur']
        st.metric("Transaktionsvol.", f"{vol:,.0f} €")
    with col4:
        st.metric("Hash-Kette", s['audit_stats']['hash_chain'],
                  delta="✅" if s['audit_stats']['hash_chain'] == "INTACT" else "🚨")
    with col5:
        st.metric("Uptime", f"{s['system']['uptime_hours']}h")

    # Process demo transaction if submitted
    if submitted:
        with st.spinner("Generiere Audit-Paket (Z3-Proof läuft)..."):
            tx = {
                "contract_id": contract_id,
                "sector": sector,
                "gross_amount": gross_amount,
                "net_amount": gross_amount * 0.80,
                "tax_amount": gross_amount * 0.15,
                "retention_amount": gross_amount * 0.05,
                "contractor": contractor,
                "milestone": milestone,
                "timestamp": datetime.now().isoformat(),
            }
            result = orch.generate_full_audit_package(tx)
            a = result["artifacts"][0]

            # Show certificate
            cert = a["certificate"]
            st.success(f"✅ Audit-Paket generiert: {cert['certificate_id']}")

            # BHO bar chart
            dash_data = orch.dashboard.render(tx)
            da = dash_data["artifacts"][0]

            fig = go.Figure(data=[
                go.Bar(
                    x=list(da["bar_data"]["split"].keys()),
                    y=list(da["bar_data"]["split"].values()),
                    marker_color=["#28a745", "#17a2b8", "#ffc107"],
                    text=[f"{v:,.0f} €" for v in da["bar_data"]["split"].values()],
                    textposition="auto",
                )
            ])
            fig.update_layout(
                title=f"BHO-Nullsumme — {cert['contract_id']} "
                      f"(Δ = {cert['bho_delta_eur']:.2f} €)",
                yaxis_title="Euro (€)",
                height=400,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Certificate detail
            with st.expander("📜 Audit-Zertifikat (Details)"):
                st.json(cert)

    # If no transaction submitted yet, show empty state with explanation
    else:
        st.info("👈 Über das Formular links eine Demo-Transaktion starten, "
                "um das Audit-Paket live zu sehen.")

        # Show BHO explanation
        st.markdown("""
        ### 📐 BHO-Nullsummen-Prinzip

        Jede Transaktion wird in drei Teile zerlegt:
        - **80% Netto** → Handwerker (sofort auszahlbar)
        - **15% Steuer (§48b EStG)** → Finanzamt (Bauabzug)
        - **5% Einbehalt (VOB/B §17)** → Sicherheitseinbehalt (4 Jahre)

        Die Summe muss exakt dem Brutto-Betrag entsprechen: **Δ ≤ 0,01 €**
        """)

        # Placeholder chart
        if PLOTLY:
            fig = go.Figure(data=[
                go.Bar(
                    x=["Netto (Handwerker)", "Steuer (§48b)", "Einbehalt (VOB/B)"],
                    y=[36000, 6750, 2250],
                    marker_color=["#28a745", "#17a2b8", "#ffc107"],
                    text=["36.000 €", "6.750 €", "2.250 €"],
                    textposition="auto",
                )
            ])
            fig.update_layout(
                title="Beispiel: 45.000 € Brutto — BHO-Nullsumme (Δ = 0,00 €)",
                yaxis_title="Euro (€)",
                height=400,
            )
            fig.add_annotation(
                x=1, y=38000,
                text="✅ Z3-Proof: MATHEMATICALLY PROVED",
                showarrow=False,
                font=dict(size=14, color="#28a745"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📊 Plotly nicht installiert — Balkendiagramm nicht verfügbar.\n\n"
                    "BHO-Nullsumme: 36.000 € + 6.750 € + 2.250 € = 45.000 € (Δ = 0,00 €)")

# ── Mode: Wirtschaftskreislauf ──────────────────────────────────
elif mode == "🔄 Wirtschaftskreislauf":
    st.subheader("🔄 Wirtschaftlicher Kreislauf — SimChain")
    st.caption("Auftrag → Meilenstein → Settlement → BHO-Prüfung → Audit → nächster Zyklus")

    # Cycle runner controls
    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
    with col_ctrl1:
        cycles = st.number_input("Zyklen", 1, 50, 5, help="Anzahl der simulierten Aufträge")
    with col_ctrl2:
        base_amount = st.number_input("Basis-Betrag (€)", 10000.0, 500000.0, 45000.0, 10000.0,
                                       help="Basis-Betrag pro simuliertem Auftrag")
    with col_ctrl3:
        run_cycles = st.button("🚀 Simulation starten", type="primary")

    if run_cycles:
        results = []
        progress = st.progress(0)
        status_text = st.empty()

        for i in range(cycles):
            status_text.text(f"Zyklus {i+1}/{cycles} — Auftrag → Meilenstein → Settlement → BHO → Audit")

            amount = base_amount * (1.0 + (i * 0.1))  # Steigende Beträge
            tx = {
                "contract_id": f"SIM-{i+1:04d}",
                "sector": "BAU",
                "gross_amount": amount,
                "contractor": f"firma-{(i%5)+1:02d}.b2g",
                "milestone": f"MS_{(i%3)+1}",
                "timestamp": datetime.now().isoformat(),
            }
            result = orch.generate_full_audit_package(tx)
            results.append(result)
            progress.progress((i + 1) / cycles)

        status_text.text("")
        st.success(f"✅ {cycles} Zyklen abgeschlossen")

        # Cycle overview metrics
        total_vol = sum(r["artifacts"][0]["certificate"]["gross_amount_eur"] for r in results)
        all_bho = all(r["artifacts"][0]["certificate"]["bho_invariant_holds"] for r in results)
        z3_verified = sum(1 for r in results if r["artifacts"][0]["certificate"]["z3_proof_verified"])

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Aufträge", cycles)
        with col_m2:
            st.metric("Gesamtvolumen", f"{total_vol:,.0f} €")
        with col_m3:
            st.metric("BHO Δ=0", f"{sum(1 for r in results if r['artifacts'][0]['certificate']['bho_invariant_holds'])}/ {cycles}",
                      delta="✅ 100%" if all_bho else "🚨")
        with col_m4:
            st.metric("Z3-Proofs", f"{z3_verified}/{cycles}",
                      delta="✅" if z3_verified == cycles else "⚠️")

        # Flow visualization
        st.markdown("---")
        st.markdown("### 🔄 Kreislauf-Visualisierung")

        # Bar chart: cumulative volume per cycle
        cum_vol = []
        cum = 0
        for r in results:
            cum += r["artifacts"][0]["certificate"]["gross_amount_eur"]
            cum_vol.append(cum)

        fig_flow = go.Figure()
        fig_flow.add_trace(go.Scatter(
            y=cum_vol, mode="lines+markers",
            name="Kumulatives Volumen",
            line=dict(color="#28a745", width=3),
            marker=dict(size=8),
        ))
        fig_flow.update_layout(
            title="Wirtschaftlicher Kreislauf — Kumuliertes Auftragsvolumen",
            xaxis_title="Zyklus",
            yaxis_title="Euro (€)",
            height=350,
        )
        st.plotly_chart(fig_flow, use_container_width=True)

        # BHO bar for the last transaction
        last = results[-1]["artifacts"][0]
        dash_data = orch.dashboard.render(
            {"contract_id": f"SIM-{cycles:04d}", "sector": "BAU",
             "gross_amount": base_amount * (1.0 + ((cycles-1) * 0.1)),
             "contractor": f"firma-{((cycles-1)%5)+1:02d}.b2g",
             "timestamp": datetime.now().isoformat()}
        )
        da = dash_data["artifacts"][0]

        fig_bho = go.Figure(data=[
            go.Bar(
                x=list(da["bar_data"]["split"].keys()),
                y=list(da["bar_data"]["split"].values()),
                marker_color=["#28a745", "#17a2b8", "#ffc107"],
                text=[f"{v:,.0f} €" for v in da["bar_data"]["split"].values()],
                textposition="auto",
            )
        ])
        fig_bho.update_layout(
            title=f"Letzte Transaktion — BHO-Nullsumme (Δ = {last['certificate']['bho_delta_eur']:.2f} €)",
            yaxis_title="Euro (€)", height=350,
        )
        st.plotly_chart(fig_bho, use_container_width=True)

        # Audit chain for all cycles
        with st.expander("🔐 Audit-Kette (alle Zyklen)"):
            chain_data = []
            for i, r in enumerate(results):
                cert = r["artifacts"][0]["certificate"]
                chain_data.append({
                    "Zyklus": i+1,
                    "Vertrag": cert["contract_id"],
                    "Betrag": cert["gross_amount_eur"],
                    "BHO Δ": cert["bho_delta_eur"],
                    "Z3": cert["z3_proof_status"],
                    "Seal": cert["seal"][:16] + "...",
                })
            st.dataframe(chain_data, use_container_width=True)

    else:
        st.info("👆 Anzahl Zyklen wählen und 'Simulation starten' klicken.")
        st.markdown("""
        ### 🔄 Was passiert in jedem Zyklus?

        1. **Auftrag** — Ein simulierter Bauauftrag wird erstellt
        2. **Meilenstein** — Eine Teilabnahme wird bestätigt
        3. **Settlement** — Atomarer Split: 80% Netto / 15% Steuer / 5% Einbehalt
        4. **BHO-Prüfung** — Z3-Theorem-Prover beweist Δ = 0,00 €
        5. **Audit** — Eintrag in die GoBD-WORM-Hash-Kette
        6. **→ nächster Zyklus** — Das Volumen steigt, die Kette wächst
        """)

# ── Mode: Audit-Paket ───────────────────────────────────────────
elif mode == "📦 Audit-Paket":
    st.subheader("📦 Audit-Paket Generator")

    if submitted:
        tx = {
            "contract_id": contract_id,
            "sector": sector,
            "gross_amount": gross_amount,
            "net_amount": gross_amount * 0.80,
            "tax_amount": gross_amount * 0.15,
            "retention_amount": gross_amount * 0.05,
            "contractor": contractor,
            "milestone": milestone,
            "timestamp": datetime.now().isoformat(),
        }
        result = orch.generate_full_audit_package(tx)
        a = result["artifacts"][0]

        st.success("✅ Audit-Paket generiert!")

        # Dashboard view
        st.markdown("### 📊 Dashboard-Ansicht")
        dash_data = orch.dashboard.render(tx)
        da = dash_data["artifacts"][0]

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Brutto", f"{da['bar_data']['brutto_eur']:,.2f} €")
        with c2:
            st.metric("BHO Δ", f"{da['bho_delta']:.2f} €",
                      delta="✅" if abs(da['bho_delta']) <= 0.01 else "🚨")
        with c3:
            st.metric("Z3-Proof", da['proof']['label'])

        # Certificate
        st.markdown("### 📜 Audit-Zertifikat")
        cert = a["certificate"]
        st.json(cert)

        # Audit trail entry
        st.markdown("### 🔐 Audit-Trail-Eintrag")
        st.json(a["audit_entry"])
    else:
        st.info("👈 Parameter im Seitenmenü eingeben und 'Audit-Paket generieren' klicken.")

# ── Mode: Audit-Kette ───────────────────────────────────────────
elif mode == "🔐 Audit-Kette":
    st.subheader("🔐 Audit-Kette (GoBD)")

    chain = orch.audit.verify_chain()
    c = chain["artifacts"][0]
    stats = orch.audit.get_stats()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Einträge", stats['total_entries'])
    with col2:
        st.metric("Status", c['status'],
                  delta="✅" if c['verified'] else "🚨")
    with col3:
        st.metric("Brüche", c['breaks_found'],
                  delta="✅" if c['breaks_found'] == 0 else "🚨")

    if c['breaks_found'] > 0:
        st.error(f"🚨 {c['breaks_found']} Hash-Ketten-Brüche gefunden!")
        st.json(c['breaks'])
    else:
        st.success("✅ Hash-Kette ist intakt — GoBD-konform (WORM)")

    # Show last entries
    if stats['total_entries'] > 0:
        st.markdown("### Letzte Audit-Einträge")
        entries = orch.audit.trail[-5:]
        for e in reversed(entries):
            with st.expander(f"{e['id']} — {e['timestamp'][:19]}"):
                st.json(e)

    # Generate sample data button
    if st.button("➕ 5 Demo-Einträge generieren"):
        for i in range(5):
            orch.generate_full_audit_package({
                "contract_id": f"VOB-2026-DEMO-{i:04d}",
                "sector": "DEMO",
                "gross_amount": 10000.0 * (i + 1),
                "net_amount": 8000.0 * (i + 1),
                "tax_amount": 1500.0 * (i + 1),
                "retention_amount": 500.0 * (i + 1),
            })
        st.rerun()

# ── Mode: System-Info ───────────────────────────────────────────
elif mode == "ℹ️ System-Info":
    st.subheader("ℹ️ System-Informationen")

    pitch = orch.get_pitch_summary()
    p = pitch["artifacts"][0]

    st.markdown(f"""
    ### 🏛️ Agent X — Final Veredelung (Wave 34)

    | Eigenschaft | Wert |
    |-------------|------|
    | System Health | **{p['system_health']}/100** (Grade {p['grade']}) |
    | Audit-Einträge | **{p['audit_entries']}** |
    | Transaktionsvolumen | **{p['total_volume_eur']:,.0f} €** |
    | Hash-Kette | **{p['hash_chain']}** |
    | BHO-Invarianz | **{p['bho_invariant']}** |
    | Z3-Proofs | **{p['z3_proofs_verified']}** |
    | Uptime | **{p['uptime_hours']}h** |
    | Pitch-Ready | **{'✅ JA' if p['pitch_ready'] else '❌ NEIN'}** |
    """)

    st.markdown("""
    ### 📐 Architektur

    ```
    FinaleOrchestrator
    ├── DashboardRendererAgent  (Streamlit + Plotly)
    ├── AuditTrailAgent          (GoBD-WORM Hash-Kette)
    └── RealtimeMonitorAgent     (Health + Alerting)
    ```
    """)

    st.info("Z3-Theorem-Prover-Service: `services/z3_solver/` — "
            "mathematischer BHO-Invarianz-Beweis via Z3 Real-Arithmetik")
