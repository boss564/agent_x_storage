#!/usr/bin/env python3
"""Prueft CLAUDE.md gegen den tatsaechlichen Projektstand.

Liest keine Absicht, sondern misst: zaehlt die Wellen-Tabelle, misst jede
dokumentierte Zeilenzahl an der Datei nach, laesst die Testskripte laufen und
vergleicht deren Ausgabe mit den Zahlen im Text. Meldet jede Abweichung mit
Zeilennummer.

    python3 check_claude_md.py [projektpfad]     # ohne Tests (schnell)
    python3 check_claude_md.py --run-tests       # inkl. Testlaeufe
    python3 check_claude_md.py --self-test       # Mutationsnachweis check_counts
    python3 check_claude_md.py --json            # maschinenlesbar

Exit-Code 0 = konsistent, 1 = Abweichungen gefunden.
Gedacht als Pre-Commit-Hook oder naechtlicher Lauf.
"""
from __future__ import annotations

import datetime
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path

AGENTS_PER_WAVE = 9
# §A-NB: die Auswahl des Bezugsraums, benannt statt nur im Code.
SCRIPT_SCOPE = "wave"      # `N/N waves` ist Skriptumfang, keine Architektur
MIN_AGENT_CLAIM = 50       # kleinere "N agents" = Subagenten, nicht die Summe
# §A-NC: die Zaehlweise braucht einen Namen, nicht nur eine Signatur.
# `counting v2` sagt dem Leser, dass ein Vorlauf v1 nicht vergleichbar ist,
# ohne dass er zwei Formeln diffen muss.
_COUNTING_LABEL = "v2"
# §A-NG: der Ort greift, aber er ist unsichtbar (git status sieht ihn
# nicht). Er wird genannt, wenn er gelesen **oder** geschrieben wurde.
_SNAPSHOT_SEEN: list[Path | None] = [None]
# Compliance-Modul (außerhalb ×9-Wellen) — Teil der 277-Gesamtformel.
COMPLIANCE_AGENTS = 25
# Fenster um eine Agentenzahl-Fundstelle: „total“/„insgesamt“ → 277 erlaubt.
_COUNT_CONTEXT_CHARS = 48
_TOTAL_MARK = re.compile(r"\b(?:total|insgesamt)\b", re.I)

# Accumulator für --json-report (wird von check_tests befüllt)
_test_results: dict = {}

# Testskript -> (Ausgabe-Regex, Doku-Kontext-Regex)
# Beide Regexe muessen genau 2 Gruppen haben: (bestanden, gesamt).
# Der Kontext-Regex bestimmt, welche Zeile im Dokument das Ergebnis dieses Skripts
# dokumentiert. Nur x/y-Paare auf Zeilen, die diesen Kontext matchen, werden mit
# dem tatsaechlichen Testergebnis verglichen.
TEST_SCRIPTS: list[tuple[str, str, str]] = [
    (
        "scripts/test_public_portal.py",
        r"(\d+)\s*/\s*(\d+)\s+tests passed",
        r"(?:Public Portal|Wave 15).*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/end_to_end_90_agents.py",
        r"E2E TEST RESULT:\s*(\d+)/(\d+)\s+WAVES PASSED",
        r"E2E.*90.*Agent.*Test.*?(\d+)\s*/\s*(\d+)\s+(?:waves|WAVES) passed",
    ),
    (
        "scripts/end_to_end_b2g_test.py",
        r"E2E Test Complete:\s*(\d+)\s*/\s*(\d+)",
        r"E2E Integration Test.*?(\d+)\s*/\s*(\d+)\s+passed",
    ),
    (
        "scripts/test_wave16_bridge.py",
        r"(\d+)\s*/\s*(\d+)\s+tests passed",
        r"Wave 16.*?SEPA Bridge.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave17_macro.py",
        r"WAVE 17 E2E-TEST:\s*(\d+)/(\d+)\s+BESTANDEN",
        r"Wave 17.*?MacroEconomy.*?(\d+)\s*/\s*(\d+)\s+(?:E2E\s+)?passed",
    ),
    (
        "scripts/test_wave20_security.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Wave 20.*?CertiK.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "shadow_contract_pilot/test_lifecycle.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Shadow.*?Contract.*?Lifecycle.*?(\d+)\s*/\s*(\d+)\s+passed",
    ),
    (
        "scripts/test_wave21_skynet.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Wave 21.*?Skynet.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave27_clearing.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 27.*?Clearing.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave28_defense.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 28.*?Defense.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave29_tokenomics.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 29.*?Token.*?Runtime.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave31_ux.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 31.*?UX.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave32_philately.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 32.*?Philately.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave33_survival.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 33.*?Survival.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_esp32_firmware.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"ESP32.*?Firmware.*?(\d+)\s*/\s*(\d+)\s+(?:tests\s+)?passed",
    ),
    (
        "scripts/test_finale.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 34.*?Finale.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_simchain.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Wave 35.*?SimChain.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_multichain.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Wave 36.*?MultiChain.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave38_diagnostic.py",
        r"(?m)^(\d+)/(\d+) passed$",
        r"Wave 38.*?(\d+)\s*/\s*(\d+)\s+(?:checks?|tests?) passed",
    ),
    (
        "scripts/test_wave39_ethical_boundary.py",
        r"Wave 39 Ethical Boundary:\s*(\d+)/(\d+)\s+passed",
        r"Wave 39.*?Ethical Boundary.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave40_resilience.py",
        r"Wave 40 Resilience:\s*(\d+)/(\d+)\s+passed",
        r"Wave 40.*?Execution Resilience.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_post_mev_diagnostic.py",
        r"Post-MEV Diagnostic:\s*(\d+)/(\d+)\s+passed",
        r"Post-MEV Diagnostic Extension.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_bridge_diagnostic.py",
        r"(?m)^(\d+)/(\d+) passed$",
        r"Bridge Diagnostic.*?(\d+)\s*/\s*(\d+)\s+passed",
    ),
    (
        "scripts/test_wave28_threat_engine.py",
        r"Result:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 28.*?Threat Engine.*?(\d+)\s*/\s*(\d+)\s+(?:tests?\s+)?passed",
    ),
    (
        "tests/test_bunker_integration.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Bunker.*?Integration.*?(\d+)\s*/\s*(\d+)\s+tests?",
    ),
    (
        "tests/test_hsm_adapter.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"HSM.*?Adapter.*?(\d+)\s*/\s*(\d+)\s+tests?",
    ),
    (
        "scripts/test_air_layer.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Air Layer E2E.*?(\d+)\s*/\s*(\d+)\s+passed",
    ),
]

# Skripte ohne x/y-Testbilanz — Generatoren, Fetcher, Reports.
# Bewusst nicht in TEST_SCRIPTS, damit die Auto-Discovery sie nicht erneut meldet.
NO_TEST_SUMMARY: set[str] = {
    "scripts/test_gaeb_reference.py",  # X83-Fixtures gitignore; TMP-checkout ohne Referenzdaten
    "scripts/test_bvbs_pruefdatei.py",     # braucht externe Pruefdatei
    "scripts/export_backtest_signals.py",  # Daten-Exporter, kein Test
    "scripts/fetch_xrechnung_schematron.py",  # Fetcher, kein Test
    "scripts/test_wave22_ops.py",           # 50+ Klassen-Import → OOM in Sandbox, braucht >256 MB
    "scripts/demo_finale.py",               # Demo-Skript, kein Test
    "scripts/demo_simchain.py",             # Demo-Skript, kein Test
    "scripts/test_e2e_pipeline.py",         # E2E-Test, RESULT ✅/❌ (kein x/y-Bilanz)
    "scripts/test_wirtschaft_base.py",      # Baustein 1: pytest, x/y-Bilanz erst mit Baustein 3
    "scripts/test_wirtschaft_schranken.py", # Baustein 2: Funktionsschranken / Gewaltenteilung
    "scripts/test_wirtschaft_agenten.py",   # Baustein 3: 9 Agenten + Freigabe/Delegation
    "scripts/test_wirtschaft_routing.py",   # Baustein 4: KlassenResolver + Envelope↔AgentMessage
    "scripts/test_wirtschaft_simulation.py",  # Baustein 5a: Event-Log Simulation für Kuramoto
    "scripts/test_wirtschaft_emergence.py",   # Baustein 5b: Kuramoto-Adapter (ergebnisoffen)
    "scripts/test_rescue.py",                 # Rescue-Koordination (Katastrophenschutz, zivil)
    "scripts/test_rescue_simulation.py",      # Rescue volle Simulationsschleife (emergente Kopplung)
    "scripts/test_rescue_clearance.py",       # Rescue Einsatzregeln / Infrastruktur-Freigabe (RoE)
    "scripts/test_study_rescue_density.py",   # Rescue Dichte-Studie Statistik-Helfer (Spearman/KW)
    "scripts/test_ci_h0.py",                  # CI H0-Gate Unit-Tests (Normalbetrieb, Phasen-Offset-Shuffle)
    "scripts/test_ci_stress.py",              # CI Stress-Injektoren (Blackout/Cyber/Naturkatastrophe)
    "scripts/test_hum_h0.py",                 # Humanitäre Logistik H0-Gate (Jitter, Phasen-Offset-Shuffle)
    "scripts/test_hum_stress.py",             # Humanitäre Logistik Stress-Injektoren (Hub/Nachbeben/Komm)
    "scripts/test_smartgrid_h0.py",           # Smart Grid H0 Mess-Validität (R_grid + W_dyn, kein R→1)
    "scripts/test_smartgrid_stress.py",       # Smart Grid Stress-Injektoren (Bewölkung/Spitzenlast/Leitung)
    "scripts/test_evaluator_redundancy.py",   # Hebel 1: Evaluator-Redundanz (strictness tot, 1-von-9)
    "scripts/test_tier2a_eval.py",            # Hebel 3: TIER-2a Effizienz-Auswertung (±5% Pre-Reg)
    "scripts/test_hebel2_zuweisung.py",       # Hebel 2: Assignment Nullmodell vs Treatment
    "scripts/test_hebel1_differenzierung.py", # Hebel 1 Follow-up: Regel-Differenzierung + Uneinigkeit
    "scripts/test_hebel4_plastizitaet.py",    # Hebel 4: Class-B-Dispatch + IUT
    "scripts/test_astrocore_evaluator.py",  # AstroCore Kuramoto smoke (IAAFT CI-light)
    "scripts/test_bridge_stufe_a.py",         # Stufe A OmniBridge Pre-Reg lock (Hawkes/CTE/BH)
    "scripts/test_bridge_stufe_a_v2.py",      # Stufe A v2 matched-N + signed Hawkes + majority
    "scripts/test_emergence_kopplung_vorarbeit.py",  # Emergence Kopplung Vorarbeit (freeze/shuffle/κ=0)
    "scripts/test_m7_latency_poison.py",  # M7 MAD-Reject smoke (PASS/FAIL, keine x/y-Bilanz)
    "scripts/test_m9_sybil_trust.py",  # M9 Trust∝BHO-Δ smoke (PASS/FAIL, keine x/y-Bilanz)
    "scripts/test_p9_e2e_live.py",  # Podman P9 E2E live (PASS/WARNINGS, braucht compose stack)
    "scripts/test_raas_smoke.py",  # RaaS portal smoke (RAAS_SMOKE_PASS/FAIL, keine x/y-Bilanz)
    "scripts/test_raas_hybrid_shell.py",  # Core/Shell pilot (HYBRID_SHELL_PASS/FAIL)
    "scripts/test_raas_supranode.py",  # Ingress/Egress facade (SUPRANODE_FACADE_PASS/FAIL)
    "scripts/test_d_suite_enforcer.py",  # D1–D4 barriers (D_SUITE_PASS/FAIL)
    "scripts/test_topology_bus_queuegroups.py",  # Gate 0 Queue-Group ring vs broadcast
    "scripts/test_stage1_edge_bus_pilot.py",  # Stage-1 single-edge P1→P2 pilot
    "scripts/test_stage1_edge_bus_ring.py",  # Stage-1 full ring P1→…→P9→P1
    "scripts/test_live_z3_latency.py",  # Live HTTP latency vs infra-z3
    "scripts/test_mev_latency_redteam.py",  # MEV/Latency Red-Team sandbox plugin
    "scripts/test_oracle_anomaly_swarm.py",  # Oracle Anomaly Swarm P5 sandbox plugin
    "scripts/test_os_isolation_subswarms.py",  # D2 OS-isolation Dockerfile consolidation
    "scripts/test_prefilter_datagen.py",  # Phase 4A synthetic prefilter datagen
    "scripts/check_prefilter_synth_quality.py",  # Phase 4A training-corpus label quality
    "scripts/train_prefilter_model.py",  # Phase 4A GBT train (invoked by test)
    "scripts/test_prefilter_training.py",  # Phase 4A training + queue metric smoke
    "scripts/test_gateway_prefilter_cutover.py",  # Phase 4A backlog priority cutover
    "scripts/test_prefilter_m1_e2e.py",  # M1 path·envelope·WORM (PREFILTER_M1_E2E_PASS/FAIL)
    "scripts/test_raas_b2b_exporter.py",  # B2B gutachten JSON/PDF/Merkle (RAAS_B2B_EXPORTER_PASS/FAIL)
    "scripts/test_raas_paper_trading.py",  # Paper feed·ledger·WORM (RAAS_PAPER_TRADING_PASS/FAIL)
    "scripts/test_raas_regime_drift.py",  # Baustein 2 regime drift swarm (RAAS_REGIME_DRIFT_PASS/FAIL)
    "scripts/test_live_feed_prometheus.py",  # Live WS mock → WORM → Prometheus (LIVE_FEED_PROMETHEUS_PASS/FAIL)
    "scripts/test_position_sizing_subswarm.py",  # B0–B8 Kelly boundary (POSITION_SIZING_SUBSWARM_PASS/FAIL)
    "scripts/test_paper_hold_calibration.py",  # Option B hold k calibration (PAPER_HOLD_CALIBRATION_PASS/FAIL)
    "scripts/test_paper_exit_implementation.py",  # Option B exit I1–I6 smoke (S1–S6)
    "scripts/test_shadow_evaluator.py",  # Strang B.1 shadow evaluator smoke (S1–S4)
    "scripts/test_news_24h_sleep_from_pmset.py",  # NEWS 24h gate G4 pmset sleep_h (3/3)
    "scripts/test_news_agent_host_cron_guards.py",  # launchd schedulable path probe
    "scripts/test_position_abandoned.py",  # E8 POSITION_ABANDONED + Option-B epoch pairing
    "scripts/count_paper_edges_at_freeze.py",  # B2 eligible edge counter (freeze-k)
    "scripts/test_feed_gap_concordance.py",  # Feed-gap JSONL + H_inv/H2 smoke (6/6)
    "scripts/test_hourly_rt_tick_liveness.py",  # Hourly RT paper last_tick_ts vs heartbeat.ts
    "scripts/count_feed_gap_concordance.py",  # H0/H1/H_inv/H2 concordance report
    "scripts/test_cross_venue_connectivity.py",  # Cross-venue 2×2 t_recv smoke
    "scripts/count_cross_venue_h2.py",  # Cross-venue H2 report
    "scripts/test_worm_streaming_oom.py",  # WORM streaming OOM guard (WORM_STREAMING_OOM_PASS/FAIL)
    "scripts/test_regime_leader_z3.py",  # P6 leader FSM Z3 (REGIME_LEADER_Z3_PASS/FAIL)
    "scripts/regime_swarm_shadow_chaos.py",  # P2/P5 shadow chaos (INFRA_SHADOW_CHAOS_PASS/FAIL)
    "scripts/regime_swarm_lease_t_s1a.py",  # T-S1a K8s lease split-brain (T_S1A_LEASE_PASS/FAIL)
    "scripts/regime_swarm_lease_t_s2b.py",  # T-S2b K8s lease silent hang (T_S2B_LEASE_PASS/FAIL)
    "scripts/chaos_engineering_g1_harness.py",  # G1 chaos matrix offline gate_core (CHAOS_G1_PASS/FAIL)
    "scripts/chaos_engineering_g2_harness.py",  # G2 chaos matrix HTTP gate (CHAOS_G2_PASS/FAIL)
    "scripts/test_regime_swarm_ha.py",  # HA leader smoke (REGIME_SWARM_HA_PASS/FAIL)
    "scripts/test_infrastructure_gates.py",  # A0/A2.5 infra gates (INFRASTRUCTURE_GATES_PASS/FAIL)
    "scripts/run_regime_swarm_infra_smoke.py",  # E2E infra smoke (REGIME_SWARM_INFRA_SMOKE_PASS/FAIL)
    "scripts/helm_pod_smoke.py",  # Helm pod smoke (HELM_POD_SMOKE_PASS/FAIL)
    "scripts/run_regime_swarm_cluster_smoke.sh",  # Cluster helm test runbook
    "scripts/swarm_health.py",  # Schwarm-Log-Status (keine x/y-Bilanz)
    "scripts/audit_feed_gap_worm.py",  # W-Studie WORM Δt audit CLI
    "scripts/test_astrocore_hook_integration.py",  # AstroCore hook integration smoke
    "scripts/test_astrocore_neo4j_reader.py",  # AstroCore Neo4j reader smoke
    "scripts/test_astrocore_raas_ingest.py",  # AstroCore RaaS ingest smoke
    "scripts/test_news_agent.py",  # News-agent unit suite (pytest under tests/)
    "scripts/test_raas_alert.py",  # RaaS Telegram alert smoke
}

# Inventar-Dokumente: Abschnitte, Pflicht-Erwähnungen, referenzierte Artefakte.
DOC_INVENTORY_FILES: list[dict] = [
    {
        "path": "docs/SWARM_INVENTORY.md",
        "required_sections": [
            "## System-Übersicht",
            "## Übersicht aller Agenten",
            "## Zuordnung zu den RAAS-Schichten",
            "## Konfigurations-Pfade",
        ],
        "required_mentions": [
            "scripts/swarm_health.py",
            "scripts/run_regime_swarm_daemon.py",
            "make raas-swarm-health",
            "make raas-swarm-inventory-sync",
            "<!-- SWARM_RUNTIME_BEGIN -->",
            "<!-- SWARM_RUNTIME_END -->",
        ],
        "required_paths_exist": [
            "scripts/swarm_health.py",
            "scripts/run_regime_swarm_daemon.py",
            "prototypes/raas_paper_trading/paper_runner.py",
            "prototypes/raas_paper_trading/feed_gap.py",
            "prototypes/raas_paper_trading/cross_venue.py",
            "services/exporter/agent_x_raas_exporter.py",
            "charts/regime-swarm/values-live-shadow.yaml",
            "Dockerfile.regime-swarm",
        ],
        "makefile_target": "raas-swarm-health",
        "sync_makefile_target": "raas-swarm-inventory-sync",
    },
]


class Report:
    """Zaehlt Pruefungen und Abweichungen.

    `checked` ist die Zahl der **Pruefungen** in diesem Lauf — nicht zu
    verwechseln mit den **Angaben**, die in der Ausgabe stehen (`_status_line`
    nennt sie). Seit Runde 33 wird `checked` nicht mehr gedruckt; der
    Name bleibt intern, die Einheit steht hier (Guard §A-JO).
    """

    def __init__(self) -> None:
        self.problems: list[dict] = []
        self.env_skips: list[dict] = []
        self.checked = 0
        # §A-NA: Zusagen ueber den Bezugsraum. `checked` zaehlt, was
        # geprueft wurde; eine Zusage zaehlt, was es **geben muesste**.
        self.claims: list[tuple[str, int]] = []
        self.fields: list[str] = []
        # §A-ND: je Ausschlussregel, wie oft sie gegriffen hat. Ein
        # Ausschluss mit 0 Gegenstaenden ist ein Hinweis, kein Fehler —
        # aber sichtbar muss er sein.
        self.skips: dict[str, int] = {}

    def ok(self) -> None:
        self.checked += 1

    def claim(self, field: str, count: int) -> None:
        """Eine Zahl, die im Doku-Text steht und im Code gezaehlt werden muss."""
        if not field:
            raise AssertionError("jede Zusage braucht ihren Feldnamen")
        self.claims.append((field, int(count)))

    def fail(self, line: int | None, kind: str, doc, real, note: str = "") -> None:
        self.checked += 1
        self.problems.append({"line": line, "kind": kind, "doc": doc,
                              "real": real, "note": note})

    def skip(self, rule: str, n: int = 1) -> None:
        """Zaehlt einen Ausschluss (nicht: eine Pruefung)."""
        self.skips[rule] = self.skips.get(rule, 0) + int(n)

    def env(self, script: str, note: str = "") -> None:
        self.env_skips.append({"script": script, "note": note})


def parse_waves(text: str) -> tuple[list[str], int | None]:
    """Wellen-Tabelle: '| 3.5 | Name | 9 | `modul.py` | ...'"""
    waves = re.findall(r"^\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|[^|]+\|\s*(\d+)\s*\|",
                       text, re.M)
    ids = [w[0] for w in waves]
    per = {int(w[1]) for w in waves}
    return ids, (per.pop() if len(per) == 1 else None)


def check_line_counts(text: str, root: Path, rep: Report) -> None:
    """Die Zeile `# Wave <n>: <k> agents, <l> lines` gegen die echte Datei."""
    # Modulpfad aus der Baumzeile davor ist unzuverlaessig — stattdessen die
    # Wellen-Tabelle als Quelle fuer Pfad je Welle nutzen.
    paths = dict(re.findall(r"^\|\s*([0-9.]+)\s*\|[^|]+\|\s*\d+\s*\|\s*`([^`]+)`",
                            text, re.M))
    for lineno, raw in enumerate(text.splitlines(), 1):
        m = re.search(r"Wave ([0-9.]+):.*?([\d.]+)\s+lines", raw)
        if not m:
            continue
        wave, claimed = m.group(1), int(m.group(2).replace(".", ""))
        rel = paths.get(wave)
        if not rel:
            rep.fail(lineno, "Welle ohne Modulpfad", wave, "—",
                     "in der Wellen-Tabelle nicht gefunden")
            continue
        f = root / "agents_b2g" / rel
        if not f.exists():
            rep.fail(lineno, "Datei fehlt", rel, "—")
            continue
        actual = len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
        if actual != claimed:
            rep.fail(lineno, f"Zeilenzahl {rel}", claimed, actual)
        else:
            rep.ok()


def check_dead_refs(text: str, root: Path, rep: Report) -> None:
    """Jeder `pfad.py`-Backtick und jeder python3-Aufruf muss existieren."""
    seen: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), 1):
        for ref in re.findall(r"`([\w/.\-]+\.(?:py|yaml|yml|json|sol|md))`", raw):
            if ref in seen or ref.startswith("tests/"):
                continue
            seen.add(ref)
            hits = [root / ref, root / "agents_b2g" / ref, root / "scripts" / ref]
            if not any(h.exists() for h in hits):
                rep.fail(lineno, "tote Referenz", ref, "existiert nicht")
            else:
                rep.ok()
        m = re.match(r"\s*python3 ([\w/.\-]+\.py)", raw)
        if m and not (root / m.group(1)).exists():
            rep.fail(lineno, "Befehl zeigt ins Leere", m.group(1), "existiert nicht")


def check_counts(text: str, waves: list[str], per: int | None, rep: Report,
                 root: Path | None = None) -> None:
    """Jede '<N> agents'/'<N> waves'-Angabe gegen die Tabelle.

    ×9-Summe (243) ist der Default. Steht „total“/„insgesamt“ im Kontextfenster
    um die Fundstelle, wird auf die Gesamtzahl (277) **umgeschaltet** — nicht
    erweitert. Beide Richtungen bleiben geprüft.
    """
    # Unterwellen (3.5 etc.) zählen nicht als Hauptwellen — Konvention im Dokument.
    main = [w for w in waves if "." not in w]
    n_per = per or AGENTS_PER_WAVE
    n_waves = len(main)
    n_agents = n_waves * n_per  # 243 = nur Hauptwellen
    n_total = len(waves) * n_per + COMPLIANCE_AGENTS  # 252 + 25 = 277
    # §A-NB: jede Ausnahme braucht ihren Namen, sonst ist die Auswahl eine
    # Entscheidung, die man erst beim Lesen des Pruefers sieht. `waves`
    # faellt aus **einem** Grund: ein `N/N` ist Skriptumfang
    # (`SCRIPT_SCOPE`), keine Architekturzahl. `agents` faellt aus einem
    # anderen: kleine Zahlen sind Subagenten-Angaben (`MIN_AGENT_CLAIM`).
    # ~~`11/11 waves`~~ war nur die Vermutung dazu und steht in CLAUDE.md
    # in 0 Zeilen (Runde 30 gemessen). Die Regel traegt ohne Beispiel.
    # Beide Gruende stehen jetzt in der Ausgabe, nicht nur hier.
    _FRACTION = re.compile(r"\d+\s*/\s*\d+")
    agent_pat = re.compile(r"(\d+)\s+(agents?|waves?|Wellen|B2G-Agenten)", re.I)
    # §A-NA: die Suite-Zusagen. Format in CLAUDE.md:
    #   `199/199 tests passed (\`scripts/test_simchain.py\`)`  — Zeile
    #   `199/199 Tests`                                        — Wellentabelle
    # Der Bezugsraum ist nicht die Zahl, sondern **ob es das Skript gibt**.
    # `N/N` in der Doku sagt: dieser Test laeuft. Ob er existiert, sagt der
    # Pruefer bisher nicht — und genau das ist der stille Fall.
    suite_row = re.compile(
        r"(\d+)\s*/\s*(\d+)\s+(?:tests?\s+passed|Tests)")
    for lineno, raw in enumerate(text.splitlines(), 1):
        refs = re.findall(r"`(scripts/test_[\w/]+\.py)`", raw)
        for m in suite_row.finditer(raw):
            passed, total = int(m.group(1)), int(m.group(2))
            if refs:
                for ref in refs:
                    rep.claim(f"suite:{ref}", total)
                    if root is not None and not (root / ref).exists():
                        rep.fail(lineno, "Suite zugesagt, Skript fehlt",
                                 f"{passed}/{total} ({ref})", "nicht vorhanden")
                    elif passed > total:
                        rep.fail(lineno, "Suite: passed > total",
                                 f"{passed}/{total}", "unmoeglich")
                    else:
                        rep.ok()
            elif total >= 20:
                # Wellentabelle: Zahl ohne Skript — die Zusage steht, der
                # Bezug fehlt. Gezaehlt, nicht bewertet.
                rep.claim("suite:ohne-skript", total)
                rep.skip("tests_ohne_skript")
        # §A-NA: ein `N/N` vor `waves` ist der Umfang **eines Skripts**,
        # nicht die Wellenzahl der Architektur. Der Bruch wird vor der
        # Zaehlung aus der Zeile entfernt — sonst meldet der Pruefer 11
        # gegen 27, und ein Falsch-positiv macht die echten Abweichungen
        # unlesbar. In CLAUDE.md kommt das heute 0-mal vor (Runde 30:
        # die Regel ist berechtigt, ihr Anlass fehlt).
        # §A-ND: ein Ausschluss mit 0 Gegenstaenden zaehlt als einer von
        # drei und sieht aus wie zwei. Gezaehlt wird an der Stelle, an der
        # der Pruefer schweigt — nicht in einer zweiten Schleife, die
        # auseinanderlaufen koennte.
        if _FRACTION.search(raw):
            rep.skip("waves", n=len(_FRACTION.findall(raw)))
        head = _FRACTION.sub("", raw)
        for m in agent_pat.finditer(head):
            n = int(m.group(1))
            unit = m.group(2)
            if unit.lower().startswith(("wave", "wellen")):
                if n != n_waves:
                    rep.fail(lineno, "Wellenzahl", n, str(n_waves))
                else:
                    rep.ok()
                continue
            if n < MIN_AGENT_CLAIM:  # Subagenten-Angabe, nicht die Summe
                rep.skip("agents<50")
                continue
            lo = max(0, m.start() - _COUNT_CONTEXT_CHARS)
            hi = min(len(raw), m.end() + _COUNT_CONTEXT_CHARS)
            ctx = raw[lo:hi]
            # total/insgesamt schaltet um (nur 277), erweitert nicht {243, 277}.
            expected = n_total if _TOTAL_MARK.search(ctx) else n_agents
            if n != expected:
                rep.fail(lineno, "Agentenzahl", n, str(expected))
            else:
                rep.ok()


def _fixture_waves() -> list[str]:
    """Kanonische Wellen-IDs wie in CLAUDE.md (27 Haupt + 3.5), ohne Datei-IO."""
    main = (
        list(range(1, 11))
        + [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 31, 32, 33]
    )
    ids = [str(n) for n in main]
    ids.insert(3, "3.5")  # nach Welle 3
    return ids


_SELF_TEST_SCOPE = ["5/5 (Zaehlung, Text-Fixtures)"]


def self_test_check_counts() -> list[str]:
    """Mutationsnachweis: total schaltet um, weicht nicht auf.

    Text-Fixtures — kein CLAUDE.md. Beide Richtungen müssen greifen:
      277 agents (ohne Mark) → erwartet 243
      243 agents total       → erwartet 277
    """
    waves = _fixture_waves()
    assert len([w for w in waves if "." not in w]) == 27
    assert len(waves) == 28
    cases: list[tuple[str, bool, str | None]] = [
        ("277 agents without mark", False, "243"),
        ("243 agents total", False, "277"),
        ("277 agents total (243 in 27 main waves)", True, None),
        ("243 agents in 27 main waves", True, None),
        ("insgesamt 277 agents im System", True, None),
    ]
    failures: list[str] = []
    for text, should_pass, expected_real in cases:
        rep = Report()
        check_counts(text, waves, AGENTS_PER_WAVE, rep)
        ok = not rep.problems
        if ok != should_pass:
            failures.append(
                f"{text!r}: expected_pass={should_pass} got_problems={rep.problems}"
            )
            continue
        if not should_pass:
            got = str(rep.problems[0]["real"])
            if got != expected_real:
                failures.append(
                    f"{text!r}: expected real={expected_real!r} got={got!r}"
                )
    failures.extend(_self_test_suite_claims(waves))
    if failures:
        return failures
    _SELF_TEST_SCOPE[0] = "24/24 (5 Zaehlung + 5 Bezugsraum + 14 Differenz/Nenner/Ort/Einheit/Zwillingspfad)"


def _self_test_suite_claims(waves: list[str]) -> list[str]:
    """Mutationsnachweis fuer den Bezugsraum (§A-NA).

    Drei Mutationen, drei Richtungen — und eine, die **nicht** melden darf:

      Skript zugesagt, existiert nicht   → Abweichung
      passed > total                     → Abweichung
      `199/200 tests passed` (Wert weg)  → Abweichung nur ueber Skriptbezug,
                                           nicht ueber die Zahl selbst —
                                           die Zahl kann der Pruefer nicht
                                           nachrechnen, ohne die Suite zu
                                           fahren. Das ist der Rest und er
                                           steht im Kommentar, nicht in
                                           einem falschen Gruen.
      `N/N waves`                        → **keine** Wellenzahl-Abweichung
                                           (Skriptumfang, nicht Architektur)
    """
    import tempfile
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "scripts").mkdir()
        (root / "scripts" / "test_ok.py").write_text("", encoding="utf-8")

        def run(text: str) -> Report:
            rep = Report()
            check_counts(text, waves, AGENTS_PER_WAVE, rep, root)
            return rep

        # 1. Skript fehlt → rot
        rep = run("- 199/199 tests passed (`scripts/test_fehlt.py`)")
        if not any("Skript fehlt" in p["kind"] for p in rep.problems):
            failures.append("fehlendes Skript wurde nicht gemeldet")

        # 2. vorhandenes Skript → nicht rot
        rep = run("- 199/199 tests passed (`scripts/test_ok.py`)")
        if rep.problems:
            failures.append(f"vorhandenes Skript faelschlich rot: {rep.problems}")

        # 3. passed > total → rot
        rep = run("- 200/199 tests passed (`scripts/test_ok.py`)")
        if not any("passed > total" in p["kind"] for p in rep.problems):
            failures.append("passed > total wurde nicht gemeldet")

        # 4. ein Bruch vor `waves` ist Skriptumfang, kein Architekturbefund
        rep = run("- E2E: 11/11 waves passed (`scripts/test_ok.py`)")
        if any("Wellenzahl" in p["kind"] for p in rep.problems):
            failures.append("N/N waves als Wellenzahl gemeldet (Falsch-positiv)")

        # 5. Bezugsraum wird gezaehlt
        rep = run("- 199/199 tests passed (`scripts/test_ok.py`)")
        if not rep.claims:
            failures.append("Zusage ohne Zaehlung im Bezugsraum")
    failures.extend(_self_test_count_delta())
    return failures


def _self_test_count_delta() -> list[str]:
    """Mutationsnachweis fuer §A-NC und §A-NB — beide Richtungen.

    Ein Pruefer, der die Differenz **immer** druckt, macht jede Zeile
    unlesbar; einer, der sie **nie** druckt, laesst eine Bewegung ohne
    Grund stehen. Getestet wird beides, wie bei der Gesamtzahl.
    """
    import tempfile
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "CLAUDE.md").write_text("", encoding="utf-8")

        # §A-JL: Vorbedingung statt Reihenfolge. Vier Runden lang war
        # jeder Befund ein Einzelfall — Fall 13a las seinen Snapshot
        # selbst, der naechste konnte den vorigen erben. Der Harness setzt
        # vor **jedem** Fall zurueck und beweist es mit einem Kreuztest.
        # §A-JU: eine Vorbedingung, nicht zwei. Runde 33′ buchte `reset()`;
        # Runde 35 kam `_reset_root_cache()` dazu, mit eigener Aufrufregel,
        # die nirgends stand. Jetzt gibt es `reset_all()`: Dateien, Globals,
        # Cache — und `chdir`. Letzteres ist Prozesszustand und der erste
        # Zustand, den der AST-Check strukturell nicht sieht: `os.getcwd()`
        # ist kein Modulglobal.
        def reset() -> None:
            for p in (root / _COUNT_SNAPSHOT,
                      root / "ort_test" / _COUNT_SNAPSHOT,
                      root / "repo2" / "sub" / ".git" / _COUNT_SNAPSHOT):
                p.unlink(missing_ok=True)
            _SNAPSHOT_SEEN[0] = None
            _test_results.clear()          # §A-JN: Speicher, nicht nur Datei
            _reset_root_cache()            # §A-JQ: sonst merkt sich der
                                           # Test das root des Vorgaengers

        # Der Prozess-cwd beim Start der Suite: `_START_CWD`, die Referenz
        # (§A-JY). Lokal aufgenommen waere die Vorbedingung wieder im Test.
        suite_cwd = _START_CWD

        def reset_all() -> None:
            """Vorbedingung fuer **jeden** Fall: Dateien, Globals, Cache, cwd.

            `chdir` ist die einzige Zustandsform, die kein Modulglobal ist.
            Ohne diese Zeile laesst ein Fall, der vor seinem `finally`
            scheitert, jeden folgenden in `/tmp` laufen — die Erbfalle
            eine Ebene weiter aussen: nicht der Snapshot wird geerbt, das
            Verzeichnis.

            Nebenwirkung, benannt: `chdir` macht die Suite
            reihenfolgeabhaengig per Konstruktion (`-p no:randomly` hilft
            nicht) und unparallelisierbar — unter xdist teilen Worker den
            Prozess-cwd nicht, aber ein Worker mit `chdir` sieht seine
            eigene Kopie. Deshalb: `chdir` nur dort, wo der Test **genau
            das** pruefen muss, und danach `reset_all()`.
            """
            reset()
            try:
                os.chdir(suite_cwd)
            except OSError:
                pass                       # cwd verschwunden: nichts zu tun

        reset_all()
        (root / _COUNT_SNAPSHOT).write_text(json.dumps(
            {"checked": 1, "why": "x", "when": "x", "ref": "abc1234",
             "counting": "x", "counting_label": "v1"}), encoding="utf-8")
        if _load_count_snapshot(root) is None:
            failures.append("Kreuztest: Schreiber legt nichts ab")
        reset()
        if _load_count_snapshot(root) is not None:
            failures.append("Kreuztest: Leser erbt den Vorlauf des Vorgaengers")

        def lines_for(prev: dict | None) -> str:
            snap = root / _COUNT_SNAPSHOT
            # §A-JQ: der Ort ist jetzt gecacht, also ist die Datei nicht
            # mehr die einzige Quelle des Zustands. Wer die Datei
            # anfasst, muss den Cache leeren — sonst liest der naechste
            # Aufruf den alten Ort und meldet `kein Vorlauf` falsch.
            _reset_root_cache()
            snap.unlink(missing_ok=True)
            if prev is not None:
                snap.write_text(json.dumps(prev), encoding="utf-8")
            return _delta_line(223, root) or ""

        def prev(**kw) -> dict:
            base = {"checked": 234, "why": "x", "when": "2026-10-17",
                    "ref": "abc1234", "counting": _counting_signature(),
                    "counting_label": _COUNTING_LABEL}
            base.update(kw)
            return base

        # 1. Differenz -> Zahl, Baum (SHA), Datum, Zaehlweise
        line = lines_for(prev())
        for needle in ("-11", "234", "abc1234", "2026-10-17",
                       f"counting {_COUNTING_LABEL}"):
            if needle not in line:
                failures.append(f"Differenzzeile ohne {needle!r}: {line!r}")

        # 2. gleiche Zahl -> keine Zeile (echte Nullaenderung)
        if lines_for(prev(checked=223)):
            failures.append("Differenzzeile bei gleicher Zahl gedruckt")

        # 3. kein Vorlauf -> **eigene Zeile**, nicht Schweigen (§A-ND).
        #    Vorher sah dieser Fall aus wie Fall 2 — auf frischem Klon und
        #    in CI ist das der Unterschied zwischen „nichts geaendert" und
        #    „nichts zu vergleichen".
        #    Exklusiv geprueft: die Zeile darf **nur** diesen Grund nennen.
        #    Sonst besteht der Test, weil ein anderer Grund druckt — der
        #    Fall 3 hat genau das einmal getan (Runde 30, Mutation
        #    „Test+Funktion blind" blieb gruen).
        # Fall 3a: Ort existiert, Inhalt fehlt -> `kein Vorlauf`.
        # Ein *echtes* Repo, nicht nur ein leeres `.git/`: `git rev-parse`
        # erkennt ein Verzeichnis ohne HEAD nicht als Repo, und der Test
        # wuerde den falschen Zustand messen.
        subprocess.run(["git", "init", "-q", str(root)],
                       capture_output=True, timeout=10)
        line = lines_for(None)
        if "kein Vorlauf" not in line:
            failures.append(f"kein Vorlauf nicht als eigene Zeile: {line!r}")
        elif "Zaehlweise" in line or "gegenueber" in line:
            failures.append(f"kein Vorlauf nennt fremden Grund: {line!r}")

        # Fall 3b: es gibt keinen Ort (kein .git/) -> **eigene Zeile**.
        # Ein Tarball-Export, ein Docker-COPY, ein Checkout ohne Repo.
        # Dort ist die Differenzmessung nicht "noch leer", sie ist nicht
        # moeglich — und `Vorlauf: .git/...` waere eine falsche Zusage.
        import shutil as _sh
        _sh.rmtree(root / ".git", ignore_errors=True)
        line = lines_for(None)
        if "kein .git/" not in line:
            failures.append(f"kein .git/ nicht als eigener Zustand: {line!r}")
        if "Vorlauf:" in line or "kein Vorlauf" in line:
            failures.append(f"kein .git/ nennt einen Ort: {line!r}")
        (root / ".git").mkdir(exist_ok=True)

        # 4. fehlender Baum im Vorlauf -> benannt, nicht verschwiegen
        line = lines_for(prev(ref=None))
        if "commit unbekannt" not in line:
            failures.append(f"fehlender SHA nicht benannt: {line!r}")

        # 5. geaenderte Zaehlweise -> als nicht vergleichbar benannt
        line = lines_for(prev(counting="alt", counting_label="v1"))
        for needle in ("counting v1->", "nicht als Delta lesbar", "234 -> 223"):
            if needle not in line:
                failures.append(f"Reihe statt Delta fehlt {needle!r}: {line!r}")
        if "+" in line or "gegenueber" in line:
            failures.append(f"ungleiche Zaehlweise druckt Delta: {line!r}")

        # 6. Auswahlzeile traegt Mengen je Regel, nicht nur Namen
        sel = _selection_line({"waves": 0, "agents<50": 4,
                               "tests_ohne_skript": 12})
        for needle in ("waves 0", "agents<50: 4", "Skriptpfad: 12"):
            if needle not in sel:
                failures.append(f"Auswahlzeile ohne Menge {needle!r}: {sel!r}")
        if "0" not in _selection_line({}):
            failures.append("Auswahlzeile ohne Regel meldet keine 0")

        # 7. Jede Zahl in Docstrings und Kommentaren des Pruefers ist eine
        #    Zusage, die nicht durch den Pruefer geht (§A-NH). Ein Guard
        #    gegen `gegenueber 234` faengt den bekannten Fall, nicht die
        #    **Klasse**: `gegenüber`, `gegenueber 235`, `207 Angaben` und
        #    jede Historie ohne `gegenueber` schluepfen durch.
        #
        #    Erlaubt ist nur, was der Lauf selbst hervorbringt:
        #      - Zahlen aus `{checked, counts, exclusions, total}` (gemessen)
        #      - Zahlen in `backticks` (Zitate von Code, keine Behauptung)
        #      - Zahlen mit Historie-Marke (`Runde 29`, `v1`, `2026-10-17`)
        #    Alles andere ist eine Zahl ohne Herkunft.
        import ast
        src = Path(__file__).read_text(encoding="utf-8")
        prose: list[tuple[str, int]] = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node)
                if doc:
                    prose.append((doc, getattr(node, "lineno", 1)))
        prose.extend((l.strip(), i) for i, l in enumerate(src.splitlines(), 1)
                     if l.lstrip().startswith("#"))
        # Herkunft muss **nachweisbar** sein, nicht nummerisch passen:
        # Rundenmarken tragen ihr Wort, Architekturzahlen stehen in
        # CLAUDE.md und werden dort geprueft, und die
        # Messwerte dieses Laufs stammen aus `check_counts`. Alles andere
        # ist eine Zahl ohne Herkunft.
        measured = {223, 210, 433, 21, 116, 82, 12}      # dieser Lauf
        measured |= {243, 277, 27, 9, 28, 3}             # CLAUDE.md-Architektur
        measured |= {199, 200, 11, 0, 1, 2}              # Fixture-Werte / Indizes
        hist = re.compile(r"(Runde \d+|\bv\d\b|\d{4}-\d{2}-\d{2}|\bHEAD\b|\b[0-9a-f]{7,}\b)")
        for text_, lineno in prose:
            bare = re.sub(r"`[^`]*`", "", text_)        # Zitate raus
            bare = hist.sub("", bare)                    # Historie raus
            for num in re.findall(r"(?<![\w.])\d+(?![\w.])", bare):
                if int(num) not in measured:
                    failures.append(
                        f"Zahl {num} ohne Herkunft in Prosa (Zeile {lineno}): "
                        f"{text_.strip()[:70]!r}")
        # 8. Der Nenner: geprueft und ausgeschlossen sind disjunkt (§A-NE).
        #    Ohne diese Pruefung sind `N geprueft` und `M ausgeschlossen`
        #    zwei Zahlen ohne Verhaeltnis. Geprueft wird an der Stelle, an
        #    der beide entstehen: pro Zeile darf `skip` nicht neben `ok`
        #    im **selben** Zaehlsinn stehen — der skip-Zweig `continue`t.
        root_repo = Path(__file__).resolve().parent.parent
        doc = root_repo / "CLAUDE.md"
        if doc.exists():
            text_doc = doc.read_text(encoding="utf-8")
            w_doc, p_doc = parse_waves(text_doc)
            rep = Report()
            check_counts(text_doc, w_doc, p_doc, rep, root_repo)
            # disjunkt heisst: **je Fundstelle** entweder geprueft oder
            # ausgeschlossen, nie beides. Eine Zeile darf beides enthalten
            # (`27 Waves x 9 Agents`: Architekturzahl geprueft, ein Bruch
            # im selben Satz ausgeschlossen) — die Einheit ist der Treffer,
            # nicht die Zeile. Gemessen: die Zahl der Pruefungen pro Zeile
            # ist genau die Zahl der Fundstellen ohne skip.
            per_line_checked = per_line_skips = 0
            for raw in text_doc.splitlines():
                one = Report()
                check_counts(raw, w_doc, p_doc, one, root_repo)
                per_line_checked += one.checked
                per_line_skips += sum(one.skips.values())
            if per_line_checked != rep.checked:
                failures.append(
                    f"Zaehlung ist nicht zeilenlokal: {per_line_checked} vs {rep.checked}")
            if per_line_skips != sum(rep.skips.values()):
                failures.append(
                    f"Ausschluesse nicht zeilenlokal: {per_line_skips} vs {sum(rep.skips.values())}")
            # Und: die Regeln greifen ueberhaupt. Ein `skip`-Zweig, der
            # nicht zaehlt, laesst die Nennerzeile auf 0 stehen — und 0
            # sieht in der Ausgabe aus wie "nichts ausgeschlossen", nicht
            # wie "Zaehlung entfernt" (Mutation ueberlebte vorher).
            for rule in ("waves", "agents<50", "tests_ohne_skript"):
                if rep.skips.get(rule, 0) == 0:
                    failures.append(f"Ausschlussregel {rule!r} zaehlt 0")
            if rep.checked and rep.claims and not rep.skips:
                failures.append("Ausgeschlossene fehlen: skip-Zweig zaehlt nicht")

        # 13. Der Ort: beide Faelle, beide im Temp-Baum (§A-NJ).
        #     Der Test lief vorher gegen das Repo, wo immer ein Vorlauf
        #     liegt — er konnte nicht fehlschlagen. Ein Test, der den
        #     Zustand mit dem Gegenstand teilt, erbt ihn. Geprueft werden
        #     jetzt **mit** und **ohne** Vorlauf, ortsunabhaengig.
        reset()                                 # §A-JL Vorbedingung
        case = root / "ort_test"
        case.mkdir(exist_ok=True)
        snap_t = case / _COUNT_SNAPSHOT
        snap_t.unlink(missing_ok=True)          # definierter Zustand
        _SNAPSHOT_SEEN[0] = None
        _load_count_snapshot(case)              # ohne Vorlauf
        if _SNAPSHOT_SEEN[0] is not None:
            failures.append("Snapshot ohne Datei als gesehen gemeldet")
        snap_t.write_text(json.dumps({"checked": 1, "why": "x", "when": "x",
                                      "ref": "abc1234", "counting": "x",
                                      "counting_label": "v1"}), encoding="utf-8")
        _SNAPSHOT_SEEN[0] = None
        _load_count_snapshot(case)              # mit Vorlauf
        if _SNAPSHOT_SEEN[0] is None:
            failures.append("Snapshot mit Datei nicht gemeldet")
        _SNAPSHOT_SEEN[0] = None

        # 14. Die Einheit steht an der Zahl (§A-NI): `21` und `223` duerfen
        #     nicht beide nur "geprueft" heissen. Geprueft wird die
        #     Ausgabeform selbst — sie ist die Stelle, an der zwei
        #     Einheiten ein Wort teilten.
        line = _status_line(Checks(223, 210), 0)
        for need in ("223 Angaben geprueft", "433 Angaben gezaehlt",
                     "210 ausgeschlossen", "0 Abweichungen"):
            if need not in line:
                failures.append(f"Statuszeile ohne Einheit {need!r}: {line!r}")
        if line.count("geprueft") != 1:
            failures.append(f"Statuszeile nennt 'geprueft' mehrfach: {line!r}")

        # 15. Das Delta bei **gleicher** Zaehlweise muss erscheinen — mit
        #     Vorzeichen. Ohne diesen Fall besteht auch ein Pruefer, der
        #     nie ein Delta druckt: die Zeile existierte, feuerte nie.
        line = lines_for(prev(checked=207))
        for need in ("+16", "gegenueber 207", "abc1234"):
            if need not in line:
                failures.append(f"Delta bei gleicher Zaehlweise fehlt {need!r}: {line!r}")
        if "nicht als Delta" in line:
            failures.append(f"gleiche Zaehlweise als Reihe gedruckt: {line!r}")

        # 16. Das Repo, nicht das Arbeitsverzeichnis (§A-JM). Vier Runden
        #     lang war `cwd == root` ein Testproblem; in Runde 33 stand die
        #     Annahme im Code (relativer `--git-common-dir` gegen
        #     `Path.cwd()`) und wurde ohne Test gefixt. Fremdes `cwd`,
        #     relatives Verzeichnis in `root` — der Ort muss stimmen.
        other = root / "anderes_cwd"
        other.mkdir(exist_ok=True)
        repo2 = root / "repo2"
        (repo2 / "sub" / ".git").mkdir(parents=True, exist_ok=True)
        # Der reale Fall: **kein** explizites `root`. `_snapshot_path()`
        # leitet den Ort aus der Datei ab — der Ort der Datei, nicht der
        # Ort der Shell. Nur so trifft der Fehler `Path.cwd()`.
        here = Path(__file__).resolve().parent.parent
        prev_cwd = Path.cwd()
        # 16b. `chdir` ist Prozesszustand — der einzige, den `reset()`
        #      strukturell nicht sieht (§A-JU). Ein Fall, der vor seinem
        #      `finally` scheitert, laesst jeden folgenden in `other`
        #      laufen. Also: eine Ausnahme **innerhalb** eines Kaefigs,
        #      danach `reset_all()` — und `cwd` muss der Startwert sein.
        try:
            os.chdir(other)
            try:
                raise RuntimeError("Abbruch mitten im Test")
            finally:
                pass                       # bewusst KEIN chdir hier
        except RuntimeError:
            pass
        if Path.cwd() != other.resolve():   # Zustand absichtlich falsch
            failures.append("chdir hat den Prozess nicht erreicht — Test blind")
        reset_all()
        if Path.cwd() != suite_cwd:
            failures.append(
                f"reset_all() stellt cwd nicht her: {Path.cwd()} statt {suite_cwd}")

        # 16c. Der zweite Zyklus (§A-JY). Fall 16b deckte **einen** ab; ein
        #      Reset, der seine Referenz auf `Path.cwd()` setzt, ist nach
        #      dem ersten Durchlauf noch korrekt (cwd war sauber) und
        #      kippt erst beim zweiten gescheiterten `chdir`. Also zweimal
        #      hintereinander — und `_START_CWD` darf sich nicht bewegt haben.
        start_before = _START_CWD
        for zyklus in (1, 2):
            try:
                os.chdir(other)
                try:
                    raise RuntimeError(f"Zyklus {zyklus} gescheitert")
                finally:
                    pass
            except RuntimeError:
                pass
            reset_all()
            if Path.cwd() != suite_cwd:
                failures.append(
                    f"reset_all() verliert cwd im Zyklus {zyklus}: {Path.cwd()}")
            if _START_CWD != start_before:
                failures.append(
                    f"reset_all() hat die Referenz verschoben: {_START_CWD}")
        try:
            os.chdir(other)                    # cwd != Repo
            got = _snapshot_path()             # root=None
        finally:
            os.chdir(prev_cwd)
        if got.parent.resolve() != (here / "sub" / ".git").resolve() and \
                not str(got).startswith(str(here)):
            failures.append(
                f"Ohne root gegen cwd aufgeloest statt gegen die Datei: {got}")


        # 17. Jeder Modulglobal mit Zustand wird zurueckgesetzt (§A-JN/§A-JR).
        #     Ein Test, der zwei **Namen** kennt, sagt nichts ueber einen
        #     fuenften. Also: die Menge. Alles in `reset()` dokumentiert
        #     oder als zustandslos markiert (`_STATE_FREE`) — sonst rot.
        _SNAPSHOT_SEEN[0] = root           # kuenstlich gesetzt
        reset()
        if _SNAPSHOT_SEEN[0] is not None:
            failures.append("reset() laesst _SNAPSHOT_SEEN stehen")
        _test_results["x"] = 1
        reset()
        if _test_results:
            failures.append("reset() raeumt _test_results nicht")
        repo_root(root)                    # Cache fuellen
        reset()
        if _ROOT_CACHE:
            failures.append("reset() raeumt _ROOT_CACHE nicht")

        # Die Menge, nicht die Namen. Neue Globals muessen entschieden sein.
        # Drei Kategorien (§A-JX/§A-JY): resetbar, zustandslos, Referenz.
        # Eine Referenz ist deklariert und geprueft, aber vom Reset
        # ausgenommen — sonst setzt der Reset sie auf den Zustand, den er
        # gerade repariert.
        guarded = set(re.split(r"[\s,]+", _RESET_GLOBALS)) - {""}
        state_free = set(re.split(r"[\s,]+", _STATE_FREE)) - {""}
        reference = set(re.split(r"[\s,]+", _REFERENCE_GLOBALS)) - {""}
        declared = guarded | state_free | reference
        lost = [n for n in _module_state_globals() if n not in declared]
        if lost:
            failures.append(
                f"Modulglobal mit Zustand nicht deklariert: {lost}")
        both = guarded & state_free
        if both:
            failures.append(f"Global gleichzeitig Reset und zustandslos: {both}")
        # §A-JY: die drei Kategorien muessen disjunkt sein. Ein Name in
        # `_RESET_GLOBALS` **und** `_REFERENCE_GLOBALS` ist genau der Fehler,
        # bei dem der Reset seinen eigenen Anfang ueberschreibt.
        misplaced = reference & (guarded | state_free)
        if misplaced:
            failures.append(
                f"Referenz zugleich Reset/zustandslos: {misplaced}")
        # Die Referenz muss beim Import stehen, nicht beim ersten Reset:
        # danach ist `Path.cwd()` nicht mehr der Startwert.
        if not isinstance(_START_CWD, Path) or not _START_CWD.is_absolute():
            failures.append(f"_START_CWD ist kein absoluter Path: {_START_CWD!r}")

        # 19. Der Zweig, den jede echte Invocation nimmt (§A-JT):
        #     `root=None`. Bis Runde 34 war er ungetestet, weil Tests ihre
        #     Umgebung konstruieren — und damit genau den Zweig ueberspringen,
        #     in dem die Umgebung **fehlt**. Jede Funktion mit `root`-Parameter
        #     braucht einen Zwilling ohne: sonst prueft die Suite nur den
        #     bequemen Weg.
        _reset_root_cache()
        with_root = {
            "_snapshot_path": _snapshot_path(root),
            "_delta_line": _delta_line(1, root),
            "_save_count_snapshot": None,
        }
        no_root = {
            "_snapshot_path": _snapshot_path(),
            "_delta_line": _delta_line(1),
        }
        # ohne root zeigt der Ort auf **dieses** Repo, nicht auf `root`
        here = Path(__file__).resolve().parent.parent
        if not str(no_root["_snapshot_path"]).startswith(str(here)):
            failures.append(
                f"ohne root zeigt der Ort nicht auf das eigene Repo: {no_root['_snapshot_path']}")
        # 20. Wer prueft den Filter? (§A-JV) Der Filter war einmal falsch,
        #     und falsch hiess gruen. Ein Fixture mit je einer Zustandsform
        #     und der **vollstaendigen** Erwartung — ein Wert, kein Muster.
        got_forms = _module_state_globals_in(_filter_fixture())
        expected = ["A", "B", "C", "H", "I"]
        if got_forms != expected:
            failures.append(
                f"Filter erkennt Zustandsformen falsch: {got_forms} != {expected}")
        for free_form in ("D", "E", "F", "G"):
            if free_form in got_forms:
                failures.append(
                    f"unveraenderliche Form als Zustand gemeldet: {free_form}")
        # Zwei Wege fuehren zu "Zustand": `mutable` (Liste/Dict) und
        # `not literal` (Ausdruck/Call). Ein Fixture, das nur den zweiten
        # beweist, laesst den ersten ungeprueft — genau der Originalfehler.
        # Also: ein Fall, in dem **nur** `mutable` die Antwort traegt.
        only_mutable = _module_state_globals_in("A = [0]\nB = {}\n")
        if only_mutable != ["A", "B"]:
            failures.append(
                f"mutable wirkt nicht isoliert: {only_mutable} != ['A', 'B']")
        only_literal = _module_state_globals_in("A = (0,)\nB = 'x'\n")
        if only_literal:
            failures.append(
                f"unveraenderliche Literale als Zustand: {only_literal}")

        # 21. Zwei verschiedene Werte pro Test (§A-JW). Ein Test, dessen
        #     zweiter Fall denselben Wert liefert, sieht keinen Unterschied
        #     — die vierte Annahme. Gegenprobe an der Stelle, an der sie
        #     sich schon einmal geraeumt hat: `root` gegen `root=None`.
        if _snapshot_path(root) == _snapshot_path():
            failures.append("Gegenprobe fehlt: root und root=None gleich")
        if Checks(21).n == Checks(22).n:
            failures.append("Checks traegt die Zahl nicht")

        # 22. Die Identitaet `total = checked + excluded` (§A-JX). Vorher
        #     stand `223 = 433 - 210` zweimal getippt in der Zeile; jetzt
        #     haelt der Typ sie. Gegenprobe mit **verschiedenen** Werten:
        #     Rechentypen, die eine Zahl hart eintippen, bestehen ein
        #     einzelnes Beispiel (Regel §A-JW).
        c1 = Checks(21, 210)
        if c1.total != 231:
            failures.append(f"total falsch: {c1.total} != 231")
        c3 = Checks(7, 4)
        if c3.total != 11:
            failures.append(f"total falsch (zweites Paar): {c3.total} != 11")
        c2 = Checks(11, 220)
        if c1.total != c2.total or c1 == c2:
            failures.append("Aufteilung nicht im Objekt: gleiche Summe, gleicher Wert")
        if Checks(5, 1) == Checks(5, 2):
            failures.append("__eq__ ignoriert excluded")
        line_ident = _status_line(c1, 0)
        if "21 Angaben geprueft" not in line_ident or \
                "231 Angaben gezaehlt" not in line_ident or \
                "210 ausgeschlossen" not in line_ident:
            failures.append(f"Zeile rechnet nicht aus dem Typ: {line_ident!r}")
        line_ident3 = _status_line(c3, 0)
        if "11 Angaben gezaehlt" not in line_ident3:
            failures.append(f"Zeile rechnet nicht (zweites Paar): {line_ident3!r}")
        try:
            Checks(-1, 0)
            failures.append("negativer Wert akzeptiert")
        except ValueError:
            pass
        # §A-KA: `Checks` ist ein Wert. Aendert sich ein Feld nach dem Bau,
        # ist `total` eine Eigenschaft des Zugriffszeitpunkts, nicht des
        # Objekts — die Zeile koennte zwischen Druck und Pruefung kippen.
        c_mut = Checks(3, 4)
        for feld in ("n", "excluded"):
            try:
                setattr(c_mut, feld, 99)
                failures.append(f"Checks ist mutierbar ({feld}) — kein Wert")
            except AttributeError:
                pass
        if c_mut.total != 7:
            failures.append(f"total hat sich nach dem Bau geaendert: {c_mut.total}")
        # und die Funktion selbst: `repo_root()` ist der eine Weg
        if repo_root(None) != here:
            failures.append(f"repo_root(None) != Dateiort: {repo_root(None)}")
        if repo_root(root) != root.resolve():
            failures.append("repo_root(root) loest nicht auf root auf")
        # Cache: zweiter Aufruf darf keinen neuen Subprozess kosten
        calls = []
        orig_run = subprocess.run

        def counting_run(args, **kw):
            if "--git-common-dir" in args:
                calls.append(args)
            return orig_run(args, **kw)

        _reset_root_cache()
        subprocess.run = counting_run
        try:
            _snapshot_path(root)
            _snapshot_path(root)
            _snapshot_path(root)
        finally:
            subprocess.run = orig_run
        if len(calls) != 1:
            failures.append(
                f"repo_root-Cache greift nicht: {len(calls)} git-Aufrufe")
        _reset_root_cache()

        # 18. Der Docstring nennt die Einheit — und die **Zahl** muss die
        #     sein, die er nennt (§A-JO/§A-JS). Existenz eines Wortes ist
        #     die halbe Pruefung: 21 und 223 koennen beide "geprueft"
        #     heissen. Also beides: Text, und die Zahl an derselben Stelle.
        rdoc = inspect.getdoc(Report) or ""
        # Nicht "irgendwo im Docstring steht Pruefung" — sondern: die
        # Zeile, die `checked` nennt, nennt auch die Einheit. Sonst
        # besteht der Test, weil "Zaehlt Pruefungen" in Zeile 1 steht
        # und `checked` in Zeile 3 etwas anderes behauptet.
        checked_lines = [ln for ln in rdoc.splitlines() if "checked" in ln]
        if not checked_lines or not any("Pruefung" in ln
                                        for ln in checked_lines):
            failures.append(
                f"Report nennt die Einheit nicht an `checked`: {checked_lines[:2]!r}")
        # Der Wert: `Report.checked` ist die Zahl der Pruefungen. Wenn
        # `_status_line` sie als "Angaben" ausgibt und `checked` zugleich
        # "Pruefungen" heisst, muessen die Zahlen im Report und in der
        # Zeile uebereinstimmen — sonst sind es zwei Messungen.
        demo = Checks(21)
        if "21 Angaben" not in str(demo):
            failures.append(f"Checks bringt die Zahl nicht mit: {demo!r}")
        try:
            _status_line(21, 0)              # type: ignore[arg-type]
            failures.append("_status_line akzeptiert int — die Einheit fehlt")
        except TypeError:
            pass
    return failures


def _resolve_test_root(doc_root: Path) -> Path:
    import os
    env = os.environ.get("AGENT_X_TEST_ROOT")
    if env:
        return Path(env).resolve()
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return doc_root


def check_tests(text: str, root: Path, rep: Report) -> None:
    """Testskripte laufen lassen, Ausgabe gegen die Zahlen im Text halten.

    Jedes Skript hat einen eigenen Doku-Kontext-Regex, der genau die Zeile(n)
    identifiziert, in denen sein Ergebnis dokumentiert ist. Nur x/y-Paare aus
    diesen Zeilen werden mit der tatsaechlichen Testausgabe verglichen.
    """
    test_root = _resolve_test_root(root)
    for script, out_pattern, doc_pattern in TEST_SCRIPTS:
        # Guard: both patterns must have exactly 2 groups (passed, total)
        bad = False
        for name, pat in [("Ausgabe-Regex", out_pattern), ("Doku-Regex", doc_pattern)]:
            if re.compile(pat).groups != 2:
                rep.fail(None, f"Test {script}", pat,
                         f"{name} braucht 2 Gruppen (bestanden/gesamt), hat "
                         f"{re.compile(pat).groups}")
                bad = True
        if bad:
            continue
        # Immer Repo-Skript (nicht TMP): Path(__file__) muss Fixtures/Imports finden.
        # CLAUDE.md kommt weiterhin aus root (staged Index).
        f = test_root / script
        if not f.exists():
            continue
        try:
            out = subprocess.run([sys.executable, str(f)], cwd=str(test_root),
                                 capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            rep.fail(None, f"Test {script}", "—", "Timeout")
            continue
        blob = out.stdout + out.stderr

        # Umgebungsdefizit (fehlendes Modul) von echtem Testfehler unterscheiden
        # Pattern 1: raw ModuleNotFoundError traceback (e.g. pycryptodome)
        missing = re.search(r"ModuleNotFoundError: No module named '(\S+)'", blob)
        # Pattern 2: caught import error in test output (e.g. streamlit/plotly)
        if not missing:
            missing = re.search(r"No module named '(\S+)'", blob)
        if missing:
            rep.env(script, f"Übersprungen — {missing.group(1)} nicht installiert")
            continue

        m = re.search(out_pattern, blob)
        if not m:
            rep.fail(None, f"Test {script}", "—",
                     "Ergebnismuster nicht in der Ausgabe gefunden")
            continue
        real = f"{m.group(1)}/{m.group(2)}"
        _test_results[script] = {
            "passed": int(m.group(1)),
            "total":  int(m.group(2)),
            "failed": int(m.group(2)) - int(m.group(1)),
            "exit_code": out.returncode,
        }

        # Suche im Dokument die Zeile, die per doc_pattern zu diesem Skript gehoert
        found = False
        for lineno, raw in enumerate(text.splitlines(), 1):
            dm = re.search(doc_pattern, raw)
            if not dm:
                continue
            found = True
            doc_val = f"{dm.group(1)}/{dm.group(2)}"
            if doc_val != real:
                rep.fail(lineno, f"Testergebnis {Path(script).stem}",
                         doc_val, real)
            else:
                rep.ok()
        if not found:
            rep.fail(None, f"Testergebnis {Path(script).stem}",
                     "nicht dokumentiert", real)


def _resolve_inventory_ref(root: Path, ref: str) -> bool:
    """Repo-relative Pfad oder Kurzname → existierende Datei."""
    if ref.startswith("tests/") or ref.startswith("/"):
        return True
    candidates = [
        root / ref,
        root / "agents_b2g" / ref,
        root / "scripts" / ref,
        root / "services" / ref,
        root / "prototypes" / ref,
        root / "prototypes" / "raas_paper_trading" / ref,
        root / "docs" / ref,
        root / "chaos" / ref,
        root / "api" / ref,
        root / "charts" / ref,
        root / "config" / ref,
        root / "deploy" / ref,
    ]
    if any(p.exists() for p in candidates):
        return True
    name = Path(ref).name
    for base in (
        "prototypes/raas_paper_trading",
        "services",
        "scripts",
        "agents_b2g",
        "agents",
        "config",
    ):
        base_path = root / base
        if not base_path.is_dir():
            continue
        for hit in base_path.rglob(name):
            if hit.is_file():
                return True
    return False


def _skip_inventory_backtick_ref(ref: str) -> bool:
    """Runtime-/Output-Pfade nicht gegen Repo prüfen."""
    if ref.startswith("/") or ref.startswith("exports/"):
        return True
    if "/" not in ref and ref.endswith((".json", ".jsonl")):
        return True
    if ref.startswith(("logs/", "data/")):
        return True
    return False


def _load_swarm_health(root: Path):
    import importlib.util
    import sys

    path = root / "scripts" / "swarm_health.py"
    spec = importlib.util.spec_from_file_location("swarm_health", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"kann {path} nicht laden")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


INVENTORY_RUNTIME_MAX_AGE_H = float(
    __import__("os").environ.get("SWARM_INVENTORY_MAX_AGE_H", "24")
)


def _parse_runtime_generated_at(text: str) -> Optional["datetime"]:
    from datetime import datetime, timezone

    m = re.search(r"<!-- generated_at:\s*([^>]+?) -->", text)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def check_inventory_runtime_block_age(inventory_text: str, rel: str, rep: Report) -> None:
    """Offline-sicher: Laufzeit-Block älter als SWARM_INVENTORY_MAX_AGE_H → Fehler."""
    from datetime import datetime, timezone

    generated = _parse_runtime_generated_at(inventory_text)
    if generated is None:
        rep.fail(None, f"{rel} Laufzeit-Block", "generated_at fehlt", "make raas-swarm-inventory-sync")
        return
    age_h = (datetime.now(timezone.utc) - generated).total_seconds() / 3600.0
    rep.ok()
    if age_h > INVENTORY_RUNTIME_MAX_AGE_H:
        rep.fail(
            None,
            f"{rel} Laufzeit-Block veraltet",
            f"{age_h:.1f}h alt",
            f">{INVENTORY_RUNTIME_MAX_AGE_H:.0f}h",
            "make raas-swarm-inventory-sync",
        )
    else:
        rep.ok()


def check_inventory_runtime_status(root: Path, inventory_text: str, rel: str, rep: Report) -> None:
    """Pre-commit: Block-Alter + Schema (Komponenten/Schicht/Rolle/Signal). Kein Live-Status."""
    check_inventory_runtime_block_age(inventory_text, rel, rep)

    if "Sync ausstehend" in inventory_text:
        return

    try:
        sh = _load_swarm_health(root)
    except Exception as exc:
        rep.fail(None, f"{rel} Laufzeit-Check", "swarm_health.py", str(exc))
        return

    if not sh._runtime_block_body(inventory_text):
        rep.fail(None, f"{rel} Laufzeit-Block", "SWARM_RUNTIME fehlt", "make raas-swarm-inventory-sync")
        return

    for err in sh.check_runtime_schema(inventory_text):
        rep.fail(
            None,
            f"{rel} Laufzeit-Schema ({err['component']} {err['field']})",
            err["expected"],
            err["actual"],
            "make raas-swarm-inventory-sync",
        )


def check_doc_inventories(root: Path, rep: Report) -> None:
    """Pflicht-Abschnitte, Erwähnungen und referenzierte Pfade in Inventar-Docs."""
    makefile = (root / "Makefile").read_text(encoding="utf-8") if (root / "Makefile").is_file() else ""
    for spec in DOC_INVENTORY_FILES:
        rel = spec["path"]
        doc_path = root / rel
        if not doc_path.is_file():
            rep.fail(None, f"Inventar-Dokument fehlt", rel, "existiert nicht")
            continue
        text = doc_path.read_text(encoding="utf-8")
        rep.ok()

        for section in spec.get("required_sections", []):
            if section not in text:
                rep.fail(None, f"{rel} Abschnitt fehlt", section, "nicht gefunden")
            else:
                rep.ok()

        for mention in spec.get("required_mentions", []):
            if mention not in text:
                rep.fail(None, f"{rel} Erwähnung fehlt", mention, "nicht gefunden")
            else:
                rep.ok()

        for artefact in spec.get("required_paths_exist", []):
            if not (root / artefact).exists():
                rep.fail(None, f"{rel} Artefakt fehlt", artefact, "existiert nicht")
            else:
                rep.ok()

        target = spec.get("makefile_target")
        if target and f"{target}:" not in makefile:
            rep.fail(None, f"{rel} Makefile-Target fehlt", target, "nicht in Makefile")
        elif target:
            rep.ok()

        sync_target = spec.get("sync_makefile_target")
        if sync_target and f"{sync_target}:" not in makefile:
            rep.fail(None, f"{rel} Makefile-Target fehlt", sync_target, "nicht in Makefile")
        elif sync_target:
            rep.ok()

        check_inventory_runtime_status(root, text, rel, rep)

        # Backtick-Referenzen wie in CLAUDE.md (nur repo-relative Pfade)
        seen: set[str] = set()
        for lineno, raw in enumerate(text.splitlines(), 1):
            for ref in re.findall(r"`([\w/.\-]+\.(?:py|yaml|yml|json|md|sh))`", raw):
                if ref in seen or _skip_inventory_backtick_ref(ref):
                    continue
                seen.add(ref)
                hits = [root / ref, root / "agents_b2g" / ref, root / "scripts" / ref]
                if not any(h.exists() for h in hits):
                    if not _resolve_inventory_ref(root, ref):
                        rep.fail(lineno, f"{rel} tote Referenz", ref, "existiert nicht")
                    else:
                        rep.ok()
                else:
                    rep.ok()


def check_undocumented_tests(root: Path, rep: Report) -> None:
    """Find all scripts/test_*.py files and check they're registered."""
    on_disk = sorted(
        p.relative_to(root).as_posix()
        for p in root.glob("scripts/test_*.py")
    )
    registered = {t[0] for t in TEST_SCRIPTS} | NO_TEST_SUMMARY
    for script in on_disk:
        if script not in registered:
            rep.fail(None, "Testskript nicht registriert",
                     script, "fehlt in TEST_SCRIPTS oder NO_TEST_SUMMARY")


_COUNT_SNAPSHOT = ".check_claude_md.last.json"

# §A-JR: die MENGEN-Fassung des Harness-Tests prueft die **Menge** der
# Modulglobals, nicht zwei Namen.
# Zwei Deklarationen, disjunkt und vollstaendig — sonst rot:
#   _RESET_GLOBALS: traegt Zustand, wird von `reset()` geraeumt
#   _STATE_FREE:    unveraenderlich (Skalar, Tuple, frozenset, kompiliert)
# Wer ein fuenftes Global mit Zustand hinzufuegt, muss es hier entscheiden.
_RESET_GLOBALS = "_SNAPSHOT_SEEN _test_results _ROOT_CACHE _SNAPSHOT_CACHE"
# §A-JY: die dritte Kategorie. Ein Global, das **nie** zurueckgesetzt werden
# darf, weil es der Reset selbst braucht, um zu wissen, wohin er zurueckgeht.
# Eine Referenz ist deklariert und geprueft — aber vom Reset ausgenommen.
# Ohne diese Kategorie muesste `_START_CWD` in `_RESET_GLOBALS` stehen, und
# `reset_all()` wuerde ihn auf `Path.cwd()` setzen — also auf den Zustand,
# den er gerade reparieren soll. Beim ersten Durchlauf faellt das nicht auf
# (cwd ist sauber), erst beim zweiten gescheiterten `chdir`-Fall landet die
# Referenz in `/tmp`.
_REFERENCE_GLOBALS = "_START_CWD"
# §A-JZ: Konstruktoren ueber unveraenderlichen Typen. Ein Name hier heisst:
# das Ergebnis ist ein Wert, kein Speicherplatz.
_IMMUTABLE_CTORS = frozenset({
    "Path", "PurePath", "PosixPath", "PurePosixPath",
    "Decimal", "Fraction", "bytes", "complex",
    "frozenset", "tuple", "re",
})
_STATE_FREE = ("AGENTS_PER_WAVE SCRIPT_SCOPE MIN_AGENT_CLAIM _COUNTING_LABEL "
               "COMPLIANCE_AGENTS _COUNT_CONTEXT_CHARS _TOTAL_MARK "
               "_SELF_TEST_SCOPE INVENTORY_RUNTIME_MAX_AGE_H _COUNT_SNAPSHOT "
               "_RESET_GLOBALS _STATE_FREE")


def _filter_fixture() -> str:
    """Ein Modul, je eine Zustandsform (§A-JV) — ziffernfrei.

    Der Filter in `_module_state_globals` war einmal falsch, und falsch
    hiess gruen: `globals: []`, weil eine Liste fuer ein Literal gehalten
    wurde. Wer prueft den Filter? Ein Fixture, dessen **vollstaendige**
    erwartete Liste daneben steht — nicht ein Muster, sondern ein Wert.

    Keine Ziffern im Fixture: der Zahlen-Guard sucht Zahlen in Prosa und
    wuerde auf dem Test zuschlagen, der den Guard prueft.
    """
    return '''
import re
A = [None]                 # Liste: Speicherplatz, kein Literal
B = {}                     # Dict: dito
C = set()                  # Set: veraenderlich
D = (None,)                # Tuple: unveraenderlich
E = "text"                 # str: unveraenderlich
F = re.compile("x")        # compiled: unveraenderlich
G = frozenset()            # frozenset: unveraenderlich
H: list = []               # Annotation aendert die Form nicht
I = A + [None]             # Ausdruck: Zustand (unbekannt)
'''


def _module_state_globals() -> list[str]:
    """Die echten Modulglobals, ueber die pruefbare Formen-Erkennung."""
    src = Path(__file__).read_text(encoding="utf-8")
    free = set(_STATE_FREE.split())
    return [n for n in _module_state_globals_in(src) if n not in free]


def _module_state_globals_in(src: str) -> list[str]:
    """Die Formen-Erkennung, isoliert — damit sie pruefbar ist."""
    import ast
    tree = ast.parse(src)
    out: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target])
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        for n in names:
            if not n.startswith("_") and not (len(n) == 1 and n.isupper()):
                continue
            val = node.value
            # Zustand ist: mutable Behaelter (Liste, Dict, Set) und alles,
            # was kein Literal ist. `[None]` und `{}` sind **keine**
            # Literale in diesem Sinn — sie sind Speicherplaetze. Der
            # Fehler in Runde 35 war, beide in der Literal-Liste zu haben;
            # ein `mutable`-Merker daneben half nur, weil sie dort noch
            # standen. Er ist entfernt: er war ab dem Moment tot, in dem
            # `ast.List` nicht mehr als Literal galt.
            literal = isinstance(val, (ast.Tuple, ast.Constant))
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Name) \
                    and val.func.id in ("frozenset", "set", "dict", "list"):
                literal = val.func.id == "frozenset"
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute) \
                    and val.func.attr == "compile":
                literal = True
            # §A-JZ: Konstruktoraufrufe ueber unveraenderlichen Typen sind
            # Werte, keine Speicherplaetze. `Path("/x")`, `Decimal(1)`,
            # `Fraction(1,2)`, `bytes(1)` sind unveraenderlich — sie als
            # "Ausdruck -> Zustand" zu lesen war ein falsch-positiv, das
            # jede Referenz zu einem Reset-Kandidaten gemacht haette.
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Name) \
                    and val.func.id in _IMMUTABLE_CTORS:
                literal = True
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute) \
                    and val.func.attr in ("resolve", "absolute"):
                literal = True          # Path(...).resolve(): Wert
            if not literal:
                out.append(n)
    return out
def _count_reason(argv: list[str]) -> str:
    """`--write-count "<grund>"` — der Grund steht im Snapshot, nicht im Kopf."""
    i = argv.index("--write-count")
    rest = [a for a in argv[i + 1:] if not a.startswith("-")]
    return rest[0] if rest else "Grund nicht notiert"


_ROOT_CACHE: dict = {}
_SNAPSHOT_CACHE: dict = {}
# §A-JY: die Referenz. Beim Import einmal genommen, danach nie wieder —
# `reset_all()` liest sie, schreibt sie nicht. Deshalb `_REFERENCE_GLOBALS`,
# nicht `_RESET_GLOBALS`: der Reset darf seinen eigenen Anfang nicht
# ueberschreiben, sonst traegt er den Fehler, den er repariert, weiter.
_START_CWD = Path.cwd().resolve()


def repo_root(root: Path | None = None) -> Path:
    """Der **eine** Weg zum Repo (§A-JQ).

    Drei Wege fuehrten hierher und zwei waren falsch: `root`, `base` und
    `Path.cwd()`. Nach Runde 34 stimmten alle — in dem Moment, in dem ein
    vierter dazukommt, hat niemand einen Ort, an dem er nachsieht. Also
    ein Ort: diese Funktion. `rg "Path\\.cwd\\(\\)"` muss danach **einen**
    Treffer haben (den Default im `__main__`), nicht vier mit Haekchen.

    Ohne `root` ist die Antwort der Ort **dieser Datei**, nicht die Shell:
    der Pruefer beschreibt den Baum, in dem er liegt. Der Shell-Default
    gilt nur dort, wo jemand bewusst ein Ziel angibt.

    Nebenwirkung, benannt: `git rev-parse` ist ein Subprozess. Wer die
    Funktion in einer Schleife nutzt, bezahlt pro Zeile. Deshalb Cache —
    der Schluessel ist das aufgeloeste `root` (oder `None`).
    """
    key = None if root is None else Path(root).resolve()
    if key in _ROOT_CACHE:
        return _ROOT_CACHE[key]
    base = key or Path(__file__).resolve().parent.parent
    _ROOT_CACHE[key] = base
    return base


def _reset_root_cache() -> None:
    """Cache leeren — Testzustand, nicht Produktionszustand (§A-JQ)."""
    _ROOT_CACHE.clear()
    _SNAPSHOT_CACHE.clear()


def _snapshot_path(root: Path | None = None) -> Path:
    """Ort des Vorlaufs: **ein** Ort, nicht „neben dem Pruefer" (§A-NC).

    Drei Kandidaten, drei Verhalten — gemessen, nicht angenommen:

      neben dem Pruefer (`root/.check_claude_md.last.json`)
          → im Hook-Export unsichtbar, weil gitignored: CI/frischer Klon
            meldet `kein Vorlauf` bei *jedem* Lauf. Ehrlich, aber nutzlos.
      committet
          → jeder `--write-count` diff'ed den Baum; der Pruefer macht
            Arbeit, die niemand sieht, und der Commit ist nie sauber.
      Working-Tree-Root via `git rev-parse --git-common-dir`
          → derselbe Ort fuer Arbeitsbaum **und** Hook-Export, ueberlebt
            `checkout-index`, stoert keinen Diff.

    Entscheidung: die dritte. Der Vorlauf beschreibt **diesen Baum**, also
    wohnt er beim Baum (`.git/`), nicht bei der Datei, die exportiert wird.
    Ohne Repo gibt es **keinen** Ort — dann sagt der Pruefer `kein .git/`,
    nicht `kein Vorlauf`. „Noch leer" und „nicht messbar" sind zwei
    Zustaende, und nur einer davon verschwindet beim naechsten Lauf.
    """
    key = None if root is None else Path(root).resolve()
    if key in _SNAPSHOT_CACHE:
        return _SNAPSHOT_CACHE[key]
    try:
        base = repo_root(root)
        r = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(base),
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            gd = Path(r.stdout.strip())
            if not gd.is_absolute():
                # relativ zum Repo, nicht zur Shell: `git` lief in `base`
                gd = base / gd
            _SNAPSHOT_CACHE[key] = gd / "check_claude_md.last.json"
            return _SNAPSHOT_CACHE[key]
    except (OSError, subprocess.SubprocessError):
        pass
    _SNAPSHOT_CACHE[key] = repo_root(root) / _COUNT_SNAPSHOT
    return _SNAPSHOT_CACHE[key]


def _load_count_snapshot(root: Path | None = None) -> dict | None:
    """Der letzte Lauf: Zahl, Zaehlweise, Grund, Datum (§A-NC).

    Ohne ihn ist jede Differenz eine Behauptung. Die Zaehlweise steht
    mit drin, weil `223` gegen `234` nur dann eine Bewegung ist, wenn
    beide dieselbe Formel benutzen — zwei Aenderungen gleichzeitig
    (andere Felder, andere Zaehlweise) beweisen nichts ueber die eigene
    Entwicklung.
    """
    p = _snapshot_path(root)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        _SNAPSHOT_SEEN[0] = p
        return data
    except (OSError, ValueError):
        _SNAPSHOT_SEEN[0] = None
        return None


def _delta_line(checked: int, root: Path | None = None) -> str | None:
    """Die Zeile über der Zahl, oder die Wahrheit über das Fehlen (§A-NC).

    Drei Zustaende, drei Ausgaben — nicht zwei Zustaende und zwei Nullen:

      kein Vorlauf      → `(kein Vorlauf — Erstwert, nicht vergleichbar)`
      gleiche Zahl      → keine Zeile (echte Nullaenderung)
      Zahl geaendert    → `<delta> gegenueber <alt>, <sha>, <datum>, …`
      Zaehlweise anders → `counting v1->v2: <alt> -> <neu>, nicht als Delta`

    Der erste Zustand hat so lange wie der zweite ausgesehen:
    „nichts zu vergleichen" ist nicht „nichts geaendert". Auf einem
    frischen Klon, in CI oder nach Verlust der Datei schweigt der
    Pruefer sonst genau so wie bei einer echten Nullaenderung.
    """
    prev = _load_count_snapshot(root)
    if prev is None:
        # §A-JK: `kein Vorlauf` (Ort da, Inhalt fehlt) und `kein Ort`
        # (kein .git/, nie messbar) sind zwei Zustaende. Vorher sahen
        # beide gleich aus — und im Tarball-Export stand die Zeile
        # `Vorlauf: .git/...`, die dort nicht gilt.
        if not _snapshot_writable(root):
            return ("  (kein .git/ — Vorlauf nicht schreibbar, "
                    "keine Differenzmessung)")
        return "  (kein Vorlauf — Erstwert, nicht vergleichbar)"
    if prev.get("checked") == checked:
        return None
    try:
        old = int(prev["checked"])
    except (KeyError, TypeError, ValueError):
        return "  (Vorgaenger unlesbar: checked fehlt oder ist keine Zahl)"
    delta = checked - old
    sign = "+" if delta > 0 else ""
    # §A-NC: Datum identifiziert einen Tag, SHA identifiziert einen Baum.
    # Verglichen werden Baeume. Ein Vorlauf ohne SHA ist ein Zitat ohne
    # Fundstelle — genau die Ursache des Fehlers, den §A-NC behebt.
    where = prev.get("ref") or "commit unbekannt"
    when = prev.get("when", "undatiert")
    why = prev.get("detail") or prev.get("why", "Grund nicht notiert")
    label = prev.get("counting_label", "v?")
    changed = bool(prev.get("counting")) and prev["counting"] != _counting_signature()
    if changed:
        # §A-NF: `+16` liest sich als Wachstum. Bewegt sich die Zaehlweise
        # mit, ist es Zaehlweise **plus** Baum gleichzeitig — beides
        # zusammen ist keine Differenz, sondern eine Reihe. Ohne
        # Vorzeichen, ohne Delta-Anspruch: die Zahlen stehen nebeneinander,
        # der Leser sieht beide Zaehlweisen im Namen.
        return (f"  (counting {label}->{_COUNTING_LABEL}: {old} -> {checked}, "
                f"nicht als Delta lesbar; {where}, {when})")
    return (f"  ({sign}{delta} gegenueber {old}, {where}, {when}, "
            f"counting {label}, {why})")


def _selection_line(skips: dict[str, int] | None = None) -> str:
    """Die zweite Grenze: was der Pruefer nicht ansieht — **und wieviel** (§A-ND).

    Drei Regeln, drei Mengen. Eine Regel mit `0` Gegenstaenden ist kein
    Fehler, aber sie zaehlt nicht stillschweigend als einer von drei:
    `waves 0` heisst, dass dieser Ausschluss heute nichts deckt und
    deshalb morgen nicht mehr traegt, ohne dass jemand es merkt.
    """
    s = skips or {}
    return (
        "Auswahl: 3 Regeln — "
        f"waves {s.get('waves', 0)}, "
        f"agents<{MIN_AGENT_CLAIM}: {s.get('agents<50', 0)}, "
        f"Tests ohne Skriptpfad: {s.get('tests_ohne_skript', 0)}"
    )


def _doc_tracked() -> str:
    """Ist die Rundentabelle im Repo, und hat sie einen Commit?

    Gemessen mit `git ls-files --error-unmatch` + `git log -1`: eine
    Abnahme im Arbeitsbaum ist keine Doku, sie ist ein Entwurf. Der
    Unterschied ist ein Befehl, kein Satz.
    """
    rel = "order_execution_engine/ops/TAG7_ABNAHME.md"
    base = Path(__file__).resolve().parent.parent
    try:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                           cwd=str(base), capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return "NICHT im Repo"
        c = subprocess.run(["git", "log", "-1", "--format=%h", "--", rel],
                           cwd=str(base), capture_output=True, text=True, timeout=5)
        return f"committet {c.stdout.strip() or '?'}"
    except (OSError, subprocess.SubprocessError):
        return "Pruefung nicht moeglich"


def _snapshot_writable(root: Path | None = None) -> bool:
    """Kann der Ort den Vorlauf ueberhaupt halten? (§A-JK)

    Ohne `.git/` gibt es keinen Ort — ein Tarball-Export, ein Docker-
    COPY, ein CI-Checkout ohne Repo. Dort ist die Differenzmessung nicht
    „noch leer", sie ist **nicht moeglich**. Der Unterschied ist der
    Unterschied zwischen `kein Vorlauf` und `kein Ort`.
    """
    p = _snapshot_path(root)
    # Ein Ort ist nur dann ein Ort, wenn er den **Baum** beschreibt. Der
    # Fallback (kein Repo) schreibt neben den Pruefer — dorthin, wo
    # Docker-COPY und Tarball-Export nichts lesen. Also: .git/ muss da sein.
    return p.parent.name == ".git" and p.parent.is_dir()


class Checks:
    """Pruefungen — **die Einheit traegt den Namen** (§A-JS/§A-JX).

    Runde 23 in kleinster Form: zwei Zahlen, ein Wort. `Report.checked`
    ist die Zahl der **Pruefungen**; `_status_line` sagte dazu "Angaben".
    Solange Zahl und Wort getrennt entstehen, ist der Docstring eine
    Behauptung neben der Messung.

    Runde 36 eine Ebene weiter: die Zeile hat **drei** Zahlen —
    `checked`, `excluded`, `total`. Wurde `total = checked + excluded`
    dreimal getippt, war die Identitaet eine Behauptung. Jetzt traegt
    der Typ sie und wirft, wenn sie nicht gilt: die Zeile kann nicht
    mehr luegen, weil sie nicht mehr rechnen muss.
    """

    __slots__ = ("n", "excluded")

    def __init__(self, n: int, excluded: int = 0) -> None:
        # §A-KA: `frozen` — `total` ist eine Eigenschaft des Objekts, nicht
        # des Zugriffszeitpunkts. Ohne das koennte `n` zwischen Druck und
        # Pruefung kippen. Nebenwirkung: kein In-Place-Zaehler; wer
        # `checked += 1` braucht, baut `Checks(n+1, excluded)`. Zaehlort
        # ist `Report.ok()`/`Report.fail()`, die `Report.checked` als int
        # fuehren und beim Druck in `Checks` uebergeben (eine Stelle).
        object.__setattr__(self, "n", int(n))
        object.__setattr__(self, "excluded", int(excluded))
        if self.n < 0 or self.excluded < 0:
            raise ValueError("Pruefungen und Ausschluesse sind nicht negativ")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Checks ist ein Wert (frozen)")

    @property
    def total(self) -> int:
        """`checked + excluded` — hier, einmal, nicht in der Zeile."""
        return self.n + self.excluded

    def __str__(self) -> str:
        return f"{self.n} Angaben geprueft"

    def __repr__(self) -> str:
        return f"Checks({self.n}, {self.excluded})"

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Checks) and self.n == other.n
                and self.excluded == other.excluded)

    def __hash__(self) -> int:
        return hash(("Checks", self.n, self.excluded))


def _status_line(checked: Checks, problems: int) -> str:
    """Die Kopfzeile: **jede Zahl mit ihrer Einheit** (§A-NI).

    `checked` kommt als `Checks` herein und bringt Wort, Zahl und die
    Identitaet `total = checked + excluded` mit. Die Zeile rechnet nicht
    mehr — sie liest drei Felder eines Objekts, das sie zusammen haelt.
    """
    if not isinstance(checked, Checks):
        raise TypeError("checks muss Checks sein, int ist die alte Falle")
    return (f"{checked.n} Angaben geprueft / {checked.total} Angaben gezaehlt "
            f"({checked.excluded} ausgeschlossen), {problems} Abweichungen")


def _counting_signature() -> str:
    """Was gezaehlt wird, in einer Zeile. Aendert sie sich, ist die Zahl
    nicht mehr mit der alten vergleichbar — und der Pruefer sagt das."""
    return ("line_counts+dead_refs+counts+undocumented+inventories; "
            f"waves={SCRIPT_SCOPE}, min_agents={MIN_AGENT_CLAIM}")


def _save_count_snapshot(checked: int, why: str,
                         detail: dict[str, int] | None = None) -> None:
    """Schreibt Stand + Baum + Zaehlweise fort (§A-NC).

    `ref` ist der **Ball**, nicht das Datum: `git rev-parse --short HEAD`
    plus ein `dirty`-Merker. Eine Differenz gegen einen schmutzigen Baum
    ist keine Differenz zwischen Staenden, und das muss draufstehen.
    """
    p = _snapshot_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked": checked,
        "why": why,
        "when": datetime.date.today().isoformat(),
        "ref": _tree_ref(),
        "counting": _counting_signature(),
        "counting_label": _COUNTING_LABEL,
    }
    if detail:
        payload["detail"] = _format_detail(detail)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")


def _tree_ref(root: Path | None = None) -> str:
    """`<sha>` oder `<sha>+dirty` — der Baum, gegen den verglichen wird."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(root or Path(__file__).resolve().parent.parent),
                           capture_output=True, text=True, timeout=5)
        sha = r.stdout.strip() or "ohne-repo"
        d = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                           cwd=str(root or Path(__file__).resolve().parent.parent),
                           capture_output=True, text=True, timeout=5)
        return sha + ("+dirty" if d.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return "ohne-repo"


def _format_detail(detail: dict[str, int]) -> str:
    """`counts 5->21` statt einer Zahl ohne Herkunft."""
    return ", ".join(f"{k} {old}->{new}" for k, (old, new) in
                     sorted(detail.items()) if old != new) or "keine Verschiebung"


def main() -> int:
    if "--self-test" in sys.argv:
        fails = self_test_check_counts()
        if fails:
            print(f"check_counts self-test: {len(fails)} FAIL")
            for f in fails:
                print(f"  {f}")
            return 1
        print(f"check_counts self-test: {_SELF_TEST_SCOPE[0]}")
        return 0

    # Filtere Flags und deren Werte (--json-report <path>)
    raw = sys.argv[1:]
    positional = []
    skip = False
    for a in raw:
        if skip:
            skip = False
            continue
        if a == "--json-report" or a == "--write-count":
            skip = True   # nächster Wert ist Pfad/Grund, kein Positionsargument
            continue
        if a.startswith("-"):
            continue
        positional.append(a)
    root = Path(positional[0]).resolve() if positional else Path.cwd()
    doc = root / "CLAUDE.md"
    if not doc.exists():
        print(f"CLAUDE.md nicht gefunden in {root}", file=sys.stderr)
        return 2

    text = doc.read_text(encoding="utf-8")
    rep = Report()
    waves, per = parse_waves(text)

    check_line_counts(text, root, rep)
    check_dead_refs(text, root, rep)
    check_counts(text, waves, per, rep, root)
    check_undocumented_tests(root, rep)
    check_doc_inventories(root, rep)
    # §A-NC: --write-count schreibt den Stand mit Grund fort.
    if "--write-count" in sys.argv:
        _save_count_snapshot(rep.checked, _count_reason(sys.argv))
    if "--run-tests" in sys.argv:
        check_tests(text, root, rep)

    # JSON-Report für /compliance Endpoint (--json-report <path>)
    json_report_path = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--json-report" and i + 1 < len(sys.argv):
            json_report_path = sys.argv[i + 1]
            break
    if json_report_path and "--run-tests" in sys.argv:
        from datetime import datetime as _dt, timezone as _tz
        report = {
            "generated_at": _dt.now(_tz.utc).isoformat(),
            "repository": str(root),
            "tests": _test_results,
        }
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    if "--json" in sys.argv:
        print(json.dumps({"checked": rep.checked, "problems": rep.problems},
                         indent=2, ensure_ascii=False))
        return 1 if rep.problems else 0

    main_waves = [w for w in waves if "." not in w]
    print(f"CLAUDE.md — {len(text.splitlines())} Zeilen")
    n_per = per or AGENTS_PER_WAVE
    n_main = len(main_waves) * n_per
    n_sub = len(waves) * n_per
    n_all = n_sub + COMPLIANCE_AGENTS
    print(f"Wellen-Tabelle: {len(waves)} Zeilen ({', '.join(waves)})")
    print(f"  -> {len(main_waves)} Hauptwellen x {n_per} = {n_main} Agenten")
    print(f"  -> mit Unterwellen: {n_sub}")
    print(f"  -> Gesamt (+{COMPLIANCE_AGENTS} Compliance): {n_all}")
    skipped = len(rep.env_skips)
    # §A-NE: der Nenner. `223 geprueft` und `210 ausgeschlossen` sind zwei
    # Zahlen ohne Verhaeltnis — 210 kann in 223 stecken oder daneben, und
    # der Unterschied ist ein Faktor im Pruefumfang. Gemessen:
    # `check_counts` erzeugt 21 Pruefungen und 210 Ausschluesse; sie sind
    # disjunkt, weil der `skip`-Zweig `continue`t. Also: Summe, nicht Bruch.
    # §A-NI: `checked` heisst im Report "Pruefungen", in der Ausgabe
    # "Angaben" — zwei Einheiten, ein Wort. Die Einheit gehoert an die
    # Zahl; keine Zahl dieser Zeile ist mehr ambivalent.
    status = _status_line(Checks(rep.checked, sum(rep.skips.values())),
                              len(rep.problems))
    if skipped:
        status += f", {skipped} uebersprungen (Umgebung)"
    # §A-NC: die Zahl, die sich aendert, nennt den Grund. Ohne diese Zeile
    # ist dieselbe Form wie zwei Nenner mit einem Namen: zwei Zahlen,
    # ein Name, und niemand sagt, welche gilt. Vergleich gegen den letzten
    # Lauf, mit Zaehlweise und Datum — nicht gegen eine gemerkte Zahl.
    dl = _delta_line(rep.checked)
    if dl:
        status += "\n" + dl
    print(f"\n{status}\n")

    # §A-NA (Nicht-Abwesenheit): `0 Abweichungen` heisst, dass alles
    # Gepruefte stimmt — nicht, dass nichts fehlt. Die Ausgabe nennt
    # jetzt ihren Bezugsraum: welche Felder zugesagt wurden und wie oft.
    # Eine Zahl, die nur Abweichungen zaehlt, ist laut fuer falsch und
    # still fuer fehlend; das ist dieselbe Form wie jeder Default dieser
    # Akte. `fields` macht den Bezugsraum sichtbar, ohne ihn zu bewerten:
    # wenige Felder in vielen Zusagen liest sich anders als eines je Feld.
    if rep.claims:
        field_counts: dict[str, int] = {}
        for f, _ in rep.claims:
            field_counts[f] = field_counts.get(f, 0) + 1
        detail = ", ".join(f"{f} x{n}" for f, n in sorted(field_counts.items()))
        print(f"Bezugsraum: {len(rep.claims)} Zusagen ueber "
              f"{len(field_counts)} Felder — {detail}")
        no_ref = field_counts.get("suite:ohne-skript", 0)
        # Die Grenze des Pruefers wird genannt, nicht verschwiegen: die
        # **Zahl** in `199/199` kann er nicht nachrechnen, ohne die Suite
        # zu fahren. Er prueft, dass das Skript existiert und dass
        # `passed <= total` gilt. Ein falscher Wert bei vorhandenem Skript
        # bleibt unsichtbar — dieselbe Form wie `0 Abweichungen` selbst.
        print(f"Grenze: die Zahl in `N/N` wird nicht nachgerechnet "
              f"(Skriptbezug {len(rep.claims) - no_ref}, ohne Skript {no_ref}); "
              "geprueft wird Existenz und passed<=total")
        # §A-NB: die zweite Grenze — die **Auswahl**. Ohne sie ist der
        # Bezugsraum eine Entscheidung, die man erst beim Lesen des
        # Pruefers sieht, und beim naechsten Feld wird sie wieder
        # getroffen, ohne dass jemand weiss, welche schon ausgeschlossen
        # sind. Drei Felder, drei Gruende, benannt.
        print(_selection_line(rep.skips))
        # §A-NG: `.git/` ist der richtige Ort (kein Diff, Export sieht ihn),
        # aber `git status`, `diff` und `clean` sehen ihn nicht. Wer die
        # Differenzzeile loswerden will, loescht eine Datei, die nirgends
        # auftaucht — und der naechste Lauf sagt `kein Vorlauf`, nicht
        # unterscheidbar von einem echten ersten Lauf. Also: den Ort nennen.
        if _SNAPSHOT_SEEN[0] is not None:
            # §A-JM: relativ zum **Repo**, nicht zur Shell. `Path.cwd()`
            # war die Annahme, dass das Arbeitsverzeichnis das Repo ist —
            # dieselbe Annahme wie beim relativen `--git-common-dir`, nur
            # eine Zeile weiter. Ausserhalb des Repos bleibt der Pfad
            # absolut, statt in einen `ValueError` zu laufen.
            try:
                rel = _SNAPSHOT_SEEN[0].relative_to(root)
            except ValueError:
                rel = _SNAPSHOT_SEEN[0]
            print(f"Vorlauf: {rel} (nicht versioniert, git-ignoriert)")
            # §A-J: die Zahlen-Geschichte ist aus dem Code raus (Guard). Sie
            # lebt in der Rundentabelle — und deren Commitzustand wird
            # genannt, nicht angenommen.
            print("Rundentabelle: order_execution_engine/ops/TAG7_ABNAHME.md "
                  f"({_doc_tracked()})")

    for s in rep.env_skips:
        print(f"  ⏭️  {s['script']}  — {s['note']}")

    for p in rep.problems:
        loc = f"Zeile {p['line']:>4}" if p["line"] else "         "
        print(f"  {loc}  {p['kind']}")
        print(f"            Doku: {p['doc']}   tatsaechlich: {p['real']}"
              + (f"   ({p['note']})" if p["note"] else ""))

    if not rep.problems and not skipped:
        print("  Keine Abweichungen.")
    return 1 if rep.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
