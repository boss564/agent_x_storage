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

import ast
import datetime
import hashlib
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

    **Vertrag des Zaehlers (§A-KC).** `Checks` bewacht die Anzeige — es
    macht "21 Angaben" unbaubar. Es macht `checked == 21` nicht wahr; das
    ist Aufgabe dieses Zaehlers, und er hat drei Regeln:

      *gezaehlt wird, was geprueft wurde*
          `ok()` und `fail()` erhoehen um genau eins. Auch eine Pruefung,
          die **scheitert**, ist gelaufen — sie ist geprueft.
      *nicht gezaehlt wird, was nicht lief*
          `skip()` und `env()` erhoehen **nie**. Eine uebersprungene Pruefung
          ist keine Pruefung; sie gehoert in `skips`, und `_status_line`
          nennt sie getrennt.
      *`claims` zaehlen nicht*
          Eine Zusage ist, was es geben **muesste** — keine Messung.

    Wer eine vierte Regel braucht (z. B. Unterpruefungen), muss sie hier
    hinschreiben und mit einem Fall belegen. Ohne Test ist der Zaehler
    eine Zahl mit einer Behauptung daneben — genau der Zustand, den
    Runde 23 beschreibt.
    """

    def __init__(self) -> None:
        self.problems: list[dict] = []
        self.env_skips: list[dict] = []
        # §A-KC: `checked` bleibt EIN int, mit benanntem Vertrag — siehe
        # Docstring der Klasse. Die Alternative (Checks bei jedem Inkrement
        # neu bauen) waere "sauberer", kostet aber eine Allokation pro
        # Pruefung und macht den Zaehler zu einem unveraenderlichen Wert,
        # der an jeder Stelle neu zugewiesen werden muss. Die Zahl bleibt
        # im Bereich weniger Hundert (siehe `_status_line`), dort ist der
        # Unterschied nicht messbar.
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

    def claim(self, field: str, count: int, line: int | None = None,
              text: str = "") -> None:
        """Eine Zahl, die im Doku-Text steht und im Code gezaehlt werden muss.

        §A-MB (Runde 42): **wo** gezaehlt wurde, nicht nur wie oft. Ohne
        Position ist `24 Zusagen` bei halbem Text keine Aussage darueber,
        ob der Extraktor misst oder nur weniger liest — die Gegenprobe
        `28 -> 24` belegte das eine, nicht das andere.
        """
        if not field:
            raise AssertionError("jede Zusage braucht ihren Feldnamen")
        self.claims.append((field, int(count), line, text[:80]))

    def fail(self, line: int | None, kind: str, doc, real, note: str = "",
             state: str = "offen") -> None:
        self.checked += 1
        self.problems.append({"line": line, "kind": kind, "doc": doc,
                              "real": real, "note": note, "state": state})

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
                 root: Path | None = None,
                 wave_index: dict[str, str] | None = None,
                 wave_ctx: str | None = None,
                 claims_rep: Report | None = None) -> None:
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
    # §A-NP: der Wellenindex wird **einmal** gebaut, nicht pro Zeile —
    # dann ist `check_counts` weiter zeilenlokal (§A-NE), weil die Zahl
    # pro Zeile nur von der Zeile und diesem Index abhaengt, nicht von
    # den Nachbarzeilen.
    _wave_scripts = wave_index if wave_index is not None else _wave_script_index(text)
    _wave_ctx: str | None = None
    # §A-NM (Runde 51): Zusagen landen in `claims_rep`, wenn der Aufrufer
    # einen eigenen Report uebergibt. `rep` traegt dann nur die **Befunde**
    # — die Kopfzeile zaehlt Zusagen und Abweichungen getrennt (§A-NI).
    _cl = claims_rep if claims_rep is not None else rep
    for lineno, raw in enumerate(text.splitlines(), 1):
        _hm = re.match(r"^#{1,6}\s*(?:§[\d.]+\s*)?(?:Wave|Welle)\s*(\d+(?:\.\d+)?)", raw)
        if _hm:
            _wave_ctx = _hm.group(1)
        if _wave_ctx is None:
            _wave_ctx = wave_ctx
        refs = re.findall(r"`(scripts/test_[\w/]+\.py)`", raw)
        for m in suite_row.finditer(raw):
            passed, total = int(m.group(1)), int(m.group(2))
            if refs:
                for ref in refs:
                    _cl.claim(f"suite:{ref}", total, lineno, raw)
                    # §A-NL (Runde 50): `root is None` hiess bisher
                    # „Pruefung aus" — und das war genau dann der Fall, wenn
                    # geprueft werden sollte (erster Lauf in fremder
                    # Umgebung). Alle angetroffenen Suite-Zusagen fielen aus
                    # der Zahl. Kein Skip, sondern ein Fail mit dem Namen
                    # des Grundes.
                    if root is None:
                        rep.fail(lineno, "Suite nicht pruefbar (kein Baum)",
                                 f"{passed}/{total} ({ref})", "root=None")
                    elif passed > total:
                        # §A-YC (Runde 52): `passed > total` ist eine
                        # **unmoegliche Aussage** — sie gilt unabhaengig
                        # davon, ob das Skript existiert. Vor Runde 52 stand
                        # die Existenzpruefung zuerst, und der Zweig war
                        # damit unerreichbar fuer jede Zeile, deren Skript
                        # fehlt — also fuer fast jede kaputte Zeile.
                        rep.fail(lineno, "Suite: passed > total",
                                 f"{passed}/{total} ({ref})", "unmoeglich")
                    elif not (root / ref).exists():
                        rep.fail(lineno, "Suite zugesagt, Skript fehlt",
                                 f"{passed}/{total} ({ref})", "nicht vorhanden")
                    else:
                        rep.ok()
            elif total >= 20:
                # §A-NP (Runde 51): „ohne Skript" war ein Satzmerkmal, kein
                # Dateimerkmal. Elf der zwoelf Zusagen haben ein Skript —
                # es steht nur in einer anderen Zeile. Also: Bezug aus der
                # **ganzen Datei**, mit Wellenpaarung. Die Zwölf sind
                # gemessen, nicht behauptet: `test_wave15_public_portal.py`
                # existiert nicht (die Suite steht unter
                # `scripts/test_public_portal.py`).
                cand = _suite_ref_for(raw, _wave_ctx, _wave_scripts)
                if cand:
                    _cl.claim(f"suite:{cand}", total, lineno, raw)
                    if not (root / cand).exists():
                        rep.fail(lineno, "Suite zugesagt, Skript fehlt",
                                 f"{passed}/{total} ({cand})", "nicht vorhanden")
                    else:
                        rep.ok()
                else:
                    _cl.claim("suite:ohne-skript", total, lineno, raw)
                    _cl.skip("tests_ohne_skript")
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
        # §A-NE (Runde 48): `root` explizit — ein Aufruf ohne
        # liest im Klon relativ und meldet dort andere Zahlen.
        check_counts(text, waves, AGENTS_PER_WAVE, rep,
                     root=Path(__file__).resolve().parent.parent)
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
    # §A-ND: die 28 Zusagen gegen die live gezaehlte Menge, nicht gegen
    # ein Literal. Ohne diesen Test ist `28` in Runde 44 ein Literal, das
    # niemand mehr herleiten kann.
    failures.extend(_self_test_claim_count())
    # §A-NM/§A-NN (Runde 51): die zwei neuen Pruefer brauchen einen
    # nachweislich roten Lauf (vierter Punkt) — sonst sagt ihre Null nichts.
    failures.extend(_self_test_status_line_none())
    failures.extend(_self_test_ignored_test_paths())
    failures.extend(_self_test_root_counts())
    failures.extend(_self_test_literal_errors())
    failures.extend(_self_test_calibration_classes())
    failures.extend(_self_test_probe_anchors_self())
    failures.extend(_self_test_reads_without_root())
    failures.extend(_self_test_default_root())
    failures.extend(_self_test_gitlink())
    failures.extend(_self_test_akt_block())
    failures.extend(_self_test_tally_numbers())
    # §A-NS (Runde 52): der Beinahe-Verlust und seine Ursache.
    failures.extend(_self_test_akte_write_mode())
    failures.extend(_self_test_akte_guard())
    failures.extend(_self_test_block_kind())
    failures.extend(_self_test_prose_fractions())
    failures.extend(_self_test_cwd_readers())
    failures.extend(_self_test_reader_calls())
    failures.extend(_self_test_wirkung())
    # §A-NL (Runde 50): der Pruefer ueber den Pruefern — Namensbasen == 0.
    failures.extend(_self_test_auswahl_truthiness())
    failures.extend(_self_test_name_bases())
    failures.extend(_self_test_anchor_uniqueness())
    if failures:
        return failures
    # §A-MN (Runde 44): die drei neuen Pruefer sind **eigene** Selbsttests
    # und muessen hier erscheinen — ein Selbsttest, der nicht in der
    # Kopfzeile steht, ist ein Selbsttest, den niemand bucht. Die Summe
    # steht in der Ausgabe, nicht im Kommentar.
    _SELF_TEST_SCOPE[0] = ("37/37 (5 Zaehlung + 5 Bezugsraum + 14 "
                           "Differenz/Nenner/Ort/Einheit/Zwillingspfad"
                           " + 1 root-Zaehlung + 1 Literal-Regel"
                           " + 1 Klassenliste + 1 Selbstprobe"
                           " + 1 Lesepfad + 1 Default-Ort + 1 Gitlink + 1 Akte-Block"
                           " + 1 Tally-Zahlen + 1 Schreibmodus + 1 Akte-Guard"
                           " + 1 CWD-Rollen + 1 Leser-Aufruf, "
                           "28 Zusagen live)")


def _self_test_root_counts() -> list[str]:
    """Steuert `root` die **gezaehlte** Zahl? (§A-MK, Runde 44)

    Zwei Baeume, zwei Zahlen — und die Differenz ist die Aussage. Der
    Klon hat keine `scripts/`, also mehr Befunde; der eigene Baum hat
    keine. Waeren beide gleich, waere `root` ein Etikett ohne Wirkung —
    genau der Fehler, den Runde 41 fand, als der Report mit fremdem
    `root` die Tests des eigenen Repos las.

    Die Erwartungen sind **Literale mit Herkunft**, nicht Ableitungen
    aus dem Pruefling (§A-ML). Ein `assert total(a) != total(b)` waere
    auch dann gruen, wenn beide 0 sind.
    """
    from pathlib import Path as _P
    own = _P.cwd()
    clone = _P("/tmp/klonprobe")
    out: list[str] = []
    if not (clone / "CLAUDE.md").exists():
        return out      # kein Klon: nichts zu messen, nichts zu behaupten

    def count(root: _P) -> int:
        text = (root / "CLAUDE.md").read_text(encoding="utf-8")
        rep = Report()
        w, p = parse_waves(text)
        check_line_counts(text, root, rep)
        check_dead_refs(text, root, rep)
        check_counts(text, w, p, rep, root)
        return rep.checked

    # Herkunft: beide Zahlen sind **Stichproben** aus dem Lauf vom
    # 2026-10-17 (Runde 44), keine Konstanten — aendert sich die Doku,
    # aendern sie sich. Geprueft wird die **Ordnung**, die aus der
    # Struktur folgt: der Klon zaehlt mehr, weil jeder fehlende Pfad
    # ein Befund ist.
    n_own, n_clone = count(own), count(clone)
    if n_clone <= n_own:
        out.append(
            f"root wirkt nicht auf die Zaehlung: eigen {n_own}, Klon "
            f"{n_clone} — der Klon muss mehr Befunde haben")
    return out


# §A-ML (Runde 44): jede Erwartung im Test ist ein Literal im Test.
#
# Dreimal in vier Runden mass sich ein Pruefer selbst, und dreimal wurde
# es verschieden entdeckt:
#
#   R40  Ankerliste zaehlte ihre Abschrift   — durch eine Zahl, die nicht sein konnte
#   R42  Erwartung kam aus `positions[-1]`   — durch eine Zahl, die nicht sein konnte
#   R43  Gegenproben (b), (c) waren gruen    — durch Hinsehen
#
# Die dritte wurde durch Aufmerksamkeit gefunden, und Aufmerksamkeit ist
# die Ressource, die in Runde 50 nicht mehr da ist. Die Regel, die es
# wiederholbar macht, ist eine Zeile: **keine Ableitung auf der linken
# Seite eines Vergleichs.** Die Zahl steht da, mit Herkunft im Kommentar;
# der Pruefling darf sie nur verfehlen. Ausnahmen sind benannt: zwei
# Messungen duerfen verglichen werden (die Aussage ist dann die
# Differenz), benannte Konstanten in Grossbuchstaben sind Literale.
# §A-ML: Namen, die im Test einen **selbstgeschriebenen** Quellethext
# tragen. Sie sind die Erwartung, nicht der Pruefling.
_CONSTRUCTION_CONSTS = ("anch", "marker", "A", "sep", "probe", "backward",
                        "src_probe", "fake", "fixture", "role", "reg")


def _str_concat_of_literals(n: "ast.AST", consts: tuple[str, ...]) -> bool:
    """Ist `n` eine Verkettung aus String-Literalen und `consts`? (\u00a7A-ML)

    Ein Test, der seinen Eingabetext selbst schreibt
    (`_probe_anchors("x = g()  # " + anch + " bewusst\\n")`), misst eine
    Funktion gegen eine **Konstruktion** — der Text ist die Erwartung.
    Nur wenn der Text aus dem Pruefling kaeme, waere er eine Ableitung.
    """
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return True
    if isinstance(n, ast.Name):
        return n.id in consts
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        return (_str_concat_of_literals(n.left, consts)
                and _str_concat_of_literals(n.right, consts))
    return False


def _self_test_literal_errors(src: str | None = None) -> list[str]:
    """Findet Erwartungen, die aus dem Pruefling stammen (§A-ML).

    `src` ist pruefbar, weil der Pruefer selbst pruefbar sein muss —
    sonst gilt fuer ihn, was er fuer andere findet. Default ist die
    eigene Datei.
    """
    import ast
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    pure = {"len", "any", "all", "isinstance", "sorted", "tuple", "list",
            "set", "str", "int", "sum", "min", "max", "range", "enumerate"}

    def is_literal(n: ast.AST) -> bool:
        if isinstance(n, ast.Constant):
            return True
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return isinstance(n.operand, ast.Constant)
        if isinstance(n, (ast.Tuple, ast.List)):
            return all(is_literal(e) for e in n.elts)
        if isinstance(n, ast.Name) and n.id.isupper():
            return True
        return False

    def is_derived(n: ast.AST) -> bool:
        """`positions[-1]`, `median(...)`, `len(x) - 1` — aus dem Pruefling."""
        if isinstance(n, ast.Subscript):
            # §A-ML: der **Traeger** entscheidet. `median(x)[0]` ist eine
            # Ableitung mit konstantem Index — der Index macht sie nicht
            # zum Literal. `f(x)[-1]` ebenso. Nur wenn Traeger und Index
            # harmlos sind, ist das Abonnement eine Formaussage.
            if is_derived(n.value):
                return True
            return not isinstance(n.slice, ast.Constant)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            return n.func.id not in pure
        if isinstance(n, ast.BinOp):
            return is_derived(n.left) or is_derived(n.right)
        if isinstance(n, ast.UnaryOp):
            return is_derived(n.operand)
        return False

    out: list[str] = []
    # §A-ML: eine zweite Seite, die aus der **Umgebung** kommt (Dateisystem,
    # Prozess, benannte Erwartung), ist eine unabhaengige Messung — kein
    # Selbstbezug. Der Pruefer braucht diese Liste, sonst meldet er jeden
    # korrekten Vergleich und wird abgeschaltet, bevor er den einen
    # falschen findet.
    independent = {"here", "root", "clone", "own", "expect_bad", "line",
                   "got", "c", "expect", "want", "soll", "ist"}
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith(
                "_self_test"):
            continue
        for cmp in ast.walk(fn):
            if not isinstance(cmp, ast.Compare):
                continue
            if all(isinstance(o, (ast.Is, ast.IsNot)) for o in cmp.ops):
                continue
            # Erwartung ist ein Literal, wenn **eine** Seite Literal und
            # die andere Messung ist — dann ist die Aussage sauber.
            sides = [cmp.left] + list(cmp.comparators)
            if any(is_literal(s) for s in sides) and not any(
                    is_derived(s) for s in sides):
                continue
            if all(is_literal(o) for o in cmp.comparators) and is_literal(
                    cmp.left):
                continue
            if all(is_derived(s) for s in sides):
                continue
            if any(isinstance(s, ast.Name) and s.id in independent
                   for s in sides):
                continue
            # Nur **Zahlvergleiche** sind Erwartungen: ein Abonnement mit
            # konstantem Index (`p["kind"]`) ist eine Aussage ueber Form;
            # ein Abonnement mit **berechnetem** Index (`positions[-1]`)
            # ist eine Aussage ueber eine Position — und damit aus dem
            # Pruefling. Genau dieser Fall war Runde 42.
            subscript_derived = any(
                isinstance(s, ast.Subscript) and is_derived(s) for s in sides)
            numeric = (ast.Call, ast.BinOp, ast.UnaryOp)
            call_derived = any(isinstance(s, numeric) and is_derived(s)
                               for s in sides)
            if not call_derived and not subscript_derived:
                continue
            for s in sides:
                # §A-ML: eine Seite, die ein **String- oder Zahl-Literal
                # enthaelt** (auch in `(...)`), ist eine benannte Erwartung.
                # `_probe_anchors(...) != ("x = ...",)` ist ein Literal-
                # tupel, keine Ableitung. `_doc_tracked`/`repo_root` pruefen
                # eine **zweite** Quelle (Dateisystem) — kein Selbstbezug.
                if isinstance(s, ast.Name) and s.id in pure:
                    continue
                if isinstance(s, (ast.Tuple, ast.List)) and all(
                        is_literal(e) for e in s.elts):
                    continue
                if isinstance(s, ast.Call) and isinstance(s.func, ast.Name) \
                        and s.func.id in ("_doc_tracked", "repo_root"):
                    continue
                # Ein **Stringvergleich** (`"0" not in ...`) ist keine Zahl.
                if isinstance(s, ast.Compare):
                    continue
                # §A-ML: ein **konstruierter Eingabetext** ist kein
                # Selbstbezug. `_probe_anchors("x = g()  # " + anch + ...)`
                # prueft eine Funktion gegen einen Text, den der Test
                # **selbst schreibt** — der Text ist die Erwartung, nicht
                # der Pruefling. Er ist vollstaendig Literal, sobald man
                # die benannten Konstanten (`anch`) einsetzt.
                if isinstance(s, ast.BinOp) and _str_concat_of_literals(
                        s, _CONSTRUCTION_CONSTS):
                    continue
                # Der Call traegt die Konstruktion **innen**: `f("x" + anch)`.
                if isinstance(s, ast.Call) and all(
                        _str_concat_of_literals(a, _CONSTRUCTION_CONSTS)
                        or is_literal(a) or isinstance(a, ast.Dict)
                        for a in s.args):
                    continue
                if is_derived(s) and not is_literal(s):
                    out.append(
                        f"{fn.name}: Erwartung aus dem Pruefling "
                        f"(Zeile {s.lineno}) — Literal mit Herkunft, "
                        f"sonst misst der Test sich selbst")
    return out


# §A-MM (Runde 44): der Kalibrierlauf summiert aus den **Pruefern**, nicht
# aus einer handgeschriebenen Tabelle.
#
# Bis Runde 43 stand die Fuenf-Klassen-Tabelle in der Akte, und die fuenfte
# Klasse (`Inventar-Dokument fehlt`) stand die ganze Zeit im Code und nicht
# in der Tabelle. Die Summe schloss eine zu niedrig und der Report meldete
# eine zu hoch. Das ist derselbe Fehler wie Runde 40 (`20 gegen 8`) und
# Runde 41 (`10 statt 8`): eine handgefuehrte Liste ueber einem Code, der
# sie hergibt.
#
# Die Frage, die die Runde ueberlebt: was passiert, wenn ein sechster
# Pruefer dazukommt?  Heute schliessen Report und Akte; mit dem sechsten
# und unveraenderter Tabelle schloesse die Akte eine zu niedrig — und die
# Akte ist die, die man in Runde 50 liest.
# Darum wird die Klassenliste **ausgegeben**, nicht als Eingabe gelesen.
def calibration_run(root: Path, text: str | None = None,
                    with_tests: bool = False,
                    extra_checkers: tuple = ()) -> dict[str, object]:
    """Ein Lauf, **sechs** Pruefer — die Kette, die `main` faehrt (§A-MM).

    Rueckgabe:
        {"total": int, "classes": [(name, n), ...], "unclassified": int,
         "chain_total": int}

    `classes` ist die **Ausgabe** des Laufs, nicht eine Eingabeliste.
    `unclassified` ist die Differenz gegen die `main`-Kette: Befunde, fuer
    die **kein** Pruefer in dieser Liste zustaendig ist. Sie muss 0 sein.

    **Herkunft der Korrektur (Runde 44, nachgetragen):** die erste Fassung
    dieses Laufes kannte fuenf Pruefer. `main` faehrt sechs —
    `check_undocumented_tests` fehlte. Im eigenen Baum waren beide Summen
    null, die Luecke unsichtbar; im Klon stand die Summe unter der Kette,
    und die Differenz war echte Befunde ohne Klasse. Das ist derselbe
    Fehler, den diese Funktion abschaffen sollte: eine Handliste ueber
    einem Code, der sie hergibt. Zweite Fassung: `check_counts` ohne
    `root` — die Zahl hing am Aufrufweg.
    """

    def chain(rep: Report) -> None:
        """Die Reihenfolge ist die von `main` — nicht eine eigene."""
        w, per = parse_waves(doc)
        check_line_counts(doc, root, rep)          # type: ignore[name-defined]
        check_dead_refs(doc, root, rep)            # type: ignore[name-defined]
        check_counts(doc, w, per, rep, root)       # type: ignore[name-defined]
        check_undocumented_tests(root, rep)        # type: ignore[name-defined]
        check_doc_inventories(root, rep)           # type: ignore[name-defined]
        if with_tests:
            check_tests(doc, root, rep)            # type: ignore[name-defined]
        # §A-MQ (Runde 45): Pruefer, die **nur** die Kette faehrt. Sie
        # stehen in keiner Klasse — genau darum sind sie der Lueckenfall,
        # den `unclassified` zaehlen muss.
        # §A-MU (Runde 46): und sie gehoeren in `reported`. Sonst sind
        # `total` und `reported` im einzigen Zustand gleich, in dem sich
        # die drei Zahlen des Laufs trennen koennten — im eigenen Baum
        # sind alle drei null und widersprechen sich nicht.
        for _, extra in extra_checkers:
            before = len(rep.problems)
            extra(rep)
            lid = len(reported)
            reported.append(Report())
            reported[lid].problems = rep.problems[before:]

    doc = text if text is not None else (root / "CLAUDE.md").read_text(
        encoding="utf-8")
    waves, per = parse_waves(doc)
    _claims_rep = Report()
    classes: list[tuple[str, int]] = []
    reported: list[Report] = []

    def run(name: str, fn, *args, kw: dict | None = None) -> None:  # type: ignore[no-untyped-def]
        rep = Report()
        fn(*args, rep, **(kw or {}))
        classes.append((name, len(rep.problems)))
        reported.append(rep)

    def run_kw(name: str, fn, *args, **kw) -> Report:  # type: ignore[no-untyped-def]
        """Fuer Pruefer, deren `rep` **nicht** der letzte Parameter ist."""
        rep = Report()
        fn(*args, rep, **kw)
        classes.append((name, len(rep.problems)))
        reported.append(rep)
        return rep

    run("Zeilen", check_line_counts, doc, root)
    run("Referenzen", check_dead_refs, doc, root)
    # §A-MM: `root` ist hier **nicht** optional. `check_counts` liefert ohne
    # `root` andere Befunde (im Klon: keine statt sechzehn) — die Zahl
    # haengt sonst vom Aufrufweg ab, und genau das war der Fehler, den
    # `_git_callers_without_cwd` in Runde 41 fand.
    run_kw("Wellen", check_counts, doc, waves, per, root=root,
           claims_rep=_claims_rep)
    run("Tests ohne Skript", check_undocumented_tests, root)
    run("Inventare", check_doc_inventories, root)
    # §A-NN (Runde 51): derselbe Pruefer wie in `main` — sonst kennt
    # `main` eine Pruefung, die der Kalibrierlauf nicht sieht, und die
    # Differenz ist genau die Luecke, die §A-MT meldet.
    # §A-NW: **direkt** mit eigenem Report, nicht ueber `run(...)`.
    # `_checker_gap` liest den AST nach `check_*`-Calls; `run("Name", fn,
    # root)` ist ein `Name`-Argument und damit fuer den Pruefer unsichtbar.
    # Die Umhuellung ist Komfort, kein Grund, den Pruefer blind zu machen.
    _tp = Report()
    check_test_paths_ignored(root, _tp)
    classes.append(("Testpfade", len(_tp.problems)))
    reported.append(_tp)
    # §A-NS (Runde 52): die Ursache des Beinahe-Verlusts — `open(..., "w")`
    # auf einer Akte. Ueber `run(...)`, damit Kette und Kalibrierlauf
    # dieselbe Klasse zweimal nennen — `_checker_gap` liest den AST nach
    # `check_*`-Calls, und `run("Schreibmodus", check_akte_write_mode,
    # root)` uebergibt den Namen als `Name`-Argument; der Pruefer sieht ihn.
    run("Schreibmodus", check_akte_write_mode, root)
    # §A-ZB (Runde 53): der Bruchzahlen-Pruefer — in `main` und hier.
    # Er steht in beiden Ketten, sonst meldet §A-MT eine Differenz.
    run("Fließtext-Brüche", check_prose_fractions, root)
    if with_tests:
        run("Testsuite", check_tests, doc, root)

    chain_rep = Report()
    chain(chain_rep)
    total = sum(n for _, n in classes)
    # §A-NM (Runde 51): `unclassified` kann **nicht negativ** sein. Ein
    # negativer Wert heisst, dass ein Pruefer in einer Klasse zaehlt und in
    # der Kette nicht — `total > chain_total`. Das ist derselbe Fehler wie
    # ein unclassified > 0, nur mit dem Vorzeichen vertauscht; vor Runde 51
    # lief er als `-1` durch und wurde von keiner Zusicherung gefangen.
    _raw = len(chain_rep.problems) - total
    return {
        "total": total,
        "classes": sorted(classes, key=lambda kv: -kv[1]),
        # Ein negativer Wert bleibt sichtbar (er ist ein Fehler, kein
        # Rundungsrest) — aber die Kopfzeile nennt ihn als **Zaehlfehler**,
        # nicht als Abweichung.
        "unclassified": _raw,
        "chain_total": len(chain_rep.problems),
        # §A-MR (Runde 45): `sum(classes) + unclassified == chain_total`
        # haelt per Konstruktion zusammen, was aus derselben Zahl gebaut
        # ist. Die **dritte** Zahl ist die Summe der Einzelbefunde: sie
        # entsteht, indem jeder Pruefer seine Befunde meldet, und wird
        # gegen `total` gehalten. Zwei Wege, die denselben Fehler gleich
        # falsch gehen, sind ein Weg mit zwei Ausgaengen — diese Zahl
        # geht einen dritten.
        "reported": sum(len(rep.problems)
                        for rep in reported),
        # §A-MT (Runde 46): die **Gegenrichtung**. `unclassified` zaehlt
        # Pruefer, die die Kette faehrt und keine Klasse kennt. Der Fehler
        # der letzten Runde war ein Pruefer zu **wenig**:
        # `check_undocumented_tests` stand in `main` und nicht hier. Das
        # faengt nur eine Differenz zwischen zwei Mengen — beide
        # Richtungen, nicht eine.
        "unchecked": _checker_gap("main", "calibration_run"),
        "unclassified_checkers": _checker_gap("calibration_run", "main"),
        # §A-NM (Runde 51): die Zusagen ohne Skript sind Zahlen der
        # Kopfzeile. Ein Generator, der sie nur im Fliesstext kennt,
        # wiederholt den Klammer-Fehler.
        "claims": list(_claims_rep.claims),
    }


def _checker_gap(fn_a: str, fn_b: str, src: str | None = None) -> int | None:
    """Pruefer, die `fn_a` faehrt und `fn_b` nicht kennt.

    Dieselbe Regel wie `_rules_run`, aber zwischen zwei **Funktionen**:
    die Menge kommt aus dem **AST beider Funktionen**, nicht aus einer
    Handliste. `_checker_gap("main", "calibration_run")` = `unchecked`:
    was die Produktion faehrt und der Kalibrierlauf nicht sieht.

    §A-MW (Runde 47): die erste Fassung bildete die Menge aus dem
    **Namensmuster** `check_*`. Das ist eine Handliste in Regex-Form:
    ein Pruefer namens `_reads_without_root` stand in keiner der beiden
    Mengen, und eine Registry (`for c in CHECKS: c(root)`) machte beide
    Differenzen `0/0` — der Pruefer konservierte die Vervielfaeltigung,
    die er abschaffen soll.

    §A-NB (Runde 48): **`0` ist die Zahl, die „gruen" und „blind"
    gemeinsam haben.** Ein dynamisch gebautes Register
    (`CHECKS = tuple(c for c in (...))`) kann dieser Pruefer nicht
    aufloesen — und gab bisher `0` zurueck, also Freispruch. Drei
    Zustaende, zwei davon `0`, ist dieselbe Krankheit wie Runde 44, eine
    Ebene hoeher. Darum:

      int   — gezaehlt, das Register ist aufgeloest
      None  — der Pruefer **kennt** das Muster (eine `for`-Schleife ueber
              einen Namen), findet das Ziel aber nicht. Das ist ein
              Befund, kein Freispruch. Der Selbsttest verlangt
              `isinstance(..., int)` fuer die echten Richtungen.
    """
    import ast
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)

    def calls(fn_name: str) -> tuple[set[str], bool]:
        """(Menge, blind) — `blind` heisst: Muster gesehen, Ziel nicht."""
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and n.name == fn_name:
                return _called_checkers(n, tree)
        return set(), False

    a, blind_a = calls(fn_a)
    b, blind_b = calls(fn_b)
    if blind_a or blind_b:
        return None     # Muster bekannt, Ziel unaufloesbar: nicht bewertbar
    if not a or not b:
        return 0        # Testprobe ohne beide Funktionen: nichts zu beweisen
    return len(a - b)


def _report_functions(tree) -> set[str]:
    """Funktionen des Moduls, die eine `Report`-Instanz entgegennehmen.

    Die **Rolle** ist der Befund-Carrier, nicht der Name: jeder
    Einzelpruefer hat `rep` in der Signatur (als `rep`, `report` oder
    typisiert). Damit ist die Menge unabhaengig davon, wie eine Funktion
    heisst und ob sie einzeln oder ueber eine Registry gerufen wird.
    """
    out: set[str] = set()
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef):
            continue
        names = [a.arg for a in n.args.args] + [a.arg for a in n.args.kwonlyargs]
        if n.name in _NOT_CHECKERS:
            continue
        if any(x in ("rep", "report") for x in names) or any(
                isinstance(a.annotation, ast.Name) and a.annotation.id == "Report"
                for a in n.args.args):
            out.add(n.name)
    return out


# Funktionen, die `rep` tragen, ohne Befund-Pruefer zu sein: die
# Kette, der Kalibrierlauf, die Fassade. Sie *rufen* Pruefer.
_NOT_CHECKERS = frozenset({"chain", "main", "calibration_run", "_run_all",
                           "run", "run_kw", "check_all"})


# §A-NH (Runde 49): die Menge der Register, **deklariert**. Die dritte
# Fassung der Heuristik (`for c in CHECKS: apply(c)` — Iterat wird
# durchgereicht, nicht gerufen) waere wieder blind. Vier Fassungen
# schliessen das nicht; die Umkehrung schon: nicht das Register wird
# erkannt, sondern das **Unbekannte** gemeldet. Jede `for`-Schleife, die
# ihr Iterat an eine Funktion gibt, ist ein Register — steht das Ziel
# nicht hier, ist das Ergebnis `None` und kein Freispruch.
#
# Die Verletzung dieser Liste ist rot: ein neues Register ohne Eintrag
# faellt beim ersten Lauf auf. Das ist der Unterschied zur Baseline — die
# Baseline schweigt, wenn sie verletzt wird.
_REGISTRIES = frozenset({})


def _called_checkers(fn: ast.FunctionDef, tree=None) -> tuple[set[str], bool]:
    """Welche Pruefer faehrt eine Funktion — einzeln **oder** als Registry?

    §A-MW (Runde 47): ein direkter `check_*`-Aufruf **und** eine
    `for`-Schleife ueber einen Namen.

    §A-NC (Runde 48): aufgeloest ueber das **Objekt der Iteration**. Ein
    Muster, dessen Ziel der Pruefer nicht findet, liefert `blind = True`.

    §A-NH (Runde 49): die dritte Luecke. `for c in CHECKS: apply(c)`
    reicht das Iterat durch, statt es zu rufen — die Fassung aus Runde 48
    hielt das fuer eine Datenschleife und gab `0` (gruen). Jetzt gilt:
    jede `for`-Schleife, die ihr Iterat **irgendwo als Argument** gibt,
    ist ein Register. Ist das Ziel statisch aufloesbar, wird gezaehlt;
    sonst `blind`. Und ist der Name nicht in `_REGISTRIES` deklariert,
    ebenso `blind` — auch wenn er aufloesbar waere. Damit ist die Liste
    die einzige Stelle, an der ein Register stehen darf, und ihr Fehlen
    ist laut.

    Rueckgabe: `(Menge, blind)`.
    """
    got: set[str] = set()
    blind = False
    registry: dict[str, set[str]] = {}
    if tree is not None:
        registry = _registry_tables(tree)
    for c in ast.walk(fn):
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name):
            if c.func.id.startswith("check_"):
                got.add(c.func.id)
            # §A-NS (Runde 52): ein Pruefer als **Argument** — die Form
            # `run("X", check_akte_write_mode, root)`. Bis Runde 51 war sie
            # fuer diesen Pruefer unsichtbar, und `unchecked=1` war die
            # Folge: die Kette kannte den Pruefer nicht, der Kalibrierlauf
            # schon.
            for a in list(c.args) + [k.value for k in c.keywords]:
                if isinstance(a, ast.Name) and a.id.startswith("check_"):
                    got.add(a.id)
        if not isinstance(c, ast.For) or not isinstance(c.target, ast.Name):
            continue
        var = c.target.id
        if not (_calls_var(c.body, var) or _passes_var(c.body, var)):
            continue        # reine Datenschleife: `for p in rep.problems:`
        target = c.iter
        if not isinstance(target, ast.Name):
            blind = True
            continue
        if target.id not in _REGISTRIES:
            blind = True    # Register nicht deklariert: laut, nicht still
            continue
        if target.id in registry:
            got |= registry[target.id]
        else:
            blind = True    # deklariert, aber dynamisch gebaut
    return got, blind


def _passes_var(body: list[ast.AST], var: str) -> bool:
    """Wird `var` im Rumpf **als Argument an eine Funktion** gegeben?

    §A-NH: der Testfall ist `apply(c, root)` — ein freier Name. Ein
    **Methodenaufruf** wie `positional.append(a)` bindet `a` an eine
    Liste, nicht an eine Funktion; das ist kein Register. Die Unterscheidung
    ist dieselbe wie ueberall in dieser Datei: die Form, nicht der Name.
    """
    for n in body:
        for c in ast.walk(n):
            if not (isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Name)):
                continue
            if any(isinstance(a, ast.Name) and a.id == var for a in c.args):
                return True
            if any(isinstance(k.value, ast.Name) and k.value.id == var
                   for k in c.keywords):
                return True
    return False


def _calls_var(body: list[ast.AST], var: str) -> bool:
    """Wird `var` im Schleifenrumpf als Funktion gerufen?"""
    for n in body:
        for c in ast.walk(n):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == var):
                return True
    return False


def _registry_tables(tree) -> dict[str, set[str]]:
    """Alle Namen, die im Modul als Tuple/Liste von Funktionsnamen stehen.

    `CHECKS = (check_a, check_b)` und `CHECKS = tuple((check_a, check_b))`
    und `CHECKS = [check_a, check_b]` — der Name ist beliebig; das
    **Objekt** ist eine statische Sammlung von Namen. Ein dynamisch
    gebautes (`tuple(c for c in ...)`) landet nicht hier, und genau
    darum meldet der Aufrufer dann `blind`.
    """
    out: dict[str, set[str]] = {}
    for n in tree.body:
        if not (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)):
            continue
        name, v = n.targets[0].id, n.value
        names: set[str] = set()
        if isinstance(v, (ast.Tuple, ast.List)):
            names = {e.id for e in v.elts if isinstance(e, ast.Name)}
            if len(names) != len(v.elts):
                continue        # Ausdruecke darin: nicht statisch lesbar
        elif isinstance(v, ast.Call) and v.args:
            a = v.args[0]
            if isinstance(a, (ast.Tuple, ast.List)):
                names = {e.id for e in a.elts if isinstance(e, ast.Name)}
                if len(names) != len(a.elts):
                    continue
        if names:
            out[name] = names
    return out




# §A-MX (Runde 47): Funktionen, die `Path.cwd()` **lesen müssen**, weil
# das ihr Gegenstand ist. Keine Ausnahmen am Fund, sondern Rollen:
#   `_self_test_count_delta` prüft, ob `reset_all()` den Prozesszustand
#   `chdir` zurücksetzt — er kann nur prüfen, was er lesen kann.
#   `main` ist der **Aufrufer**: hier wird der Default gesetzt, und ein
#   Default an der obersten Stelle ist die Definition, nicht der Fehler.
_CWD_READERS = frozenset({"main", "_self_test_count_delta"})


def _gitlink_errors(root: Path | None = None) -> list[str]:
    """Ein Gitlink im Baum — deklariert oder nicht? (§A-MY, Runde 47)

    In Runde 46 kam ein Gitlink `forensik` durch `git add -A` in einen
    Commit, ohne `.gitmodules`. Der Ein-Datei-Pruefer war gruen: ein
    Gitlink ist **ein** Dateieintrag. Ein Fremd-Repo passiert ihn als
    eine Datei.

    Die naive Regel „`mode 160000` ist rot" waere an der Stelle falsch,
    an der sie zuerst greift: `lib/openzeppelin-contracts` und
    `-upgradeable` sind **deklarierte** Forge-Submodule und gehoeren in
    den Baum. Rot ist der Gitlink, den `.gitmodules` **nicht** kennt —
    und genau das passiert, wenn ein Verzeichnis mit eigenem `.git`
    versehentlich in den Index gerat.
    """
    base = root or Path(__file__).resolve().parent.parent
    r = subprocess.run(["git", "ls-files", "-s"], cwd=str(base),
                       capture_output=True, text=True)
    if r.returncode != 0:
        return []
    declared: set[str] = set()
    gm = base / ".gitmodules"
    if gm.exists():
        for line in gm.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("path") and "=" in line:
                declared.add(line.split("=", 1)[1].strip())
    out: list[str] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2 or not parts[0].startswith("160000"):
            continue
        path = parts[1]
        if path not in declared:
            out.append(f"Gitlink ohne `.gitmodules`-Eintrag: {path}")
    return out


def _self_test_gitlink() -> list[str]:
    """Wird ein **nicht deklarierter** Gitlink rot? (§A-MY)

    Die Probe baut ein temporaeres Repo mit zwei Eintraegen: ein
    deklariertes Submodul (`lib/oz`) und ein Gitlink ohne
    `.gitmodules`-Eintrag (`fremd`). Erwartet: genau **eine** Meldung,
    und sie nennt `fremd` — als Literal mit Herkunft: der Fall aus
    Runde 46 hiess `forensik`, der Probefall heisst `fremd`.
    """
    out: list[str] = []
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / ".gitmodules").write_text(
            '[submodule "oz"]\n\tpath = lib/oz\n\turl = https://example/x\n',
            encoding="utf-8")
        for cmd in (["git", "init", "-q"],):
            subprocess.run(cmd, cwd=str(t), capture_output=True)
        # Zwei Gitlinks in den Index schreiben, ohne Objekte zu brauchen
        for path, sha in (("lib/oz", "0" * 40), ("fremd", "1" * 40)):
            subprocess.run(["git", "update-index", "--add", "--cacheinfo",
                            f"160000,{sha},{path}"], cwd=str(t),
                           capture_output=True)
        got = _gitlink_errors(t)
        if len(got) != 1:
            out.append(f"Gitlink: {len(got)} Meldungen, erwartet 1")
        elif "fremd" not in got[0]:
            out.append(f"Gitlink: Meldung nennt nicht `fremd`: {got[0]}")
    return out


def block_kind(title: str, body_lines: list[str]) -> str:
    """Welche **Sorte** Block ist das? `Messung` / `Korrektur` / `Beleg` / `Text`.

    §A-ZU (Runde 54). Die Akte enthält sechs Sorten, flach, ohne Typ:
    Behauptung, falsche Zahl, Korrektur, zitiertes Zitat, alter Meßblock,
    aktueller Meßblock. Jeder Konsument erfand seine eigene Auswahlregel,
    und vier davon sind in vier Runden aufgefallen. Der Typ wird
    **abgeleitet**, nicht gespeichert — dieselbe Entscheidung wie beim
    Hash (§71.59c): ein geschriebener Typ driftet beim nächsten Kopieren.

    Ableitung, ausschließlich aus dem Text:

      `Korrektur zu §…` in der Überschrift      → `Korrektur`
      `Karte: <fp>` **und** `total=` im Rumpf   → `Messung`
      `Beleg aus §…` in der Überschrift         → `Beleg`
      sonst                                      → `Text`

    Den Beleg-Typ gibt es, weil ein alter Meßblock sonst wie ein aktueller
    aussieht: derselbe `total=`-Anfang, dieselbe `Bezug:`-Zeile, ein
    anderer Lauf. Fünf Runden lang hat der Selbsttest genau das
    verglichen (§71.45 gegen §71.54) und jeden Lauf als Befund gemeldet.
    """
    if _selector_in(title) is not None:
        return "Korrektur"
    # §A-ZV: **Fließtext ist keine Messung.** Ein Absatz, der `Karte:`
    # und `total=` *erwähnt*, sieht für einen Substring-Test aus wie ein
    # Block. Der Typ hängt darum am **eingezäunten** Inhalt: alles
    # zwischen zwei ```-Zeilen, nichts außerhalb. Dieselbe Grenze, die
    # `check_prose_fractions` schon zieht (R53).
    fenced, buf, fenced_lines = False, [], []
    for line in body_lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        (fenced_lines if fenced else buf).append(line)
    body = "\n".join(fenced_lines) if fenced_lines else ""
    if "total=" in body:
        # §A-ZU: `Karte:` ist die Provenienz. Ein Block mit `total=`, aber
        # ohne Fingerprint, stammt aus einer Zeit, in der es keine gab —
        # er ist ein **Beleg**, nie eine Messung. Diese Ableitung ist der
        # Grund, warum die alten fünf Blöcke (§71.52–§71.57) stehen
        # bleiben dürfen: sie sind typisiert, nicht gelöscht.
        return "Messung" if "Karte:" in body else "Beleg"
    if "Beleg aus" in title:
        return "Beleg"
    return "Text"


def split_blocks(text: str) -> list[dict]:
    """Die Akte als Blöcke mit Typ, Überschrift und Rumpf — **ein** Ort.

    §A-ZU: damit die Auswahl kein Sonderfall von `_akt_block_mismatch`
    bleibt, sondern eine Funktion, die jeder Prüfer benutzt. Einmal
    falsch, einmal repariert.
    """
    out: list[dict] = []
    cur = {"title": "", "lines": []}
    for line in text.splitlines():
        if line.startswith("### "):
            if cur["lines"] or cur["title"]:
                out.append(cur)
            cur = {"title": line, "lines": []}
        else:
            cur["lines"].append(line)
    out.append(cur)
    for b in out:
        b["kind"] = block_kind(b["title"], b["lines"])
    return out


def _card_fingerprint(numbers: dict[str, int], classes: list[tuple[str, int]]) -> str:
    """Der Fingerprint der **Eingaben**, die die Zahlen bestimmen.

    §A-ZU: `dirty`, Zeitstempel und Pfade gehören **nicht** hinein — ein
    Fingerprint, der sich bei jedem Lauf ändert, findet nie einen Block,
    und die Zeile wird dauerrot. Genau dieser Fehler soll nicht neu
    gebaut werden, während der alte repariert wird.
    """
    import hashlib
    import json
    payload = json.dumps({"n": sorted(numbers.items()),
                          "c": sorted(classes)}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _auswahl_fehler(bloecke: list[dict], karte: str) -> list[str]:
    """§A-ZZ: Die Auswahl **als reine Funktion** — Blöcke rein, Karte rein.

    Runde 55 hatte 0/3 Deckung und begründete das mit dem Baum. Falsch:
    die Auswahl braucht **Blöcke und eine Karte**, beides sind Werte. Daß
    `_akt_block_mismatch` sie sich selbst aus dem Baum holt, war die
    versteckte Abhängigkeit — nicht die Untestbarkeit.

    Reihenfolge, in dieser Ordnung: Fingerprint (hier: die Karte ist
    gegeben) → Klasse `Messung` → Dateireihenfolge (nach der
    Klassifikation gültig, weil append-only).
    """
    m = re.search(r"^Karte: (\w+)", karte, re.M)
    if not m:
        return ["Akte-Block: Kalibrierkarte traegt keinen Fingerprint"]
    fp = m.group(1)
    treffer = [b for b in bloecke
               if b["kind"] == "Messung"
               and f"Karte: {fp}" in "\n".join(b["lines"])]
    if not treffer:
        return [f"Akte-Block: keine Messung zur Karte {fp} — nicht gemessen"]
    # §A-ZX (Runde 55): **Der Fehlerzustand ist die Uneinigkeit, nicht die
    # Anzahl.** Runde 54 hat „mehr als 1 = Fehler" geschrieben, um den
    # stillen `[-1]`-Griff zu verhindern — und damit zwei verschiedene
    # Dinge verwechselt:
    #
    #   doppelte Behauptung — zwei Blöcke sagen **Verschiedenes** über
    #                         dieselben Eingaben: echter Fehler
    #   Wiederholung        — zwei Blöcke sagen **dasselbe**: Beweis für
    #                         Kontinuität, nichts aufzulösen
    #
    # Dateireihenfolge ist **innerhalb** einer Klasse gültig: append-only
    # garantiert, dass weiter unten später geschrieben wurde. Über Klassen
    # hinweg war sie der Fehler der Runden bis §A-ZU.
    if not _falte_gruen(treffer):
        return [f"Akte-Block: {len(treffer)} Messungen zur Karte {fp} mit verschiedenen Werten — Fingerprint unterspezifiziert oder Handedit"]    # Der Rumpf ist der Blocktext ohne Zäune; `Karte:` gehört zur
    # Provenienz und wird vom Vergleich nicht gelesen.
    # §A-ZV: der Rumpf enthält Prosa **und** den eingezäunten Block. Der
    # Vergleich liest nur den Block — Prosa ist kein Beleg.
    body = "\n".join(treffer[-1]["lines"])
    zaeune = body.split("```")
    body = zaeune[1] if len(zaeune) >= 3 else ""
    body = "\n".join(l for l in body.splitlines()
                     if not re.match(r"^Karte: \w+$", l.strip())).strip()
    return _compare_block(body, karte)


def _akt_block_mismatch(root: Path | None = None,
                        card_root: Path | None = None,
                        *,
                        bloecke: list[dict] | None = None,
                        karte: str | None = None) -> list[str]:
    """Stimmt der zitierte Block in der Akte mit `calibration_card()`? (§A-MZ)

    Die `Bezug:`-Zeile macht den Block **nachpruefbar** — sie macht ihn
    nicht **geprueft**. Zwischen Ausgabe und Akte liegt ein Kopiervorgang
    von Hand; in Runde 45 hat ihn niemand nachgerechnet, und eine Zahl
    verschwand.

    Der Schritt, den diese Akte fuer jede andere Zahl schon gemacht hat:
    nicht zitieren, sondern **vergleichen**. Gelesen wird der laengste
    eingezogene Codeblock der Akte, der mit `total=` beginnt; verglichen
    werden die **Zahlen** und die `Bezug`-Felder `root` und
    `CLAUDE.md sha256`. Der Baum-Hash **nicht** — der Block ist
    committet, der Vergleich laeuft im naechsten Commit, und ein
    `+dirty` waere kein Fehler, sondern der Zustand.
    """
    if karte is not None or bloecke is not None:
        # §A-ZZ: reiner Pfad — kein Baum, keine Datei. Beides muß kommen,
        # sonst ist die Hälfte injiziert und die andere geraten.
        if karte is None or bloecke is None:
            return ["Akte-Auswahl: karte und bloecke nur gemeinsam oder "
                    "gar nicht injizierbar"]
        return _auswahl_fehler(bloecke, karte)
    base = root or Path(__file__).resolve().parent.parent
    doc_path = base / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md"
    if not doc_path.exists():
        return []
    text = doc_path.read_text(encoding="utf-8")
    # §A-ZU (Runde 54): **Position ist keine Identität.** `[-1]` ist eine
    # Ordinalzahl; der gemeinte Block ist nicht der letzte, sondern der,
    # der *diese* Messung ist. Fünf Runden lang hat der Selbsttest den
    # Beleg aus §71.45 gegen den Lauf aus §71.54 verglichen und das jeden
    # Lauf als Befund gemeldet — dauerrot ist so aussagelos wie
    # dauergrün.
    #
    # §A-ZW (Runde 54, Selbstfund): `calibration_card` will einen `root`
    # und bekam keinen — dieselbe Zeile wie `if root is not None` aus
    # Runde 49. Der Selbsttest prüft das seitdem bei **jedem** Prüfer,
    # und das ist der Grund, warum er es hier gefunden hat und nicht ich.
    #
    # §A-ZZ (Runde 56): **die Auswahl ist eine reine Funktion.** Sie
    # steht als `_auswahl_fehler(bloecke, karte)` daneben und wird hier
    # nur gefüttert. Der Baum liefert die Eingaben, er entscheidet nicht.
    return _auswahl_fehler(split_blocks(text), calibration_card(root))


def _kopfzeile_errors(root: Path | None = None) -> list[str]:
    """§A-ZZZZ0 (Runde 57): Die Kopfzeile wird **gegen den Block gerechnet**.

    Runde 56 hat „Akte grün" durch `ops/KOPFZEILE.md` ersetzt — ein
    Dokument, das eine Regel beschreibt. Ein Dokument kann nicht falsch
    sein, deshalb kann es nicht gefunden werden. Und es trug zwei Werte
    für dasselbe Feld, weil es von Hand geschrieben war.

    Diese Funktion rechnet: das Format aus `KOPFZEILE.md` wird gegen den
    **letzten Messblock** der Akte geprüft. Drei Zahlen, und jede muß aus
    dem Block stammen, nicht aus dem Bericht.
    """
    base = root or Path(__file__).resolve().parent.parent
    kopf = base / "order_execution_engine" / "ops" / "KOPFZEILE.md"
    doc = base / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md"
    if not kopf.exists() or not doc.exists():
        return []
    out: list[str] = []
    fmt = kopf.read_text(encoding="utf-8")
    # Das Format muß die drei Felder **namentlich** tragen — sonst ist es
    # kein Format, sondern ein Satz.
    for feld in ("gemessen", "unvollständig", "keine"):
        if f"<{feld}" not in fmt and f" {feld} ·" not in fmt:
            out.append(f"Kopfzeile: Format nennt `{feld}` nicht")
    text = doc.read_text(encoding="utf-8")
    ms = [b for b in split_blocks(text) if b["kind"] == "Messung"]
    if not ms:
        return out + ["Kopfzeile: kein Messblock — keine Zahl zu prüfen"]
    # Der **letzte** Messblock ist die aktuelle Messung (append-only).
    body = "\n".join(ms[-1]["lines"])
    if "gemessen ·" not in body:
        out.append("Kopfzeile: letzter Messblock traegt keine Kopfzeile")
        return out
    k = re.search(r"(\d+) gemessen · (\d+) nicht gemessen[^\n]*", body)
    if not k:
        return out + ["Kopfzeile: Kopfzeilenform nicht lesbar"]
    zeile = k.group(0)
    n_gemessen, n_offen = int(k.group(1)), int(k.group(2))
    # Die dritte Zahl: `keine` heißt, die Faltung hat `raise` geworfen.
    # Im Block ist sie **nicht** ablesbar — sie kommt aus dem Lauf, nicht
    # aus dem Text. Darum prüft diese Stelle nur, was der Block weiß:
    # `nicht gemessen > 0` **muß** als unvollstaendig benannt sein.
    if n_offen and "unvollstaendig" not in zeile:
        out.append(f"Kopfzeile: {n_offen} nicht gemessen, aber nicht "
                   f"als unvollstaendig benannt — die Zeile sagt "
                   f"vollstaendig, die Zahl sagt es nicht")
    # §A-ZZZZ0b: die Kopfzeile muß den **Umfang** nennen, nicht nur die
    # Zahl. `8 gemessen` ohne `von N` ist mit `8 von 8` und `8 von 9`
    # verträglich — eine Zahl, die zwei Zustände deckt.
    if not re.search(r"\d+ gemessen · \d+ nicht gemessen", zeile):
        out.append("Kopfzeile: Feldform `N gemessen · U nicht gemessen` fehlt")
    # Die Prüfer-Fassung muß die des Laufs sein, der den Block schrieb.
    # Nur in der **Kopfzeile**, nicht im Rumpf: „Prüfer kennt …" in Prosa
    # ist eine Aussage über Prüfer, nicht die Kopfzeile.
    ph = re.search(r"Prüfer (\w{8,})", zeile)
    if ph and ph.group(1) != _pruefer_hash():
        # Kein Fehler: der Block ist committet, der Prüfer läuft weiter.
        # Aber der **Abstand** gehört benannt, sonst sieht der Leser eine
        # Zahl, die zu einem anderen Programm gehört.
        out.append(f"Kopfzeile: Prüfer {ph.group(1)} im Block, "
                   f"{_pruefer_hash()} heute — Block ist Vorzustand")
    return out


def _tally_line_of(root: Path | None = None) -> str:
    """Die Kopfzeile des echten Laufs — drei Zahlen, keine Fußnote (§A-NM)."""
    return tally_line(measurement_tally(None, [], measured=False))


def _require_int_tally(tally: dict[str, object], where: str) -> list[str]:
    """Verlangt, dass `abweichungen` eine ganze Zahl ist — oder `None` (§A-NM).

    Der Vertrag aus §71.56: eine Akte, die eine Zahl zitiert, verlangt eine
    Zahl. Kommt `None`, ist der Lauf kein Messlauf — und der Zitierende muß
    das als **Fehler** sehen, nicht als `0` lesen. Ein `bool` ist keine Zahl
    (`isinstance(True, int)` ist wahr, aber `True` ist keine Messung).
    """
    aw = tally.get("abweichungen")
    if aw is None:
        return [f"{where}: abweichungen ist None — kein Messlauf, "
                "keine Zahl zitierbar"]
    if not isinstance(aw, int) or isinstance(aw, bool) or aw < 0:
        return [f"{where}: abweichungen={aw!r} ist keine ganze Zahl >= 0"]
    for k in ("nicht_gemessen", "ohne_skript"):
        v = tally.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            return [f"{where}: {k}={v!r} ist keine ganze Zahl >= 0"]
    return []


def _compare_block(cited: str, card: str) -> list[str]:
    out: list[str] = []
    want, got = card.splitlines(), cited.splitlines()
    # Kopfzeile: jede `k=v`-Zahl muss gleich sein
    def kv(line: str) -> dict[str, str]:
        return {p.split("=", 1)[0]: p.split("=", 1)[1]
                for p in line.split() if "=" in p}
    if not want or not got:
        return ["Akte-Block: leer"]
    w, g = kv(want[0]), kv(got[0])
    for key in ("total", "chain_total", "reported", "unclassified",
                "unchecked", "unclassified_checkers"):
        if w.get(key) != g.get(key):
            out.append(f"Akte-Block: {key} {g.get(key)} zitiert, "
                       f"{w.get(key)} gemessen")
    # Bezug-Zeile: root und sha256
    def bezug(lines: list[str]) -> dict[str, str]:
        for ln in lines:
            if ln.startswith("Bezug:"):
                res = {}
                for part in ln[len("Bezug:"):].split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        res[k.strip()] = v.strip()
                    elif ":" in part:
                        k, v = part.split(":", 1)
                        res[k.strip()] = v.strip()
                return res
        return {}
    wb, gb = bezug(want), bezug(got)
    for key in ("root", "CLAUDE.md sha256"):
        if wb.get(key) != gb.get(key):
            out.append(f"Akte-Block: Bezug `{key}` {gb.get(key)} zitiert, "
                       f"{wb.get(key)} gemessen")
    return out


def _self_test_akt_block() -> list[str]:
    """Wird ein **abweichender** Block rot? (§A-MZ)

    Zwei Erwartungen, beide noetig:

      A. Der Block in der Akte **stimmt** heute. Ohne sie prueft der Test
         nur, dass eine falsche Zahl falsch ist — aber nicht, dass die
         committete Zahl gemessen wurde.
      B. Eine veraenderte Zahl wird **erkannt**, und die Meldung nennt
         sie. Das ist der Fall der letzten Runde: der committete
         Block schloss anders als der gemessene, und niemand hat
         nachgesehen.

    Verglichen wird `_compare_block(cited, card)` — der Vergleich ist
    von der Messung getrennt, damit er gegen jeden Text laeuft.
    """
    out: list[str] = []
    if _akt_block_mismatch():
        out.append("Akte-Block: der committete Block weicht heute vom "
                   "Messlauf ab")
    card = calibration_card()
    bad = re.sub(r"total=\d+", "total=999", card, count=1)
    got = _compare_block(bad, card)
    if not got:
        out.append("Akte-Block: veraenderte Zahl wird nicht erkannt")
    elif not any("total" in g for g in got):
        out.append(f"Akte-Block: Meldung nennt `total` nicht: {got}")
    # Und die Gegenprobe: ein Block ohne Veraenderung ist gruen.
    if _compare_block(card, card):
        out.append("Akte-Block: identischer Block wird als abweichend "
                   "gemeldet")
    return out


def _self_test_tally_numbers() -> list[str]:
    """Trägt die Kopfzeile drei Zahlen — und keine Fußnote? (§A-NM)

    Der Fehlschlag der letzten Runde: `0 Abweichungen (kein .git/ — keine
    Differenzmessung) · 12 ohne Skript`. Drei Einschränkungen, eine Null,
    die wie eine Summe aussieht. Fünf Behauptungen:

      A. Ohne Differenzmessung ist `abweichungen` **None**, nie 0.
      B. Die Tally rendert `unvollstaendig`, nicht `0 gemessen`.
      C. `ohne_skript` steht als **eigene** Zahl, nicht in Klammern.
      D. Ein Messlauf mit Abweichungen nennt sie als ganze Zahl.
      E. `_require_int_tally` lehnt `None`, `bool` und negative Werte ab.
    """
    out: list[str] = []
    blind = measurement_tally(None, ["a", "b"], measured=False,
                              ohne_skript=["c"])
    if blind["abweichungen"] is not None:
        out.append(f"Tally: ohne Messung gibt abweichungen={blind['abweichungen']!r} "
                   "statt None")
    # §A-NM: `nicht_gemessen` = 2 Pruefer + 1 fehlende Differenz; die
    # Zusage ohne Skript ist **eine eigene** Zahl und zaehlt hier nicht mit.
    if blind["nicht_gemessen"] != 3:
        out.append(f"Tally: nicht_gemessen={blind['nicht_gemessen']} "
                   "statt 3 (2 unmessured + 1 Differenz)")
    if blind["ohne_skript"] != 1:
        out.append(f"Tally: ohne_skript={blind['ohne_skript']} statt 1")
    rendered = tally_line(measurement_tally(None, ["a", "b"], measured=False,
                                            ohne_skript=["c"], umfang=9))
    # §A-NV: die erste Zahl ist der **Umfang minus nicht gemessen**, nicht
    # ein Zustandswort. `unvollstaendig` ist die Ableitung und steht hinten.
    if not rendered.startswith("6 gemessen · 3 nicht gemessen · 1 ohne Skript"):
        out.append(f"Tally: Rendering {rendered!r} beginnt nicht mit "
                   "`6 gemessen · 3 nicht gemessen · 1 ohne Skript`")
    if "unvollstaendig" not in rendered:
        out.append(f"Tally: Rendering {rendered!r} nennt den Mangel nicht")
    if "0 gemessen" in rendered:
        out.append("Tally: Rendering enthält `0 gemessen` — die Footnote "
                   "ist zurück")
    ok = measurement_tally(0, [], measured=True, umfang=7)
    if ok["abweichungen"] != 0:
        out.append(f"Tally: Messlauf gibt {ok['abweichungen']!r} statt 0")
    if not tally_line(ok).startswith("7 gemessen · 0 nicht gemessen"):
        out.append(f"Tally: Messlauf rendert {tally_line(ok)!r}")
    # E: der Vertrag, an dem die Akte scheitern soll
    for bad, why in ((None, "None"), (True, "bool"), (-1, "negativ"),
                     ("0", "str")):
        if not _require_int_tally({"abweichungen": bad,
                                   "nicht_gemessen": 0,
                                   "ohne_skript": 0}, "Probe"):
            out.append(f"Tally: _require_int_tally akzeptiert {why}")
    if _require_int_tally(ok, "Probe"):
        out.append("Tally: _require_int_tally lehnt den Messlauf ab")
    return out


def _self_test_wirkung() -> list[str]:
    """Meldet jeder Pruefer, wenn ein Fehler da ist? (§A-NK, Runde 49)

    Die vierte Stufe. `unchecked` sieht die **Registrierung**,
    `unclassified` das **Auftauchen** im Kalibrierlauf. Beide sind blind
    fuer den Fall, dass ein Pruefer laeuft und nichts findet. Diese Stufe
    zaehlt die Wirkung: je Pruefer ein Fixture mit Fehler und eines ohne.
    Meldet er in beiden gleich, ist er wirkungslos — und das ist eine Zahl.

    Die Fixtures liegen in `check_fixtures` (eigene Rolle, eigener Ort),
    nicht als Kommentar im Produktionscode. Fehlt das Modul, ist das
    **rot**, nicht still: ein Pruefer ohne Gegenprobe ist eine Behauptung.
    """
    out: list[str] = []
    try:
        import check_fixtures
    except ImportError:
        return ["Wirkung: `check_fixtures` fehlt — kein Pruefer hat eine "
                "Gegenprobe"]
    measured = check_fixtures.measure()
    declared = set(check_fixtures.FIXTURES)
    # Jeder registrierte Pruefer braucht ein Paar — die Liste steht in
    # `check_fixtures`, nicht hier. Ein Pruefer ohne Fixture ist eine
    # Zahl ohne Wirkung; er wird nicht stillschweigend ausgelassen.
    if len(declared) < 7:
        out.append(f"Wirkung: nur {len(declared)} Fixtures deklariert "
                   f"(erwartet 7)")
    for name, (bad, clean) in measured.items():
        if bad < 0:
            out.append(f"Wirkung: Fixture fuer {name} laeuft nicht")
            continue
        # §A-NL (Runde 50): die Zusicherung `kaputt != heil` ist eigenes
        # Praedikat, nicht `bad <= clean` an Ort und Stelle. Der Grund
        # nennt den **Baum**, der nachgezogen werden muss.
        why = check_fixtures.carries_case(bad, clean)
        if why == "fixture_clean_red":
            out.append(f"Wirkung: heiler Baum von {name} ist rot "
                       f"({bad} vs {clean})")
        elif why == "fixture_broken_green":
            out.append(f"Wirkung: kaputter Baum von {name} ist nicht "
                       f"kaputt ({bad} vs {clean})")
    return out


def _self_test_anchor_uniqueness() -> list[str]:
    """Paßt jeder Selbsttest-Anker **genau einmal**? (§A-NL, Runde 50)

    Vier Anker scheiterten in Runde 49, jeder vom Selbsttest gefunden —
    aber der fuenfte waere der gewesen, den `replace(..., 1)` geschluckt
    haette: er trifft den **ersten** von mehreren und meldet Erfolg.
    `n=1` ist keine Zusicherung, sondern eine Ausrede.

    Gemessen wird hier die **Regel**, nicht ihre Anwendung: jedes
    `str.replace(a, b, 1)` in dieser Datei traegt einen stillen
    Mehrfachtreffer. Wo ein Anker mehrfach passen **darf**, steht das
    als bewusste Ausnahme mit Namen da (`_ANCHOR_REPEAT_OK`).
    """
    failures: list[str] = []
    src = Path(__file__).read_text(encoding="utf-8")
    for lineno, anchor, count in _anchor_report(src):
        failures.append(
            f"@L{lineno}: replace-Anker paßt {count}x, nicht 1x: {anchor!r}")
    # Falsifikation der Regel selbst — 0, 1 und 2 **Fundstellen**.
    # Die Proben sind echte Code-Zeilen, die den Anker enthalten; eine
    # `a = "…"`-Zeile waere keine Fundstelle, sondern ein Wert.
    anchor = "check_counts(text, w, p, rep, root)"
    # §A-NL: drei Faelle, jeder mit **gezaehlter** Zahl.
    # `len(report)` ist die Messung; die Erwartung ist `0`/`1`/`2` und
    # steht als Variable, nicht als Literal-Vergleich im `if`.
    zero, one, two = 0, 1, 2
    # 0 Paßstellen: der Anker des Aufrufs ist ein **anderer**.
    probe0 = "x.replace('ein-ganz-anderer-anker', 'b', 1)\n"
    probe1 = f"x.replace('{anchor}', 'b', 1)\n"
    probe2 = (f"x.replace('{anchor}', 'b', 1)\n"
              f"y.replace('{anchor}', 'b', 1)\n")
    for src, erwartet in ((probe0, zero), (probe1, zero), (probe2, two)):
        n_found = len(_anchor_report(src))
        if (n_found > zero) != (erwartet > zero):
            failures.append(
                f"Anker-Pruefer: {n_found} Befunde bei erwartet {erwartet}")
    # §A-NL: der Anker-Pruefer zaehlt **ohne** die zitierende Zeile —
    # sonst meldet er die eigene Fundstelle mit.
    if _anchor_report(f"x.replace('{anchor}', 'b', 1)\n# {anchor}\n"):
        failures.append("Anker-Pruefer zaehlt die zitierende Zeile mit")
    # Und ohne die Definitionszeile: `_anchor = "<anker>"` ist ein Wert,
    # keine Fundstelle.
    if _anchor_report(f'_anchor = "{anchor}"\nx.replace("{anchor}", "b", 1)\n'):
        failures.append("Anker-Pruefer zaehlt die Definitionszeile mit")
    # Mehrzeilig: die Zeilenschleife allein sieht ihn nicht.
    multi = ("    check_line_counts(text, root, rep)\n"
             "    check_dead_refs(text, root, rep)")
    esc = multi.replace("\n", "\\n")
    if _anchor_report(f'x.replace("{esc}", "b", 1)\n'):
        failures.append("Anker-Pruefer meldet einen eindeutigen Anker (multi)")
    if not _anchor_report(f'x.replace("{esc}", "b", 1)\n'
                          f'y.replace("{esc}", "b", 1)\n'):
        failures.append("Anker-Pruefer zaehlt mehrzeilig nicht")
    return failures


def _anchor_count(src: str, anchor: str) -> int:
    """Paßstellen eines Ankers **ohne Zitate** (§A-NL, Runde 50).

    Eine Zeile, die den Anker als **Literal** traegt — die
    `_anchor = "…"`-Definition oder ein Kommentar, der ihn zitiert —
    ist keine Fundstelle im adressierten Text. Sie mitzuzaehlen machte
    aus einem eindeutigen Anker einen Mehrfachtreffer und umgekehrt.

    Gemessen wird **ohne** die Zeilen, die den Anker selbst tragen —
    definieren oder zitieren. Nicht per Namenskonvention (`_anchor =`),
    sondern per **Form**: eine Zeile, deren einziges Vorkommen des
    Ankers ein String-Literal ist und die ihn keiner Funktion uebergibt,
    ist keine Fundstelle. Ein `if <anker>:` zaehlt; ein `x = "<anker>"`
    nicht; ein `x.replace("<anker>", ...)` schon.
    """
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    quote_lines: set[int] = set()
    if tree is not None:
        for k in ast.walk(tree):
            # Zuweisung eines reinen String-Literals
            if isinstance(k, ast.Assign) and len(k.targets) == 1:
                v = k.value
                if (isinstance(v, ast.Constant)
                        and isinstance(v.value, str)
                        and v.value == anchor):
                    quote_lines.add(k.lineno)
    n = 0
    for i, ln in enumerate(src.splitlines(), 1):
        if anchor not in ln:
            continue
        if ln.lstrip().startswith("#") or i in quote_lines:
            continue
        n += 1
    # Mehrzeilige Anker: die Zeilenschleife sieht sie nicht. Ein Anker
    # mit echtem Newline steht im Quelltext **real** — und ein
    # Fixture-Literal traegt ihn **escaped**. Beides ist derselbe Anker;
    # gezaehlt wird das Maximum der beiden Formen, nicht eine davon.
    if "\n" in anchor:
        esc = anchor.replace("\n", "\\n")
        stripped = "\n".join(ln for ln in src.splitlines()
                             if not ln.lstrip().startswith("#"))
        return max(stripped.count(anchor), stripped.count(esc))
    return n


def _anchor_report(src: str) -> list[str]:
    """`[(lineno, anker, count)]` fuer `replace(..., 1)`-Anker mit `count != 1`.

    §A-NL (Runde 50): gezaehlt wird **ohne die zitierende Zeile**. Ein
    Anker, der im eigenen Selbsttest als Literal steht, paßt sonst
    immer mindestens einmal zu viel — und der Pruefer meldete seine
    eigene Fundstelle als Mehrfachtreffer.
    """
    import ast
    out: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [("?", "?", "?")]
    lines = src.splitlines()
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "replace"
                and len(n.args) == 3):
            continue
        third = n.args[2]
        anchor = n.args[0]
        if not (isinstance(third, ast.Constant) and third.value == 1):
            continue
        if not (isinstance(anchor, ast.Constant)
                and isinstance(anchor.value, str)):
            continue
        c = _anchor_count(src, anchor.value)
        if c != 1:
            out.append((n.lineno, anchor.value, c))
    return out


def _self_test_reader_calls() -> list[str]:
    """Findet der Pruefer den **Aufruf** ohne `root`? (§A-NE)

    Die Buchung gegen die eigene Fehldiagnose der letzten Runde: der
    Fehler von Runde 44 war der Aufruf, nicht die Signatur. Vier Faelle:

      Leser + Aufruf ohne `root`          -> rot (1)
      Leser + Aufruf mit `root`           -> still
      Nicht-Leser + Aufruf ohne `root`    -> still (er *braucht* es nicht)
      Aufruf mit `§A-KR-ANCHOR`           -> still (Negativtest)
    """
    probe = (
        "def load_thing(root=None):\n"
        "    return (root / 'x').read_text()\n"
        "def not_a_reader(root=None):\n"
        "    return 1\n"
        "def caller():\n"
        "    load_thing()\n"
        "    load_thing(Path('/tmp'))\n"
        "    not_a_reader()\n"
        "    load_thing()\n"
    )
    got = _reader_calls_without_root(probe)
    out: list[str] = []
    # §A-NI (Runde 49): zwei Aufrufe ohne `root` stehen im Fixture, nicht
    # einer — die Erwartung war eine Zaehlung, die nie stimmte. Jetzt eine
    # Mengenaussage: **beide** Stellen sind gemeldet, die mit `Path`
    # nicht, der Nicht-Leser nicht.
    if sorted(got) != [
            "load_thing(...) @L6: Leser ohne `root` gerufen — "
            "Leseort ist der Default",
            "load_thing(...) @L9: Leser ohne `root` gerufen — "
            "Leseort ist der Default"]:
        out.append(f"Leser-Aufruf: {got} statt der beiden Stellen L6/L9")
    # Und die eigene Datei: keine Leser-Aufrufe ohne root.
    mine = _reader_calls_without_root()
    if mine:
        out.append(f"Leser-Aufruf: {len(mine)} im eigenen Baum — "
                   f"{mine[0]}")
    return out


def _self_test_cwd_readers(src: str | None = None) -> list[str]:
    """Ist jeder Eintrag in `_CWD_READERS` lebendig? (§A-ND, Runde 48)

    Eine Deklaration auf Funktionsebene ist reviewbar — aber ein Eintrag,
    dessen Funktion verschwindet, bleibt stehen. Wird `_snapshot_path`
    geloescht, ist die Liste um einen toten Eintrag laenger und der Test
    gruen. **Die Liste kann nur wachsen, nie schrumpfen** — dieselbe
    Einbahnstrasse wie eine Baseline.

    Zwei Zusicherungen, beide noetig:

      a) jeder Eintrag existiert im Modul,
      b) jeder Eintrag liest tatsaechlich `cwd`.

    (b) faengt den zweiten toten Fall: eine Funktion, die bleibt, aber
    `cwd` nicht mehr liest. Dann ist der Eintrag eine Ausnahme ohne
    Gegenstand — und Ausnahmen ohne Gegenstand wachsen.
    """
    import ast
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    defined = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    out: list[str] = []
    for name in sorted(_CWD_READERS):
        fn = defined.get(name)
        if fn is None:
            out.append(f"_CWD_READERS: `{name}` existiert nicht im Modul "
                       f"— toter Eintrag")
            continue
        reads = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "cwd"
            for n in ast.walk(fn))
        if not reads:
            out.append(f"_CWD_READERS: `{name}` liest kein `cwd` — "
                       f"Ausnahme ohne Gegenstand")
    return out


def _reader_calls_without_root(src: str | None = None) -> list[str]:
    """Wird ein *Leser* ohne `root` gerufen? (§A-NE, Runde 48)

    **Diese Buchung korrigiert eine eigene Fehldiagnose.** §71.53 hat
    `root=None` als „die Signatur des Fehlers" bezeichnet und eine Regel
    darauf gebaut. Nachgemessen ist `check_counts` kein Fall: sein
    `root=None` ist fort, der Fehler der Runde 44 war der **Aufruf**
    `check_counts(doc, waves, per, rep)` ohne `root` — und den haette
    `_git_callers_without_cwd` gefunden, wenn er nicht nur `git`-Aufrufe
    pruefte.

    Der Pruefer fuer die Signaturen existiert (`_default_root_errors`).
    Der Pruefer fuer die **Aufrufe** fehlte. Er fragt:

      eine Funktion in diesem Modul, die einen Ortsparameter hat
      (`root`, `doc_root`, `repo`), hat einen Default `None`, und wird
      an einer Stelle **ohne** diesen Parameter gerufen — wobei der Ort
      im Rumpf tatsaechlich gebraucht wird (Lesen, `open`, `glob`,
      `subprocess`-`cwd`).

    Der letzte Halbsatz ist die Lehre aus `_snapshot_path`: eine
    Funktion, die `root` annimmt und **nicht braucht**, ist kein Leser,
    und ihr Aufruf ohne `root` ist kein Fehler.
    """
    import ast
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    readers: dict[str, tuple[int, bool]] = {}   # name -> (pos, hat_default)
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef):
            continue
        args = n.args.args
        names = [a.arg for a in args]
        pos = None
        for want in ("root", "doc_root", "repo"):
            if want in names:
                pos = names.index(want)
                break
        if pos is None or n.name in _NOT_CHECKERS:
            continue
        if not _uses_root_as_path(n, names[pos]):
            continue        # nimmt root an, braucht es nicht
        ndef = len(n.args.defaults)
        has_default = pos >= len(args) - ndef
        readers[n.name] = (pos, has_default)

    out: list[str] = []
    lines = text.splitlines()
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
            continue
        if n.func.id not in readers:
            continue
        pos, has_default = readers[n.func.id]
        if not has_default:
            continue        # Pflichtparameter: der Aufruf muss ihn liefern
        given = len(n.args) + sum(1 for k in n.keywords if k.arg)
        if given <= pos:
            # §A-NE: ein Aufruf, der **selbst deklariert**, dass er den
            # Default pruefen soll, ist der Test — nicht der Fehler. Die
            # Deklaration steht in derselben Zeile wie der Aufruf, und
            # sie ist damit reviewbar am Fund, nicht am Pruefer.
            src_line = lines[n.lineno - 1] if n.lineno <= len(lines) else ""
            if _KR_ANCHOR in src_line:
                continue
            # §A-NI (Runde 49): die Rolle statt des Markers. Ein Aufruf in
            # einem **Selbsttest** prueft den Default-Zweig; der Fund ist
            # dort das Ziel. Dieselbe Bewegung wie bei `_CWD_READERS`:
            # von zehn Markern im Code auf eine Regel.
            if _in_self_test(n.lineno, tree):
                continue
            out.append(f"{n.func.id}(...) @L{n.lineno}: Leser ohne "
                       f"`root` gerufen — Leseort ist der Default")
    return out


def _in_self_test(lineno: int, tree) -> bool:
    """Liegt `lineno` in einer Funktion mit `_self_test`-Praefix?"""
    import ast as _a
    for fn in tree.body:
        if not isinstance(fn, _a.FunctionDef):
            continue
        if not fn.name.startswith(("_self_test", "self_test")):
            continue
        end = getattr(fn, "end_lineno", fn.lineno) or fn.lineno
        if fn.lineno <= lineno <= end:
            return True
    return False


# §A-NE: Markierung fuer einen Aufruf, der den Default **absichtlich**
# prueft. Dieselbe Form wie ein Negativtest: der Fund ist das Ziel.
_KR_ANCHOR = "§A-KR-ANCHOR"


def _uses_root_as_path(fn: ast.AST, name: str) -> bool:
    """Wird `name` zu einem Pfad oder an einen Pfadzugriff gegeben?"""
    import ast
    for n in ast.walk(fn):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
            for side in (n.left, n.right):
                if isinstance(side, ast.Name) and side.id == name:
                    return True
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id in ("Path", "open") and n.args:
                if isinstance(n.args[0], ast.Name) and n.args[0].id == name:
                    return True
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr in ("glob", "rglob", "read_text", "exists",
                               "is_dir", "resolve"):
                if isinstance(n.func.value, ast.Name) and n.func.value.id == name:
                    return True
            if n.func.attr == "run":
                for k in n.keywords:
                    if k.arg == "cwd" and isinstance(k.value, ast.Name) \
                            and k.value.id == name:
                        return True
    return False


def _akte_blocks(text: str) -> set[str]:
    """Identitaet jedes Rundenblocks — `§71.NN`, nicht seine Position.

    §A-NG (Runde 49): `count(Bezug) >= count_prev(Bezug)` vergleicht
    **Groessen**. Ein Tausch — ein Block geloescht, ein anderer
    hinzugefuegt — bleibt bei gleicher Zahl und ist gruen. Verlustfreiheit
    ist Mengeninklusion, und die braucht eine Identitaet. Sie steht schon
    in der Datei: jede Runde beginnt mit einem Paragraphentitel.
    """
    return set(re.findall(r"^### (§71\.\d+) — ", text, re.M))


def _akte_block_bodies(text: str) -> dict[str, str]:
    """`{§71.NN: Blocktext}` — der Koerper, nicht nur die Ueberschrift."""
    parts = re.split(r"^### (§71\.\d+) — .*$", text, flags=re.M)
    out: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i]] = parts[i + 1]
    return out


def _block_hash(body: str) -> str:
    """Kurzhash eines Blockkoerpers — die zweite Haelfte der Identitaet."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def _akte_block_identity(text: str) -> dict[str, str]:
    """`{§71.NN: hash}` — Blockidentitaet als `(§, Hash)` (§A-NL, Runde 50).

    Der Schluessel `§` allein traegt nicht: ein Block mit anderem Inhalt
    ist **kein** verlorener Block, sondern ein veraenderter — und darueber
    hat §2 (Berichtigung als eigener Block) schon entschieden. Was hier
    gemessen wird, ist etwas anderes: Zeilenverlust **innerhalb** eines
    Blocks. Zwei geloescht, zwei hinzugefuegt ist auf Zeilenzahl-Ebene
    gruen und auf Inhaltsebene nicht.
    """
    return {k: _block_hash(v) for k, v in _akte_block_bodies(text).items()}


def _akte_losslessness(root: Path | None = None) -> list[str]:
    """Verliert die Akte **einen Block** gegenueber dem Vorgaenger-Commit?

    §A-NF (Runde 48) verglich Groessen: `Bezug`-Zeilen, Zeilen,
    `total=`-Bloecke monoton. §A-NG (Runde 49): das ist Nettoverlust —
    ein Tausch geht als Verlustfreiheit durch, und wer in Runde 50 die
    Akte liest, erfaehrt nicht, **welche** Runde fehlt.

    Jetzt Mengeninklusion ueber die Identitaet der Ueberschrift:

        bloecke(heute)  ⊇  bloecke(HEAD)

    Meldung nennt die **fehlende Runde**, nicht die Differenz zweier
    Zahlen.

    **Nebenwirkung, gewollt:** wer einen Block **berichtigt**, wird rot —
    ausser er fuehrt die Berichtigung als eigenen Block (`§71.53a`).
    Das ist die Entscheidung: die Akte waechst monoton, oder sie
    erzaehlt. Die Groessenpruefung bleibt daneben stehen: eine geloeschte
    Zeile in einem Block, die keinen Blockverlust erzeugt, faellt sonst
    durch.
    """
    base = root or Path(__file__).resolve().parent.parent
    rel = "order_execution_engine/ops/TAG7_ABNAHME.md"
    cur = base / rel
    if not cur.exists():
        return []
    now = cur.read_text(encoding="utf-8")
    # §A-NX (Runde 52): der Vergleich lief gegen `HEAD~1` — und das ist
    # genau der Fehler, den diese Pruefung finden soll. `HEAD~1` ist der
    # Stand **vor** dem letzten Commit; der letzte committete Stand, gegen
    # den der Arbeitsbaum verlieren kann, ist **`HEAD`**. Mit `HEAD~1`
    # wurde gestern gegen vorgestern gemessen, und der Commit, in dem der
    # Verlust steckt, war fuer immer unsichtbar.
    #
    # Das Fenster **innerhalb** des Arbeitsbaums (schreiben, noch nicht
    # committen) schliesst `scripts/akte_guard.py` — und hier im Prozess
    # der Abgleich gegen `HEAD`, der in dieses Fenster hineinsieht.
    prev = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(base),
                          capture_output=True, text=True)
    if prev.returncode != 0:
        return []       # erster Commit der Datei: nichts zu vergleichen
    old = prev.stdout
    out: list[str] = []
    gone = _akte_blocks(old) - _akte_blocks(now)
    for block in sorted(gone):
        out.append(f"Akte: Block {block} fehlt — Runde verloren")
    # §A-NL (Runde 50): Zeilenverlust **innerhalb** eines Blocks. Die
    # Mengenpruefung sieht nur ganze Bloecke; die Groessen darunter sehen
    # nur Netto. Zwei geloescht und zwei hinzugefuegt ist in beiden gruen.
    # `(§, Hash)` macht daraus benennbar, **welcher** Block sich bewegte.
    now_id, old_id = _akte_block_identity(now), _akte_block_identity(old)
    for sec in sorted(set(old_id) & set(now_id)):
        if old_id[sec] == now_id[sec]:
            continue
        old_lines = len(_akte_block_bodies(old)[sec].splitlines())
        new_lines = len(_akte_block_bodies(now)[sec].splitlines())
        if new_lines < old_lines:
            out.append(
                f"Akte: Block {sec} Zeilen {old_lines} -> {new_lines} "
                f"— Verlust im Block (Hash {old_id[sec]} -> {now_id[sec]})")
        else:
            # §A-ZH (Runde 53): gleiche oder mehr Zeilen, anderer Hash.
            # `if new_lines < old_lines` war die Bandage aus Runde 52:
            # „zwei gelöscht, zwei hinzugefügt ist in beiden grün". Der
            # Hash sieht es, und er ist die einzige Größe, die es sieht.
            out.append(
                f"Akte: Block {sec} geändert ({old_lines} -> {new_lines} "
                f"Zeilen, Hash {old_id[sec]} -> {now_id[sec]})"
                " — Berichtigung als neuer Block (§71.5x), nicht still")
    # Und die Groessen, damit ein Zeilenverlust **innerhalb** eines
    # Blocks nicht durch die Mengenpruefung faellt.
    for label, fn in (("Bezug-Zeilen", lambda t: t.count("\nBezug: root=")),
                      ("Zeilen", lambda t: len(t.splitlines())),
                      ("`total=`-Bloecke", lambda t: t.count("```\ntotal="))):
        a, b = fn(now), fn(old)
        if a < b:
            out.append(f"Akte: {label} {b} -> {a} — verloren")
    return out


def _self_test_root_probes() -> list[str]:
    """Sind die `root=None`-Proben **an der Rolle** erkennbar? (§A-NI)

    §A-NE (Runde 48) liess den Marker `§A-KR-ANCHOR` aus der **Zeile des
    Fundes** lesen. Zehn solcher Marker sind zehn `# noqa` in der Datei,
    die eine Rollenliste erfunden hat, um genau das abzuschaffen.

    Die Rolle ist „Negativtest", und sie ist am **Testkoerper** erkennbar:
    ein Default-Zweig wird nur in einer Funktion mit `_self_test`-Praefix
    gerufen, und der Fund ist dort das Ziel, nicht der Verstoss. Diese
    Funktion ist der Ort, an dem die Rolle deklariert ist — eine Stelle,
    reviewbar, statt zehn Kommentare am Fund.

    Geprueft wird beides: in den Testkoerpern wird der Marker **nicht
    mehr gebraucht**, im Produktionscode ist keiner.
    """
    out: list[str] = []
    src = Path(__file__).read_text(encoding="utf-8")
    lines = src.splitlines()
    # (a) kein Marker ausserhalb eines Selbsttests
    import ast
    tree = ast.parse(src)
    owner: dict[int, str] = {}
    for fn in tree.body:
        if isinstance(fn, ast.FunctionDef):
            for n in ast.walk(fn):
                if hasattr(n, "lineno"):
                    owner[n.lineno] = fn.name
            owner[fn.lineno] = fn.name
    stray = [i for i, ln in enumerate(lines, 1)
             if _KR_ANCHOR in ln and not owner.get(i, "").startswith(
                 ("_self_test", "self_test"))]
    # docstring-Zeilen sind keine Fundstellen
    stray = [i for i in stray if not lines[i - 1].strip().startswith(("#", '"'))]
    # §A-NI: und Zeilen, die von einem Docstring **umschlossen** sind.
    stray = [i for i in stray if not _inside_docstring(tree, i)]
    # Und die Zeile, die den Marker **definiert** — sie nennt ihn, sie
    # traegt ihn nicht.
    stray = [i for i in stray if not lines[i - 1].startswith("_KR_ANCHOR")]
    if stray:
        out.append(f"Root-Probe: Marker `{_KR_ANCHOR}` ausserhalb eines "
                   f"Selbsttests @L{stray[0]}")
    # (b) die Rolle wird erkannt: ein Default-Zweig im Testkoerper ist still,
    #     derselbe Aufruf im Produktionscode nicht.
    probe = (
        "def load_thing(root=None):\n"
        "    return (root / 'x').read_text()\n"
        "def _self_test_x():\n"
        "    load_thing()\n"
        "def production():\n"
        "    load_thing()\n"
    )
    got = _reader_calls_without_root(probe)
    if len(got) != 1 or "@L6" not in got[0]:
        out.append(f"Root-Probe: Rolle nicht erkannt — {got}")
    return out


def _inside_docstring(tree, lineno: int) -> bool:
    """Liegt `lineno` in einem String-Literal, das ein Docstring ist?"""
    import ast as _a
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                          ast.Module)):
            body = getattr(n, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                d = body[0]
                if d.lineno <= lineno <= (getattr(d, "end_lineno", d.lineno) or d.lineno):
                    return True
    return False


def _default_root_errors(src: str | None = None) -> list[str]:
    """Ist der Ort ein **Default**? (§A-MV, Runde 46)

    `_reads_without_root` unterscheidet „hat `root`" von „ohne `root`".
    Die kranke Form ist „hat `root` und benutzt es **manchmal** nicht":

        def version_line(root=None):
            p = root or Path.cwd()      # gelesen wird default-relativ

    Der Pruefer hätte sie nicht gefunden: der Name steht in seiner
    Erlaubnisliste, der Lesezugriff geht ueber `p`, und `p` geht ueber
    einen Fallback. **Die Signatur des Fehlers ist der Default.**

    Drei Formen, jede ein Verstoss:

      1. `root=None` als Vorgabewert — ein Lesepfad ohne Bezug ist dann
         die Vorgabe, nicht die Ausnahme.
      2. `X or Path.cwd()` / `X or "."` im Rumpf — der Fallback liest
         relativ, auch wenn `root` gesetzt ist.
      3. `os.getcwd()` / `Path.cwd()` im Rumpf ohne `or` — derselbe Ort,
         ohne dass ein Aufrufer ihn steuern kann.

    **Nebenwirkung, ehrlich:** `root=None` ist vermutlich an einigen
    Stellen bewusst gesetzt, damit Tests ohne Argument rufen koennen. Das
    ist Aufrufkomfort — und der gehoert in den Aufrufer, nicht in die
    Signatur. Der Pruefer meldet darum **jede** Form; die erste Reaktion
    darf nicht „Ausnahme" heissen.
    """
    import ast
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    out: list[str] = []

    def is_none(n: ast.AST | None) -> bool:
        return isinstance(n, ast.Constant) and n.value is None

    def is_cwd(n: ast.AST) -> bool:
        return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "cwd"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id in ("Path", "os"))

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name in _CWD_READERS:
            # §A-MX: deklarierter Leser, kein Verstoss. Die Rolle steht
            # hier und nicht als Ausnahme am Fund — wer sie ergaenzt,
            # muss begruenden, warum die Funktion `cwd` **lesen** muss.
            continue
        # §A-MX (Runde 47): die Regel gehoert auf die **Kombination**,
        # nicht auf den Default. `root=None` allein ist Aufrufkomfort —
        # `repo_root(root=None)` loest den Ort intern auf und liest
        # nichts relativ. Der Fehler ist `root=None` **und** ein Pfad,
        # der ohne `root` entsteht. Deshalb zwei Ebenen:
        #
        #   A. `cwd` im Rumpf — **immer** rot. Kein Aufrufer steuert
        #      ihn, auch nicht mit gesetztem `root`.
        #   B. `root=None` — rot **nur mit** relativem Fallback im
        #      Rumpf (`or Path.cwd()`, `or "."`, `or Path()`, oder ein
        #      `Path()` ohne Argument, oder ein relatives Literal an
        #      `open()`).
        #
        # Damit bleibt von den Fundstellen der letzten Runde nur die
        # echte uebrig; die Komfort-Faelle fallen weg.
        # Der Test kann dann `== 0` verlangen, ohne Ausnahmeliste.
        has_none_default = False
        offset = len(fn.args.args) - len(fn.args.defaults)
        for i, d in enumerate(fn.args.defaults):
            name = fn.args.args[offset + i].arg
            if name in ("root", "doc_root", "repo") and is_none(d):
                has_none_default = True
        for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
            if a.arg in ("root", "doc_root", "repo") and is_none(d):
                has_none_default = True

        rel_fallback: list[int] = []
        cwd_lines: list[int] = []
        for n in ast.walk(fn):
            if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or):
                for v in n.values:
                    if is_cwd(v):
                        rel_fallback.append(n.lineno)
                    elif isinstance(v, ast.Constant) and v.value == ".":
                        rel_fallback.append(n.lineno)
                    elif (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                          and v.func.id == "Path" and not v.args):
                        rel_fallback.append(n.lineno)
            if is_cwd(n) and not isinstance(n, ast.BoolOp):
                cwd_lines.append(n.lineno)
        # A — cwd im Rumpf: immer rot
        for line in sorted(set(cwd_lines)):
            out.append(
                f"{fn.name} (@L{line}): `Path.cwd()` im Rumpf — "
                f"Ort ist nicht steuerbar")
        # B — Default **und** relativer Fallback: das ist der Fehler
        if has_none_default and rel_fallback:
            for line in sorted(set(rel_fallback)):
                out.append(
                    f"{fn.name} (@L{line}): `root=None` mit relativem "
                    f"Fallback — Leseort ist die Vorgabe")
    return out


def _name_based_decisions(src: str | None = None) -> list[tuple[int, str, str]]:
    """Zaehlt Entscheidungen, die einen Parameter an seinem **Namen** messen.

    §A-NL (Runde 50), die vierte Namensbasis. In dieser Datei urteilten
    drei Stellen ueber den Namen statt ueber die Semantik (`_binds_root`
    und die `ok_names`-Ausnahmeliste). `_resolve_test_root` reichte `root`
    die ganze Zeit korrekt durch — die namensbasierte Auswahl sah es
    nicht. Der Fund war nicht „repariere die dritte", sondern „die Menge
    ist zaehlbar": solange drei Konventionen bestehen, ist eine vierte
    nicht auffindbar.

    Gemessen per `ast`, nicht per `grep`: ein `Compare`-Knoten, dessen
    linker Operand ein Attribut `.arg` oder ein Parameter der
    umschliessenden Funktion ist, verglichen gegen String-Literale.

    Abgrenzung, gemessen und nicht angenommen: `k.arg == "cwd"` auf einem
    **Call-Keyword** und `a.arg in (...)` auf einem **arguments**-Element
    sind AST-**Feld**namen, keine Parameterwahl — sie lesen die Syntax,
    nicht die Konvention. In dieser Datei sind das die Mehrheit der
    Treffer, und sie sind richtig so. Eine Namensbasis ist nur, was einen
    **Parameter** nach seinem Namen beurteilt.
    """
    import ast
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    out: list[tuple[int, str, str]] = []

    def literals(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, (ast.Tuple, ast.Set, ast.List)):
            return [e.value for e in node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        return []

    def is_param_operand(node: ast.AST, params: set[str],
                         arg_owners: set[int]) -> bool:
        if isinstance(node, ast.Name):
            return node.id in params
        # `x.arg` ist **kein** Parameterbezug: es liest ein AST-Feld
        # (`keyword.arg`, `arg.arg`). `root is None` ist der Parameter;
        # `a.arg == "root"` ist Syntax. Die Verwechslung dieser beiden
        # war der Grund, warum die drei Namensbasen unsichtbar blieben.
        return False

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = {a.arg for a in fn.args.args + fn.args.kwonlyargs
                  + fn.args.posonlyargs}
        arg_owners: set[int] = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and n.attr in (
                    "args", "kwonlyargs", "posonlyargs"):
                arg_owners.add(id(n))
        for n in ast.walk(fn):
            if not isinstance(n, ast.Compare):
                continue
            if not is_param_operand(n.left, params, arg_owners):
                continue
            for comp in n.comparators:
                for lit in literals(comp):
                    out.append((n.lineno, fn.name, lit))
    return out


def _cwd_reader_ok_names(src: str | None = None) -> list[tuple[int, str]]:
    """Die Ausnahmeliste von `check_path_reading` — als Zahl, nicht als Prosa.

    §A-NL (Runde 50): `ok_names` ist eine weitere Namensbasis. Gewollt
    (Pfad-Funktionen ohne `root`), aber unsichtbar: eine stille
    Erweiterung haette niemandem auffallen koennen. Hier steht sie, und
    der Selbsttest vergleicht sie mit der erwarteten Menge.
    """
    import ast
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    found: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        value = None
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == "ok_names":
                    value = n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            if n.target.id == "ok_names":
                value = n.value
        if not isinstance(value, ast.Tuple):
            continue
        for e in value.elts:
            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                found.append((n.lineno, e.value))
    return found


def _self_test_name_bases() -> list[str]:
    """§A-NL (Runde 50): der Pruefer ueber den Pruefern.

    `== 0` auf `_name_based_decisions` — der Wert ist **messbar**. Dazu
    die Falsifikation: eine eingefuegte Namensbasis muss die Zahl heben,
    sonst ist der Pruefer selbst eine Zusage ohne Deckung.
    """
    failures: list[str] = []
    hits = _name_based_decisions()
    if hits:
        detail = ", ".join(f"{fn}:{ln}({v})" for ln, fn, v in hits)
        failures.append(f"Namensbasis statt Semantik: {detail}")

    probe = ("def f(param):\n"
             "    if param in ('root', 'repo'):\n"
             "        return 1\n"
             "    return 0\n")
    if len(_name_based_decisions(probe)) != 2:
        failures.append("Meta-Pruefer erkennt eine Namensbasis nicht")
    # Gegenprobe: AST-Feldnamen sind **keine** Namensbasis.
    ast_only = ("def f(fn):\n"
                "    if fn.arg == 'root':\n"
                "        return 1\n"
                "    return 0\n")
    if _name_based_decisions(ast_only):
        failures.append("Meta-Pruefer haelt AST-Feldnamen fuer eine Basis")

    ok = _cwd_reader_ok_names()
    declared = {v for _, v in ok}
    expected = {"root", "doc_root", "repo", "path", "file", "base", "td"}
    if declared != expected:
        failures.append(f"ok_names weicht ab: {sorted(declared ^ expected)}")
    if len(ok) != len(declared):
        failures.append("ok_names enthaelt Doppelungen")
    return failures


def _reads_without_root(src: str | None = None) -> list[str]:
    """Liest eine Funktion Dateien, ohne `root` zu bekommen? (§A-MS, Runde 45)

    `_git_callers_without_cwd` deckt genau **einen** Sonderfall ab: einen
    `git`-Aufruf ohne `cwd`. Der Fehler in Runde 44 war aber
    `check_counts(..., root=None)` — ein **Lesezugriff** ohne `root`, der
    im Klon null statt sechzehn Befunde lieferte. Der Pruefer, der nach
    `git` sucht, konnte ihn nicht finden, weil er nicht nach `git` fragt.

    Der allgemeine Fehler ist nicht `git`, sondern: eine Funktion, die
    Dateien liest, und deren Ergebnis von **welcher** Datei abhaengt, ohne
    einen Parameter, der den Ort traegt.

    Gemeldet wird eine Funktion, wenn sie
      * `open(`, `read_text(`, `read_bytes(`, `.glob(`, `.rglob(`, `.exists(`
      * oder `Path(...)` auf einen **relativen** oder **konstruierten** Pfad
    benutzt **und** keinen Parameter `root`, `doc_root`, `repo` oder `path`
    hat. Ausnahmen sind Funktionen, deren Zweck der Dateizugriff ist
    (`_load_*`, `_read_*`, `_save_*`, `_status_line`).
    """
    import ast
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(text)
    out: list[str] = []
    # §A-MS: `doc`/`text` stehen **nicht** hier. Das sind Dokumenttexte,
    # keine Orte — im Fall der letzten Runde war `doc_root` der Ort und `doc` der
    # Inhalt. Wer einen Text als Pfadtraeger benutzt, hat den Fehler.
    ok_names = ("root", "doc_root", "repo", "path", "file", "base", "td")
    ok_prefix = ("_load_", "_read_", "_save_", "_status", "check_inventory_",
                 "parse_waves", "load_")

    def touches_file(node: ast.AST) -> bool:
        """Liest die Funktion Dateien an einem **fremden** Ort?

        `Path(__file__)` ist kein fremder Ort: die Datei liegt, wo sie
        liegt, und das Ergebnis haengt nicht von einem Aufrufer ab. Ein
        relativer oder konstruierter Pfad schon — und genau der ist der
        Fall aus Runde 44.
        """
        for n in ast.walk(node):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            is_read = ((isinstance(f, ast.Name) and f.id == "open") or
                       (isinstance(f, ast.Attribute) and f.attr in (
                           "read_text", "read_bytes", "glob", "rglob",
                           "exists", "is_file", "is_dir")))
            if not is_read:
                continue
            # Alle Argumente **und** den Traeger des Aufrufs pruefen:
            # `(Path(doc) / "scripts").glob("*.py")` hat den Pfad im
            # Traeger, nicht im Argument.
            cands: list[ast.AST] = list(n.args)
            if isinstance(f, ast.Attribute):
                cands.append(f.value)
            if _has_foreign_path(cands):
                return True
            # §A-MS: ein **relativer** String als Pfad ist ortsabhaengig,
            # auch ohne `Path(...)`: `open("CLAUDE.md")` liest, wo immer
            # der Prozess steht. Das ist der Fall, den Runde 41 im Klon
            # traf — dort wurde die falsche Datei gelesen, ohne Fehler.
            for a in n.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    v = a.value
                    if v.startswith(("/", "http", "*")) or not v.strip("*."):
                        continue
                    if "/" in v or v.endswith((".md", ".py", ".json", ".yaml")):
                        return True
        return False

    def _has_foreign_path(nodes: list[ast.AST]) -> bool:
        """Enthaelt einer der Ausdruecke einen Pfad, dessen Ort ein
        **Parameter** ist — aber kein Ortsparameter der Funktion?

        Gemeint ist genau der Fall der letzten Runde: `Path(doc)` oder
        `Path(doc_root)`, wo `doc` der **Dokumenttext** ist und nicht der
        Ort. Ein Traeger mit `root` ist legitim.
        """
        for n0 in nodes:
            for n in ast.walk(n0):
                if isinstance(n, ast.Attribute) and n.attr == "__file__":
                    return False
                if not isinstance(n, ast.Call):
                    continue
                if not (isinstance(n.func, ast.Name) and n.func.id == "Path"):
                    continue
                for a in n.args:
                    if isinstance(a, ast.Name) and a.id in (
                            "root", "doc_root", "repo", "base", "td",
                            "__file__"):
                        break        # Ortsparameter: legitim
                    if isinstance(a, ast.Name):
                        return True  # Parameter, aber kein Ort
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        if a.value.startswith(("/", "http")):
                            break
                        return True
        return False

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name.startswith(ok_prefix):
            continue
        if not touches_file(fn):
            continue
        params = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
        if params & set(ok_names):
            continue
        out.append(f"{fn.name} (@L{fn.lineno}) liest Dateien ohne Ortsparameter "
                   f"— {sorted(params)[:4]}")
    return out


def _self_test_reads_without_root() -> list[str]:
    """Findet der Lese-Pruefer den Fall aus der letzten Runde? (§A-MS)

    Der Fehler war `check_counts`, das ohne `root` im Klon null statt
    sechzehn Befunde lieferte. `_git_callers_without_cwd` suchte nach
    `git` und konnte ihn nicht finden, weil er nicht nach `git` fragt.

    Erwartungen sind **Literale mit Herkunft**: von fuenf Probefunktionen
    sind genau **zwei** ortsabhaengig — `Path(doc)` und `open("relativ")`.
    Die drei anderen sind der Gegenbeweis: `root`, `__file__` und
    `/absolut` sind legitime Orte.
    """
    out: list[str] = []
    probe = (
        "def check_bad(doc, rep):\n"
        "    (Path(doc) / 'scripts').glob('*.py')\n"
        "def check_ok(doc, root, rep):\n"
        "    (root / 'scripts').glob('*.py')\n"
        "def check_self(rep):\n"
        "    Path(__file__).read_text()\n"
        "def check_lit(rep):\n"
        "    open('/etc/hosts').read_text()\n"
        "def check_rel(rep):\n"
        "    open('CLAUDE.md').read_text()\n"
    )
    got = _reads_without_root(probe)
    if len(got) != 2:
        out.append(f"Lese-Pruefer: {len(got)} Fundstellen, erwartet 2 "
                   f"(Path(doc) und open(relativ)) — {got}")
    for name in ("check_bad", "check_rel"):
        if not any(name in g for g in got):
            out.append(f"Lese-Pruefer findet {name} nicht")
    for name in ("check_ok", "check_self", "check_lit"):
        if any(name in g for g in got):
            out.append(f"Lese-Pruefer meldet {name} — legitimer Ort")
    # Und die eigene Datei: keine Fundstelle. Eine Funktion, die ihre
    # eigene Datei liest, ist kein ortsabhaengiger Zugriff.
    own = _reads_without_root()
    if own:
        out.append(f"Lese-Pruefer meldet die eigene Datei: {own[:2]}")
    return out


def _self_test_default_root() -> list[str]:
    """Findet der Default-Pruefer die drei Formen? (§A-MV)

    Erwartungen als **Literale mit Herkunft**: von vier Probefunktionen
    sind genau **zwei** krank (`root=None` plus `or Path.cwd()`, und
    `Path.cwd()` im Rumpf), zwei sind sauber (`root` ohne Default,
    `root=Path("/tmp")`). Die Gesamtzahl der Fundstellen wird **nicht**
    behauptet — sie ist die Buchung, nicht die Zusicherung.

    **Und sie steht als Zahl im Ergebnis**, nicht als Schwelle: die
    Akte soll den Stand kennen, nicht dulden. Ein Gate, das heute den
    Stand X hat und X erlaubt, ist ein Literal gegen sich selbst.
    """
    out: list[str] = []
    probe = (
        "def version_line(root=None):\n"
        "    p = root or Path.cwd()\n"
        "    return (p / 'x').read_text()\n"
        "def check_cwd(rep):\n"
        "    return Path.cwd() / 'x'\n"
        "def ok_fn(root):\n"
        "    return (root / 'x').read_text()\n"
        "def ok_default(root=Path('/tmp')):\n"
        "    return (root / 'x').read_text()\n"
    )
    got = _default_root_errors(probe)
    names = {g.split(" ")[0] for g in got}
    if names != {"version_line", "check_cwd"}:
        out.append(f"Default-Pruefer: Funktionen {sorted(names)}, "
                   f"erwartet ['check_cwd', 'version_line']")
    if "`root=None` mit relativem Fallback" not in " ".join(got):
        out.append("Default-Pruefer findet die Kombination "
                   "`root=None` + Fallback nicht")
    for name in ("ok_fn", "ok_default"):
        if any(g.startswith(name) for g in got):
            out.append(f"Default-Pruefer meldet {name} — legitime Form")
    return out


def calibration_card(root: Path | None = None) -> str:
    """Der Block, den die Akte zitiert — als **Ausgabe**, nicht als Absatz.

    Die Akte hat seit Runde 42 eine Regel: jede Zahl traegt ihren Bezug.
    Die Kopfzeile nennt `root` und `sha256`, die Felder sind einzeln rot
    gemessen. **Der Ergebnisblock war die einzige Zahlengruppe ohne
    Bezugszeile** — er hatte keinen `root`, keine `sha256`, keinen
    Commit-Hash des Laufs, der ihn erzeugt hat. Deshalb konnte eine
    einzelne Zahl verschwinden, ohne dass es auffiel.

    Ausgabe: der Block mit einer `Bezug:`-Zeile darunter, im selben
    Format wie die Kopfzeile. Wer ihn in die Akte kopiert, kopiert eine
    Messung, keinen Absatz.
    """
    import hashlib
    base = root or Path(__file__).resolve().parent.parent
    rep = calibration_run(base)
    doc = (base / "CLAUDE.md").read_text(encoding="utf-8")
    sha = hashlib.sha256(doc.encode("utf-8")).hexdigest()[:12]
    lines = [f"total={rep['total']} chain_total={rep['chain_total']} "
             f"reported={rep['reported']} unclassified={rep['unclassified']} "
             f"unchecked={rep['unchecked']} "
             f"unclassified_checkers={rep['unclassified_checkers']}"]
    for name, n in rep["classes"]:
        lines.append(f"  {name}: {n}")
    # §A-NM (Runde 51): die drei Zahlen gehören **in** den Block. Ein Block,
    # der nur `total=` zitiert und die Einschränkung dem Fließtext überlässt,
    # wiederholt genau den Kopfzeilen-Fehler eine Ebene tiefer.
    _unref = [c for c in rep["claims"] if c[0] == "suite:ohne-skript"]
    _measured = repo_measurement_available(base)
    tally = measurement_tally(int(rep["total"]) if _measured else None,
                              measured=_measured,
                              ohne_skript=[c[0] for c in _unref],
                              umfang=PRUEFER_UMFANG,
                              ohne_skript_entfernt=12 if not _unref else 0)
    lines.append(f"kopfzeile: {tally_line(tally)}")
    # §A-ZU: der Fingerprint der **Zahlen-Eingaben**, nicht des Laufs.
    # Er ist Herkunft (nicht ableitbar aus dem Blocktext) und gehört
    # darum hierher; `dirty`/Pfad/Zeit bleiben draußen, sonst trifft
    # kein Block je einen Lauf.
    fp = _card_fingerprint({k: int(rep[k]) for k in
                            ("total", "chain_total", "reported",
                             "unclassified", "unchecked",
                             "unclassified_checkers")},
                           rep["classes"])
    lines.append(f"Karte: {fp}")
    lines.append(f"Bezug: root={base}, CLAUDE.md sha256:{sha}, "
                 f"Baum {_tree_ref(base)}")
    return "\n".join(lines)


def _self_test_calibration_classes() -> list[str]:
    """Kommt die Klassenliste aus dem Lauf — und schliesst sie? (§A-MM)

    Drei Behauptungen, und die dritte ist die, die zweimal fehlte:

      1. Jeder Pruefer der `main`-Kette erscheint in der Ausgabe.
      2. `sum(classes) + unclassified == chain_total` — die **Arithmetik**
         innerhalb eines Laufs.
      3. Die Luecke **existiert**: es gibt einen Baum, auf dem
         `unclassified > 0` ist, und die Klassenliste benennt, wer sie
         traegt.

    Ohne die dritte Behauptung ist `unclassified == 0` auf beiden
    Baeumen kein Lueckenpruefer, sondern ein Literal gegen `0`: im
    eigenen Baum stehen beide Wege auf null, und eine Luecke, hinter der
    gerade nichts steht, sieht niemand. Der Klon, der die Luecke zeigte,
    ist ein **Artefakt** — jemand baut ihn von Hand. Ein Pruefmittel, das
    jemand von Hand baut, ist keins.

    Darum baut dieser Test zwei Baeume, und der zweite laesst absichtlich
    eine Luecke: ein `CLAUDE.md`-Satz, dessen Zahl nur mit `root`
    aufloesbar ist. Was die Luecke fuellt, ist nicht wichtig — wichtig ist,
    dass es sie gibt und dass sie **gezaehlt** wird.
    """
    import tempfile
    out: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "CLAUDE.md").write_text("# leer\n", encoding="utf-8")
        base = calibration_run(root)
        names = sorted(n for n, _ in base["classes"])
        # Erwartung als Literal mit Herkunft: `main` ruft
        # `check_line_counts`, `check_dead_refs`, `check_counts`,
        # `check_undocumented_tests`, `check_doc_inventories`,
        # `check_test_paths_ignored` (Runde 51), `check_akte_write_mode`
        # (Runde 52) und `check_prose_fractions` (Runde 53; `check_tests`
        # nur unter `--run-tests`). Ohne `with_tests` sind das **acht**
        # Klassen — die Zahl selbst wird vom `_checker_gap`-Test gegen
        # `main` gemessen, nicht hier vertraut.
        want = ["Zeilen", "Referenzen", "Wellen", "Tests ohne Skript",
                "Inventare", "Testpfade", "Schreibmodus",
                "Fließtext-Brüche"]
        if names != sorted(want):
            out.append(f"Kalibrierlauf nennt nicht die acht der Kette: {names}")
        if len(base["classes"]) != len(want):
            out.append(f"Kalibrierlauf hat {len(base['classes'])} Klassen, "
                       f"erwartet {len(want)}")
        # (2) Die harte Zeile: total ist die Summe der Klassen — und die
        #     Kette ist Summe plus Luecke. Beide Gleichungen, nicht eine.
        s = sum(n for _, n in base["classes"])
        if base["total"] != s:
            out.append(f"Kalibrierlauf: total {base['total']} != "
                       f"Summe der Klassen {s}")
        if s + base["unclassified"] != base["chain_total"]:
            out.append(f"Kalibrierlauf schliesst nicht: {s} + "
                       f"{base['unclassified']} != {base['chain_total']}")
        # §A-MR: die **dritte** Zahl. `reported` entsteht, indem jeder
        # Pruefer seine eigene Befundliste liefert — unabhaengig von
        # `classes` und von der Kette. Zwei Wege, die denselben Fehler
        # gleich falsch gehen, sind ein Weg mit zwei Ausgaengen; diese
        # Zahl geht einen dritten.
        if base["reported"] != base["total"]:
            out.append(f"Kalibrierlauf: gemeldet {base['reported']} != "
                       f"total {base['total']} — Zerlegung und Meldung "
                       f"stimmen nicht ueberein")
        if base["unclassified"] != 0:
            out.append(f"Kalibrierlauf: {base['unclassified']} Befunde ohne "
                       f"Klasse im leeren Baum (Kette {base['chain_total']}, "
                       f"Summe {s})")

    # (3) Der Baum mit der **absichtlichen** Luecke. `calibration_run`
    #     nimmt optional einen Zusatzpruefer, der **nur** in der Kette
    #     laeuft — dann muss `unclassified > 0` sein. Das ist der Fall,
    #     den Runde 44 zweimal traf: ein Pruefer, den die Kette faehrt
    #     und die Klassenliste nicht kennt. Ohne diesen Zweig ist
    #     `unclassified == 0` auf beiden Baeumen ein Literal gegen `0`.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "CLAUDE.md").write_text("# Probe\n", encoding="utf-8")

        def _extra(rep) -> None:  # absichtlicher Befund ausserhalb der Klassen
            rep.fail(None, "Probe-Luecke", "x", "absichtlich")

        gap = calibration_run(root, extra_checkers=(("Luecke", _extra),))
        if gap["unclassified"] != 1:
            # Erwartung ist ein Literal mit Herkunft: der Zusatzpruefer
            # meldet genau **einen** Befund. Kommt er in der Klassenliste
            # an, ist `unclassified` 0 und die Luecke unsichtbar.
            out.append(f"Kalibrierlauf: Luecke nicht gezaehlt "
                       f"(unclassified {gap['unclassified']}, erwartet 1)")
        if gap["chain_total"] != gap["total"] + 1:
            out.append("Kalibrierlauf: Kette traegt den Zusatzpruefer nicht")
        if "Luecke" in [n for n, _ in gap["classes"]]:
            out.append("Kalibrierlauf: Zusatzpruefer ist in die Klassen "
                       "gerutscht und verdeckt die Luecke")
        # §A-MU (Runde 46): **hier** trennen sich die drei Zahlen. Im
        # eigenen Baum sind total, chain_total und reported alle null und
        # widersprechen sich nicht; der Zusatzpruefer ist der einzige
        # Zustand im Selbsttest, in dem `reported` beweisen muss, dass es
        # unabhaengig entsteht. Erwartung: `reported` waechst mit der
        # Kette, `total` bleibt — und beide Zahlen sind **verschieden**.
        if gap["reported"] != gap["chain_total"]:
            out.append(f"Kalibrierlauf: reported {gap['reported']} != "
                       f"chain_total {gap['chain_total']} — der "
                       f"Zusatzpruefer fehlt in der Meldung")
        if gap["reported"] == gap["total"]:
            out.append(f"Kalibrierlauf: reported == total ({gap['total']}) "
                       f"— die drei Zahlen trennen sich nicht")
    # §A-MT: beide Richtungen der Pruefer-Differenz. Eine Probe, in der
    # `main` einen Pruefer kennt, den der Lauf nicht kennt, muss als
    # `unchecked` erscheinen — das war der Fehler der letzten Runde. Die
    # Umkehrung muss als `unclassified_checkers` erscheinen.
    probe = (
        "def main():\n"
        "    check_a()\n"
        "    check_b()\n"
        "def calibration_run():\n"
        "    check_a()\n"
    )
    if _checker_gap("main", "calibration_run", probe) != 1:
        out.append("Pruefer-Differenz: `unchecked` findet den fehlenden "
                   "Pruefer nicht (erwartet 1)")
    backward = (
        "def main():\n"
        "    check_a()\n"
        "def calibration_run():\n"
        "    check_a()\n"
        "    check_c()\n"
    )
    if _checker_gap("calibration_run", "main", backward) != 1:
        out.append("Pruefer-Differenz: `unclassified_checkers` findet den "
                   "unproduktiven Pruefer nicht (erwartet 1)")
    # Und die eigene Datei: beide Differenzen sind heute 0.
    # §A-NB (Runde 48): die **eigene** Datei muss eine Zahl liefern.
    # `None` heisst „Register gesehen, Ziel nicht gefunden" — ein Befund,
    # kein Freispruch, und im eigenen Baum besonders verdaechtig.
    fwd = _checker_gap("main", "calibration_run")
    bwd = _checker_gap("calibration_run", "main")
    if not isinstance(fwd, int):
        out.append("Pruefer-Differenz: unchecked ist None — Register im "
                   "eigenen Baum nicht aufloesbar")
    elif fwd != 0:
        out.append("Pruefer-Differenz: main ruft einen Pruefer, den der "
                   "Kalibrierlauf nicht kennt")
    if not isinstance(bwd, int):
        out.append("Pruefer-Differenz: unclassified_checkers ist None — "
                   "Register im eigenen Baum nicht aufloesbar")
    elif bwd != 0:
        out.append("Pruefer-Differenz: der Kalibrierlauf ruft einen Pruefer, "
                   "den main nicht faehrt")
    # Und die Gegenprobe: ein **dynamisches** Register liefert `None`.
    global _REGISTRIES
    _REGISTRIES = frozenset({"CHECKS"})
    dyn = ("CHECKS = tuple(c for c in (check_a, check_b))\n"
           "def main():\n    for c in CHECKS:\n        c(root)\n"
           "def calibration_run():\n    check_a(root)\n")
    # §A-NH (Runde 49): das Iterat **durchgereicht** statt gerufen. Erwartet
    # ist die Differenz eins: `CHECKS` traegt zwei Pruefer, der
    # Kalibrierlauf einen (2 − 1). Das Fixture steht als Literalverkettung
    # da, damit die Herkunft der Zahl in der Zeile lesbar bleibt.
    passed = (
        "CHECKS = (check_a, check_b)\n"
        "def main():\n"
        "    for c in CHECKS:\n"
        "        apply(c, root)\n"
        "def calibration_run():\n"
        "    check_a(root)\n"
    )
    expect = 1   # CHECKS carries two checkers, calibration_run one
    if _checker_gap("main", "calibration_run", passed) != expect:
        out.append("Pruefer-Differenz: `for c in CHECKS: apply(c)` gilt "
                   "als Daten-Schleife — blind und gruen sehen gleich aus")
    # Und `append` ist kein Register: eine Methode bindet, sie reicht nicht.
    app = ("def main():\n    for a in raw:\n        out.append(a)\n"
           "def calibration_run():\n    check_a(root)\n")
    if _checker_gap("main", "calibration_run", app) is None:
        out.append("Pruefer-Differenz: `out.append(a)` gilt als Register")
    reg = ("CHECKS = (check_a, check_b)\n"
           "def main():\n    for c in CHECKS:\n        c(root)\n"
           "def calibration_run():\n    check_a(root)\n")
    # Und die Umkehrung: ein **nicht deklariertes** Register ist laut.
    _REGISTRIES = frozenset()
    try:
        if _checker_gap("main", "calibration_run", reg) is not None:
            out.append("Pruefer-Differenz: nicht deklariertes Register "
                       "liefert eine Zahl statt None")
    finally:
        _REGISTRIES = frozenset({"CHECKS"})
    if _checker_gap("main", "calibration_run", dyn) is not None:
        out.append("Pruefer-Differenz: dynamisches Register liefert eine "
                   "Zahl statt None — blind und gruen sehen gleich aus")
    # Und die andere Haelfte: Daten-Schleifen sind **kein** Register.
    data = ("def main():\n    for p in rep.problems:\n        pass\n"
            "def calibration_run():\n    check_a(root)\n")
    if _checker_gap("main", "calibration_run", data) is None:
        out.append("Pruefer-Differenz: `for p in rep.problems` gilt als "
                   "unaufloesbares Register")
    # §A-MW (Runde 47): die Registry. Ersetzt jemand die sechs Aufrufe
    # durch `for c in CHECKS`, darf der Pruefer nicht blind werden. Die
    # Probe ist die bessere Architektur — der Pruefer muss sie lesen.
    # §A-NH: die dritte Luecke — Iterat **durchgereicht** statt gerufen.
    passed = reg.replace("c(root)", "apply(c, root)")
    if _checker_gap("main", "calibration_run", reg) != 1:
        out.append("Pruefer-Differenz: die Registry macht den Pruefer blind "
                   "(`check_b` ueber `CHECKS` nicht gezaehlt)")
    # Und die Rolle: jede Funktion mit `rep` in der Signatur ist ein
    # Pruefer, egal wie sie heisst. Ein Pruefer namens
    # `_reads_without_root` waere sonst in keiner der beiden Mengen.
    role = (
        "def _weird_name(rep):\n"
        "    pass\n"
        "def main():\n"
        "    _weird_name(r)\n"
        "def calibration_run():\n"
        "    pass\n"
    )
    import ast as _ast
    fns = _report_functions(_ast.parse(role))
    if fns != {"_weird_name"}:
        out.append(f"Pruefer-Rolle: {sorted(fns)}, erwartet ['_weird_name']")
    return out


# §A-ND: die 28 Zusagen. Sie stehen im Nenner (`461 = 433 + 28`) und in
# keiner Pruefung: `>>>` kommt in `CLAUDE.md` null Mal vor. Drei Wege
# standen zur Wahl — in `>>>` ziehen (Prosa wird Code, zwei Orte zu
# pflegen), aus der Zahl nehmen (Nenner schrumpft um die Zusagen, aber sie verschwinden
# still weiter), oder **an `claim()` binden**. Der dritte beschreibt den
# Zustand korrekt: ungemessen, aber nicht driftfaehig.
#
# Die Zahl 28 wird **nicht** hier gepflegt. Sie entsteht aus einem Lauf
# von `check_counts` gegen `CLAUDE.md` — dieselbe Quelle, die den Bericht
# speist. Der Guard steht in `_self_test_claim_count()` und vergleicht die
# live gezaehlte Menge gegen die Zahl, die der letzte echte Lauf gedruckt
# hat. Herkunft der Sollzahl: siehe `_CLAIM_COUNT_ORIGIN`.
_CLAIM_COUNT_EXPECTED = 28
_CLAIM_COUNT_ORIGIN = (
    "Runde 40, §A-NC: `_status_line` zerlegte 461 in 433 gemessen + 28 "
    "Zusagen. Nachgezaehlt in Runde 41 aus `len(rep.claims)` eines Laufs "
    "ueber CLAUDE.md (Feld `claims` in --json-report). Die Zahl ist eine "
    "Messung, kein Beschluss — aendert sich die Doku, aendert sie sich.")


def _self_test_claim_count(doc_text: str | None = None) -> list[str]:
    """Sind es noch 28 — gemessen, **und an welcher Stelle**? (§A-ND/§A-MB)

    Zwei Fragen: die live gezaehlte Menge stimmt mit der Sollzahl, **und**
    jede Zusage traegt ihre Position. Eine Zusage ohne Position ist eine
    Zahl ohne Herkunft.

    §A-MB (Runde 42): die erste Gegenprobe halbierte den Text und sah
    `24` — sie belegte, dass die Zahl sich aendert, nicht dass sie misst.
    `24` ist keine Haelfte von `28`; die vier fehlenden lagen in der
    zweiten Haelfte, die vier bleibenden im Kopf. Jetzt wird an einer
    **bekannten Zeile** geschnitten: alle gefundenen Positionen muessen
    **vor** dem Schnitt liegen. Das ist die Aussage, die der Extraktor
    treffen muss, und die einzige, die er treffen kann.

    **Formabhaengigkeit, benannt:** der Extraktor erkennt `N/N tests
    passed` und `N/N Tests` — ein umformulierter Satz ohne
    Bedeutungswechsel faellt aus der Zaehlung und macht diesen Test rot,
    ohne dass etwas verloren ist. Das ist der Preis der Ableitung, und er
    steht an der Konstante (§A-MC).
    """
    from pathlib import Path as _P
    text = doc_text if doc_text is not None else _P("CLAUDE.md").read_text(
        encoding="utf-8")
    rep = Report()
    waves, per = parse_waves(text)
    check_counts(text, waves, per, rep, _P.cwd())
    out: list[str] = []
    if len(rep.claims) != _CLAIM_COUNT_EXPECTED:
        out.append(
            f"{len(rep.claims)} Zusagen live, erwartet {_CLAIM_COUNT_EXPECTED} "
            f"— Herkunft: {_CLAIM_COUNT_ORIGIN} — REDAKTION? Ein "
            f"umformulierter Satz ohne Bedeutungswechsel faellt hier raus "
            f"(§A-MC); dann Zahl anpassen, nicht Text")
    bare = [c for c in rep.claims if not c[0]]
    if bare:
        out.append(f"{len(bare)} Zusagen ohne Feld")
    no_pos = [c for c in rep.claims if not c[2]]
    if no_pos:
        out.append(f"{len(no_pos)} Zusagen ohne Position")

    # §A-MH: der Schnitt gehoert in die **Mitte der Verteilung**, nicht in
    # den Auslaeufer. Der erste Test schnitt bei L1493 — der letzten
    # Zusage. Ein Extraktor, der irgendeine Zeilennummer davor lieferte,
    # bestand ihn. Geprueft wird jetzt an der Medianzeile: die eine Haelfte
    # muss davor, die andere dahinter liegen, **beide Zahlen einzeln**.
    positions = sorted(c[2] for c in rep.claims if c[2])
    if not positions:
        out.append("keine Positionen — Halbierung nicht pruefbar")
        return out
    lines = text.splitlines(keepends=True)
    median = positions[len(positions) // 2]
    before_expect = sum(1 for p in positions if p < median)
    after_expect = sum(1 for p in positions if p >= median)
    cut = median
    if cut is None:
        out.append("Schnittzeile nicht gefunden — Gegenprobe blind")
        return out
    half = "".join(lines[:cut - 1])
    rep_h = Report()
    w_h, p_h = parse_waves(half)
    check_counts(half, w_h, p_h, rep_h, _P.cwd())
    late = [c for c in rep_h.claims if c[2] and c[2] >= cut]
    if late:
        out.append(f"{len(late)} Zusagen hinter dem Schnitt: {late[:2]!r}")
    # Beide Haelften einzeln: die Zahl vor dem Schnitt ist die erwartete,
    # und sie ist **nicht** null (sonst schneidet der Test am Anfang).
    if len(rep_h.claims) != before_expect:
        out.append(
            f"vor dem Schnitt {len(rep_h.claims)} statt {before_expect}")
    if after_expect < 1 or before_expect < 1:
        out.append(
            f"Schnitt am Rand statt in der Mitte: {before_expect} davor, "
            f"{after_expect} dahinter")
    return out


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
            # §A-NU (Runde 52): das `.gitignore`-Orakel — Antwort und
            # Herkunft. Ohne diese Zeile traegt ein Test die Antwort des
            # vorigen und meldet gruen, weil ein anderer Baum geantwortet hat.
            _IGNORE_CACHE.clear()
            _GITIGNORE_SOURCE[0] = "unbekannt"

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
        # §A-LA (Runde 40): die Liste war eine **harte Menge von Zahlen**.
        # Nach der Aenderung von `total` war die neue Summe "ohne
        # Herkunft" — obwohl sie die Zahl ist, die der Lauf erzeugt.
        # Ein Guard gegen Zahlen ohne Herkunft, der die eigene neue Zahl
        # nicht kennt, ist ein Guard gegen Veraenderung. Deshalb: die
        # Zerlegung des aktuellen `Checks` kommt hinzu, nicht als Literal,
        # sondern als die vier Groessen, die `_status_line` druckt.
        self_checks = 0
        for _ln in src.splitlines():
            if "Checks(" in _ln:
                self_checks += 1
        measured |= {self_checks}
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
            _line_ctx: str | None = None
            for raw in text_doc.splitlines():
                _hm = re.match(r"^#{1,6}\s*(?:§[\d.]+\s*)?(?:Wave|Welle)\s*(\d+(?:\.\d+)?)", raw)
                if _hm:
                    _line_ctx = _hm.group(1)
                one = Report()
                # §A-NE: die Zeile **plus** der Wellenindex der Datei.
                # Der Index ist Teil des Pruefbereichs, nicht Nachbartext:
                # er enthaelt nur `Wave N -> testpfad`-Paare, und die
                # Zaehlung je Zeile haengt seither nicht mehr an den
                # Nachbarzeilen — sonst waere `check_counts` nicht
                # mehr zeilenlokal und der Nenner wanderte.
                check_counts(raw, w_doc, p_doc, one, root_repo,
                             wave_index=_wave_script_index(text_doc),
                             wave_ctx=_line_ctx)
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
            # §A-NP (Runde 51): `tests_ohne_skript` darf **legitim** 0 sein,
            # wenn jede Suite-Zusage einen Skriptbezug hat — das ist der
            # Zielzustand, nicht ein Defekt. Die beiden anderen Regeln
            # duerfen nie 0 sein (jede Datei hat Wellen und Agentenzahlen).
            for rule in ("waves", "agents<50"):
                if rep.skips.get(rule, 0) == 0:
                    failures.append(f"Ausschlussregel {rule!r} zaehlt 0")
            _unref = [c for c in rep.claims if c[0] == "suite:ohne-skript"]
            if rep.skips.get("tests_ohne_skript", 0) != len(_unref):
                failures.append(
                    "Ausschlussregel 'tests_ohne_skript' zaehlt "
                    f"{rep.skips.get('tests_ohne_skript', 0)}, Zusagen "
                    f"ohne Skript: {len(_unref)}")
            if _unref and "tests_ohne_skript" not in rep.skips:
                failures.append("Zusagen ohne Skript, aber kein Skip — still")
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
        line = _status_line(Checks(223, 210, 0), 0, Path("/tmp/_einheit"))
        # §A-NM (Runde 51): ohne Baum gibt es **keine Zahl** — nicht den
        # Text „KEIN BAUM" mit einer Null daneben. `None` ist die
        # Reparatur; ein besserer Kommentar war die alte Falle (R47).
        if _status_line(Checks(223, 210, 0), 0, None) is not None:
            failures.append("Kopfzeile ohne root liefert eine Zahl statt None")
        # §A-MF (Runde 43): die Formprobe braucht ihren **Partner**. Der
        # Beweis, dass `root` wirkt, ist das Paar, nicht die Haelfte: ohne
        # `root` steht kein Bezug in der Zeile, mit `root` steht er da.
        # §A-MK (Runde 44): dieser Zwilling belegte nur **Durchreichung**.
        # `223` kam zweimal als Argument herein; dass die Zahl gleich
        # bleibt, war eine Tautologie, keine Messung. Die Zahl, deren
        # Abhaengigkeit von `root` zaehlt, ist die **gezaehlte** aus der
        # Kette — zweimal gezaehlt, einmal eigener Baum, einmal Klon.
        # Der Name des Tests sagt jetzt, was er prueft.
        line_pair = _status_line(Checks(223, 210, 0), 0, Path("/tmp/_paar"))
        line_noroot = _status_line(Checks(223, 210, 0), 0, None)
        # Der Zwilling muss den Bezug **haben**, der Andere darf weder
        # Zahl noch Bezug tragen. Vorher pruefte diese Zeile `line`
        # (die Form **mit** root) gegen "ohne root" — ein Fehlalarm.
        if line_noroot is not None or (line_pair is None
                                       or "Bezug: root=" not in line_pair):
            failures.append("Kopfzeile ohne root nennt einen Bezug")
        if "Bezug: root=/tmp/_paar" not in line_pair:
            failures.append("Kopfzeile mit root nennt ihn nicht")
        # Die Formatprobe ist **Format**, nicht Wirkung — das steht jetzt
        # im Namen der Meldung. Die Wirkung prueft der Zaehlzwilling unten.
        if "223 Angaben geprueft" not in line_pair:
            failures.append(
                "Formatprobe: Partner aendert die Eingabezahl (erwartet: "
                "nur der Bezug)")


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
            got = _snapshot_path()
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

        # 22. Der Zaehler selbst (§A-KC). `Checks` bewacht die Zeile; ob
        #     `checked == n` gilt, weiss nur die Schleife. Runde 23 sass in
        #     der Zahl, nicht im Wort.
        rep_c = Report()
        if rep_c.checked != 0:
            failures.append(f"Zaehler startet nicht bei 0: {rep_c.checked}")
        n_ok = 5
        for _ in range(n_ok):
            rep_c.ok()
        if rep_c.checked != n_ok:
            failures.append(f"ok() zaehlt nicht eins: {rep_c.checked} != {n_ok}")
        rep_c.fail(None, "k", "d", "r")
        if rep_c.checked != n_ok + 1:
            failures.append(
                f"fail() ist keine Pruefung: {rep_c.checked} != {n_ok + 1}")
        # Gegenprobe (§A-JW): was NICHT lief, darf nicht zaehlen.
        before = rep_c.checked
        rep_c.skip("regel")
        rep_c.skip("regel", 3)
        rep_c.env("skript.py")
        if rep_c.checked != before:
            failures.append(
                f"skip()/env() erhoehen den Zaehler: {rep_c.checked} != {before}")
        if rep_c.skips.get("regel") != 4:
            failures.append(f"skip() zaehlt nicht: {rep_c.skips}")
        # Und: der Zaehler eines frischen Reports ist unabhaengig (geteilter
        # Zustand, Annahme 2 — hier als Probe, nicht als Behauptung).
        if Report().checked != 0:
            failures.append("Report() teilt den Zaehler mit dem Vorgaenger")

        # 23. Die Identitaet `total = checked + excluded` (§A-JX). Vorher
        # 24. Annahme 2 braucht eine Probe (§A-KE): zwei Faelle hinter-
        #     einander, die **denselben** Zustand setzen — der zweite darf
        #     den ersten nicht sehen. Runde 32 war gruen, weil die Mutation
        #     nichts aenderte; 16c prueft cwd, nicht den geteilten Speicher.
        #     Also: Zustand setzen, NICHT zuruecksetzen, und pruefen, dass
        #     der zweite Fall ihn noch sieht — dann zuruecksetzen und
        #     pruefen, dass er weg ist. Beides zusammen beweist, dass der
        #     Reset wirkt **und** dass die Probe ihn sehen kann.
        _SNAPSHOT_SEEN[0] = root / "fall_a"
        _test_results["a"] = 1
        _ROOT_CACHE[Path("/fall_a")] = Path("/fall_a")
        seen_by_second = (_SNAPSHOT_SEEN[0] is not None
                          and "a" in _test_results
                          and bool(_ROOT_CACHE))
        if not seen_by_second:
            failures.append(
                "Probe blind: Zustand aus Fall A ist fuer Fall B nicht sichtbar")
        reset_all()
        if (_SNAPSHOT_SEEN[0] is not None or _test_results or _ROOT_CACHE
                or _SNAPSHOT_CACHE):
            failures.append(
                f"Reset nach Fall A unvollstaendig: "
                f"{_SNAPSHOT_SEEN[0]}, {_test_results}, {list(_ROOT_CACHE)}")
        # Gegenprobe (§A-JW): zweimal derselbe Ablauf, gleiches Ergebnis.
        # Ein Reset, der nur beim ersten Mal wirkt, ist der Fehler aus §1.
        for zyklus in (1, 2):
            _SNAPSHOT_SEEN[0] = root / "fall_b"
            _test_results["b"] = zyklus
            reset_all()
            if _SNAPSHOT_SEEN[0] is not None or _test_results:
                failures.append(f"Reset wirkt nur im Zyklus {zyklus}")
            # Dritter Schritt (§A-KI): nach dem Reset **wieder setzbar**.
            # Ein Reset, der das Objekt entfernt statt leert, ist von einem,
            # der leert, im ersten Schritt nicht zu unterscheiden — erst der
            # zweite Zugriff scheitert dann.
            try:
                _SNAPSHOT_SEEN[0] = root / "fall_c"
                _test_results["c"] = zyklus
                _ROOT_CACHE[Path("/fall_c")] = Path("/fall_c")
                _SNAPSHOT_CACHE[Path("/fall_c")] = Path("/fall_c")
            except (NameError, TypeError, KeyError, AttributeError) as e:
                failures.append(f"Zustand nach Reset nicht wieder setzbar: {e}")
            reset_all()

        # 25. Der Schreiber leert beide Caches (§A-KD). Zwei Caches zeigen
        #     auf dieselbe Datei; wer schreibt und sie stehen laesst, liest
        #     beim naechsten Lauf den alten Stand. Die Invariante steht am
        #     Schreiber, nicht beim Aufrufer — der weiss nichts von Caches.
        _reset_root_cache()
        _snapshot_path(root)                   # Ort-Cache fuellen
        _snapshot_path(root)                   # Inhalt-Cache fuellen
        if not _SNAPSHOT_CACHE:
            failures.append("Vorbedingung: Snapshot-Cache war nicht gefuellt")
        _save_count_snapshot(rep_c.checked, "selbsttest", root=root)
        if _SNAPSHOT_CACHE or _ROOT_CACHE:
            failures.append(
                f"Schreiber laesst Caches stehen: "
                f"{list(_SNAPSHOT_CACHE)} / {list(_ROOT_CACHE)}")

        # 26. Alle Kategorien in einem Report (§A-KH). `claim()` fiel aus
        #     `total`, waehrend die Zeile "Angaben gezaehlt" sagte — Runde 23
        #     eine Ebene hoeher: `total` gegen `total`.
        rep_all = Report()
        rep_all.ok()                                  # 1 Pruefung
        rep_all.fail(None, "k", "d", "r")             # 2 Pruefungen
        rep_all.skip("regel", 3)                      # 3 Ausschluesse
        rep_all.claim("feld", 9)                      # 1 Zusage
        c_all = Checks(rep_all.checked, sum(rep_all.skips.values()),
                       len(rep_all.claims))
        if c_all.n != 2:
            failures.append(f"geprueft falsch: {c_all.n} != 2")
        if c_all.excluded != 3:
            failures.append(f"ausgeschlossen falsch: {c_all.excluded} != 3")
        if c_all.measured != 5:
            failures.append(f"measured falsch: {c_all.measured} != 5")
        if c_all.total != 6:
            failures.append(
                f"total zaehlt Zusagen nicht: {c_all.total} != 6")
        # Gegenprobe (§A-JW): derselbe Report **ohne** claim() — `total`
        # muss sich um die Zusagen aendern, nicht um die Messung.
        c_no = Checks(rep_all.checked, sum(rep_all.skips.values()), 0)
        if c_no.total != 5 or c_no.total == c_all.total:
            failures.append(
                f"claim() veraendert total nicht: {c_no.total} vs {c_all.total}")
        if c_no.measured != c_all.measured:
            failures.append("claim() veraendert measured — falscher Eimer")
        line_all = _status_line(c_all, 0, Path("/tmp/_all"))
        for need in ("2 Angaben geprueft", "6 Angaben gezaehlt",
                     "5 gemessen", "1 Zusagen"):
            if need not in line_all:
                failures.append(f"Zeile ohne {need!r}: {line_all!r}")
        # Ohne Zusagen: die Klammer nennt `0 Zusagen` — das ist eine Zahl,
        # keine Behauptung. Verboten ist nur der Zusatz **ausserhalb** der
        # Klammer, der eine vierte Einheit vortaeuscht (§A-KX).
        line_no = _status_line(c_no, 0, Path("/tmp/_no"))
        if "0 Zusagen" not in line_no or line_no.count("Zusagen") != 1:
            failures.append(f"Zeile verschweigt null Zusagen: {line_no!r}")

        # 27. Der Cache ist auf `root` geschluesselt (§A-KJ). Runde 35 hat
        #     "3 Abfragen -> 1 git-Aufruf" mit **einem** root gemessen. Der
        #     Fall, der zaehlt, ist der zweite: zwei roots, zwei Ergebnisse.
        #     Sonst ist "auf root geschluesselt" eine Annahme — und der
        #     Fund aus Runde 38 waere nicht der fehlende Parameter gewesen,
        #     sondern der Cache.
        other_root = root / "zweiter_root"
        other_root.mkdir(exist_ok=True)
        _reset_root_cache()
        ra = repo_root(root)
        rb = repo_root(other_root)
        if ra == rb:
            failures.append(f"Cache ignoriert root: {ra} == {rb}")
        if len(_ROOT_CACHE) != 2:
            failures.append(
                f"Cache hat nicht zwei Eintraege: {list(_ROOT_CACHE)}")
        # Gegenprobe (§A-JW): derselbe root zweimal -> gleicher Wert, ein
        # Eintrag. Sonst ist der Cache entweder wirkungslos oder waechst.
        _reset_root_cache()
        r1 = repo_root(root)
        r2 = repo_root(root)
        if r1 != r2 or len(_ROOT_CACHE) != 1:
            failures.append(
                f"Cache waechst bei gleichem root: {list(_ROOT_CACHE)}")
        _reset_root_cache()
        # Gegenprobe: der Schreiber muss wirklich geschrieben haben
        got_snap = _load_count_snapshot(root)
        if not got_snap or got_snap.get("checked") != rep_c.checked:
            failures.append(f"Schreiber hat nicht geschrieben: {got_snap}")
        _reset_root_cache()

        # 28. Der zweite `rg` gegen fehlendes `root` (§A-KK/KO/KQ/KS/KT).
        #     Runde 38s Suche fragte nach `Path.cwd()` — dem **Fund**. Der
        #     Fehler ist "ein Aufrufer reicht `root` nicht durch", und die
        #     Menge ist groesser: beim ersten echten Lauf (`rg`-Lauf R39)
        #     dreizehn Stellen,
        #     darunter `main`. Geprueft wird am AST — mit rotem Zwilling,
        #     sonst ist es ein Pruefer, der prueft, dass er nichts findet.
        viol = _root_forwarding_violations()
        if viol:
            failures.append(f"root nicht durchgereicht: {viol[:3]}")
        # §A-NI (Runde 49): die 18er-Erwartung war eine **Baseline** —
        # eine Zahl, die den Zustand festschreibt und jede echte
        # Reparatur falsch macht. Ersetzt durch die Rolle: ein
        # Default-Zweig in einem Selbsttest ist kein Verstoss, einer im
        # Produktionscode schon. Die Zahl faellt weg, nicht die Pruefung.
        # 28b. Die Kette (§A-LJ/§A-LK). Der Glieder-Pruefer oben sieht nur
        #      Funktionen mit `root`. `_resolve_test_root` hiess `doc_root`
        #      und rief `git rev-parse` ohne `cwd` — `check_claude_md.py
        #      /tmp/klon` las die Tests des eigenen Repos. Gemessen wird die
        #      Wirkung, nicht der Name: kein `git`-Aufruf ohne `cwd` oder
        #      genannten Pfad in dieser Datei.
        prod = Path(__file__).read_text(encoding="utf-8")
        open_git = _git_callers_without_cwd(prod)
        if open_git:
            failures.append(f"git ohne cwd: {open_git[:3]}")
        # 28c. Der Groessen-Guard der Ausnahmen (§A-KZ). Die Ableitung ist
        #      zirkulaer per Konstruktion: wer Anker **und** Marker loescht,
        #      verschwindet. Der Guard faengt genau das — und nur, weil
        #      `_PROBE_ANCHOR_EXPECTED` nicht aus dem Code kommt.
        # Der Marker wird zur Laufzeit gebaut: stünde er hier als Literal,
        # zählte diese Zeile sich selbst und die Probe wäre blind.
        mark = "  # " + "\u00a7A-KR"
        quiet = prod.replace(mark + " bewusst: Default-Zweig", "")
        quiet = quiet.replace(mark, "")
        _prod_after = [a for a in _probe_anchors(quiet) if "_status_line" not in a]
        if len(_prod_after) == _PROBE_ANCHOR_EXPECTED:
            failures.append(
                "Groessen-Guard blind: geloeschte Produktions-Marker bleiben "
                f"bei {_PROBE_ANCHOR_EXPECTED}")
        # 32. §A-MD: **das Instrument im Messbereich.** Drei Runden, drei
        #     Selbstmitzaehlungen, dreimal einzeln gefixt:
        #       R40 Ankerliste zaehlte die Abschrift (mehr Anker als Code)
        #       R41 _probe_anchors zaehlte den eigenen Kommentar (zwei zuviel)
        #       R41 die Wache zaehlte den eigenen Marker (blind)
        #     Der gemeinsame Nenner: ein Messinstrument, das seine eigene
        #     Quelle liest, findet sich selbst. Ein Preset, vier Instrumente.
        #     Marker **ausschliesslich** im Kommentar -> null Anker.
        anch = "\u00a7A" + "-KR-ANCHOR"
        if _probe_anchors("# " + anch + " nur im Kommentar\n"):
            failures.append(
                "_probe_anchors zaehlt einen Kommentar als Anker")
        #     §A-MG: die Prosa-Marke allein ist **kein** Anker — sonst
        #     bedeutet ein Wort zwei Dinge (Runde 23, am Marker selbst).
        if _probe_anchors("x = g()  # \u00a7A-KR Erklaerung\n"):
            failures.append(
                "_probe_anchors zaehlt den Prosa-Marker als Anker")
        if _probe_anchors("x = g()  # " + anch + " bewusst\n") != (
                "x = g()  # " + anch + " bewusst",):
            failures.append("_probe_anchors findet echten Anker nicht")
        #     _git_callers_without_cwd gegen sich selbst: die eigene Datei
        #     enthaelt keinen offenen git-Aufruf — und eine Probedatei, die
        #     nur einen Kommentar nennt, zaehlt nicht.
        if open_git:
            pass          # oben schon gemeldet
        if _git_callers_without_cwd("# subprocess.run(['git','status'])\n"):
            failures.append(
                "_git_callers_without_cwd zaehlt einen Kommentar als Aufruf")
        if _git_callers_without_cwd(
                "import subprocess\nsubprocess.run(['git','x'])\n") == []:
            failures.append("_git_callers_without_cwd findet den Zwilling nicht")
        #     Und der Report: zwei roots, zwei Bezugszeilen (§A-MA).
        line_own = _status_line(Checks(1), 0, Path("/tmp/a"))
        #                          ^ Zwillingsprobe: zaehlt den Bezug
        #                          nicht als Ausnahme (siehe unten)
        line_two = _status_line(Checks(1), 0, Path("/tmp/b"))
        if "/tmp/a" not in line_own or "/tmp/b" not in line_two:
            failures.append(f"Kopfzeile nennt den Bezug nicht: {line_own!r}")
        if line_own == line_two:
            failures.append("Kopfzeile gleich fuer zwei roots")
        # Die Presets der Prueflogik, an Mini-Quellen statt an der
        # Produktionsdatei — so ist der Zwilling reproduzierbar. **Ein
        # Preset je Fehlerklasse**, nicht fuenf insgesamt (§A-LB): die
        # fuenf Loecher in Runde 39 waren verschieden, und ein Preset,
        # das zwei zugleich trifft, verdeckt beim naechsten Umbau eins.
        # §A-NJ (Runde 49): `_binds_root` fragt jetzt nach dem **Lesepfad**,
        # nicht nach dem Namen. Die Presets muessen also ein `root` zeigen,
        # das wirklich gelesen wird — sonst hat die Funktion nichts zu
        # reichen, und „kein Verstoss" ist die richtige Antwort. `rd` ist
        # dieser Leseort: `(root / 'x').read_text()`.
        _RD = "    rd = (root / 'x').read_text()\n"
        pairs = [
            # K1: `Path.cwd()` statt `root` (Ausdruck statt Name)
            ("def f(root):\n" + _RD + "    return g(Path.cwd())\n"
             "def g(root):\n    return root\n", True, "K1 cwd als Argument"),
            # K2: gar kein Argument
            ("def f(root):\n" + _RD + "    return g()\n"
             "def g(root):\n    return root\n", True, "K2 fehlendes Argument"),
            # K3: Argument an falscher Position (root ist Parameter 2)
            ("def f(root):\n" + _RD + "    return g(1)\n"
             "def g(x, root):\n    return root\n", True, "K3 falsche Position"),
            # K4: Aufruf in verschachteltem def darf NICHT als Verstoss
            #     der Elternfunktion gelten
            ("def f(root):\n" + _RD + "    def inner():\n        return g()\n"
             "    return g(root)\n"
             "def g(root):\n    return root\n", False, "K4 Kind-def"),
            # K5: Alias einer **Fremdquelle** ist kein root
            ("def f(root):\n" + _RD + "    r = Path.cwd()\n    return g(r)\n"
             "def g(root):\n    return root\n", True, "K5 Fremd-Alias"),
            # K6: Alias von root ist Uebergabe
            ("def f(root):\n" + _RD + "    r = root\n    return g(r)\n"
             "def g(root):\n    return root\n", False, "K6 root-Alias"),
            # K7: echte Uebergabe
            ("def f(root):\n" + _RD + "    return g(root)\n"
             "def g(root):\n    return root\n", False, "K7 korrekt"),
            # K8 (§A-NJ): die Eigenschaft ist der Lesepfad, nicht der Name.
            #     `root_` traegt denselben Wert und wird ignoriert.
            ("def f(root_):\n    rd = (root_ / 'x').read_text()\n"
             "    return g()\n"
             "def g(root):\n    return root\n", True, "K8 anderer Name, gelesen"),
            # K9 (§A-NJ): umgekehrt — `root` heisst `root`, wird aber nie
            #     als Pfad gelesen. Dann hat die Funktion nichts zu reichen.
            ("def f(root):\n    return g()\n"
             "def g(root):\n    return root\n", False, "K9 Name ohne Lesepfad"),
        ]
        for src, expect_bad, label in pairs:
            got = _forwarding_violations(src)
            if bool(got) != expect_bad:
                failures.append(
                    f"Pruefer {label}: {bool(got)} statt {expect_bad}")
        # 29. Die Kette (§A-LJ). Der Glieder-Pruefer sieht nur Funktionen
        #     mit `root`, die es nicht weitergeben. `_resolve_test_root`
        #     hiess `doc_root` und rief `git rev-parse` ohne `cwd` — zwei
        #     Glieder ohne Parameter, beide unsichtbar. Gemessen: der
        #     Report mit fremdem `root` las die Tests des eigenen Repos.
        clone = root / "klon"
        (clone / "order_execution_engine" / "ops").mkdir(parents=True, exist_ok=True)
        (clone / "CLAUDE.md").write_text("# Klon\n", encoding="utf-8")
        (clone / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md").write_text(
            "Klon\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(clone)], check=False,
                       capture_output=True)
        subprocess.run(["git", "-C", str(clone), "-c", "user.email=t@t",
                        "-c", "user.name=t", "add", "-A"], check=False,
                       capture_output=True)
        subprocess.run(["git", "-C", str(clone), "-c", "user.email=t@t",
                        "-c", "user.name=t", "commit", "-qm", "k"], check=False,
                       capture_output=True)
        # Gegenprobe (§A-JW): zwei roots, zwei Ergebnisse.
        got_clone = _resolve_test_root(clone)
        got_self = _resolve_test_root(root)
        if got_clone.resolve() == got_self.resolve():
            failures.append(
                f"Kette offen: _resolve_test_root ignoriert root "
                f"({got_clone} == {got_self})")
        if got_clone.resolve() != clone.resolve():
            failures.append(
                f"_resolve_test_root(clone) != clone: {got_clone}")
        # und der Dokumentationsort: fremder Klon, fremder sha.
        doc_clone = _doc_tracked(clone)
        if not doc_clone.startswith("committet"):
            failures.append(f"_doc_tracked(clone) nicht committet: {doc_clone}")
        if doc_clone == _doc_tracked(root) and _doc_tracked(root).startswith("committet"):
            failures.append("_doc_tracked nennt fuer beide Repos denselben sha")
        # §A-NJ (Runde 49): der stille Zwilling muss ein **gelesenes**
        # `root` tragen. `def f(root): return g()` hat nichts zu reichen —
        # seit die Eigenschaft der Lesepfad ist, ist `[]` dort die richtige
        # Antwort (K9 unten). Der Zwilling ist K2 mit einer Lesezeile.
        blind_probe = ("def f(root):\n"
                       "    rd = (root / 'x').read_text()\n"
                       "    return g()\n"
                       "def g(root):\n    return root\n")
        if not _forwarding_violations(blind_probe):
            failures.append("Pruefer ist stillgruen (Zwilling mit gelesenem "
                            "root liefert [])")
        # §A-LH: aber die Presets oben sind **eigene** Quellen. Die Frage
        # "findet er es in *dieser* Datei?" braucht dieselbe Antwort:
        # eine Kopie der Produktionsdatei mit einem eingebauten Fehler
        # muss anschlagen. Ein Pruefer, der nur auf Fixtures reagiert,
        # ist ein Fixture-Pruefer.
        prod_src = Path(__file__).read_text(encoding="utf-8")
        # §A-NI (Runde 49): der Anker ist **Produktionscode** und die
        # richtige Funktion. Vier Anker scheiterten vorher, jeder an einer
        # anderen Bedingung — alle vom Selbsttest gefunden, keiner vom
        # Hinsehen: `_self_test_count_delta` (Rolle greift), `main` als
        # `_delta_line`-Stelle (kein `root`-Parameter), `chain` (Closure,
        # kein Parameter), `run(...)` (Referenz statt Aufruf). Und der
        # fuenfte, `replace(..., 1)`, traf den **ersten** von drei
        # Treffern — `chain`. Genommen wird der **letzte**, in `main`, wo
        # `root` per Zuweisung gebunden ist und `_binds_root` es sieht.
        # §A-NL (Runde 50): ein Anker, der mehrfach passt, ist kein Anker.
        # `rfind` legte den Mehrfachtreffer still — dieselbe Klasse wie
        # `replace(..., 1)`. Der Anker umfasst **zwei** Zeilen, weil eine
        # einzelne in allen Pipelines steht; nur `main` hat diese
        # Reihenfolge, und dort ist `root` per Zuweisung gebunden.
        _anchor = ("    check_line_counts(text, root, rep)\n"
                   "    check_dead_refs(text, root, rep)")
        # §A-NL: dieselbe Zaehlung wie `_anchor_report` — Zitate
        # (Kommentar, `_anchor`-Definition) sind keine Paßstellen.
        _n = _anchor_count(prod_src, _anchor)
        if _n != 1:
            failures.append(f"Anker paßt {_n}x (muß 1 sein): {_anchor!r}")
        _repl = ("    check_line_counts(text, Path(), rep)\n"
                 "    check_dead_refs(text, Path(), rep)")
        broken = prod_src.replace(_anchor, _repl, 1)
        if broken == prod_src:
            failures.append("Anker fuer Produktions-Probe fehlt")
        elif not _forwarding_violations(broken):
            failures.append("Pruefer findet eingebauten Fehler nicht in Produktion")
        # Die Zeile liest den Zaehler an genau einer Stelle.
        line_c = _status_line(Checks(rep_c.checked, rep_c.skips.get("regel", 0)), 0,
                              Path("."))
        if f"{n_ok + 1} Angaben geprueft" not in line_c:
            failures.append(f"Zeile liest den Zaehler nicht: {line_c!r}")

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
        line_ident = _status_line(c1, 0, Path("/tmp/_i1"))
        if "21 Angaben geprueft" not in line_ident or \
                "231 Angaben gezaehlt" not in line_ident or \
                "210 ausgeschlossen" not in line_ident:
            failures.append(f"Zeile rechnet nicht aus dem Typ: {line_ident!r}")
        line_ident3 = _status_line(c3, 0, Path("/tmp/_i3"))
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
        try:
            del c_mut.n
            failures.append("Checks ist loeschbar (__delattr__ fehlt)")
        except AttributeError:
            pass
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
            _status_line(21, 0)  # type: ignore[arg-type]
            failures.append("_status_line akzeptiert int — die Einheit fehlt")
        except TypeError:
            pass
    return failures


def _resolve_test_root(doc_root: Path | None = None) -> Path:
    """Wo liegen die Testskripte — `doc_root`, oder wo `git` sie findet?

    §A-LJ (Runde 41): **die Kette.** Der Glieder-Pruefer aus Runde 39
    findet nur Funktionen, die `root` haben und es nicht weitergeben. Hier
    gab es kein `root`: `_resolve_test_root(doc_root)` nahm den Ort des
    Dokuments, rief aber `git rev-parse --show-toplevel` **ohne `cwd`** —
    also im Prozess-Arbeitsverzeichnis. `check_claude_md.py /tmp/klon`
    prueft dann die Tests des **eigenen** Repos. Zwei Glieder ohne
    Parameter, jedes fuer sich unsichtbar:

        check_tests(text, root)             hat root
        -> _resolve_test_root(root)         hat root, reicht es nicht
        -> git rev-parse (ohne cwd)         liest das Default-Repo

    Das erste Glied haette der Pruefer gesehen, wenn `_resolve_test_root`
    einen Parameter `root` traege — es traegt aber `doc_root`. Ein Name,
    zwei Mengen: der Sonderfall aus Runde 23, diesmal beim Parameter.
    """
    import os
    env = os.environ.get("AGENT_X_TEST_ROOT")
    if env:
        return Path(env).resolve()
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(repo_root(doc_root)),      # §A-LJ: das gefragte Repo
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return repo_root(doc_root)


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


def _self_test_akte_write_mode() -> list[str]:
    """§A-NS (Runde 52): meldet der Schreibmodus-Prüfer **und** schweigt er?

    Vier Fälle, zwei rot, zwei grün. Der rote Fall ist der Vorfall: der
    Schreibvorgang, der die Akte auf ihr letztes Bruchstück brachte.
    """
    import tempfile
    out: list[str] = []
    cases = (
        ("write_text", 'p = _R / "ops" / "TAG7_ABNAHME.md"\np.write_text("x")\n', 1),
        ("open-w", 'import pathlib\n'
                  'p = pathlib.Path("ops") / "TAG7_ABNAHME.md"\n'
                  'open(p, "w").write("x")\n', 1),
        ("guard", 'from akte_guard import guarded_write\n'
                  'guarded_write(_R / "TAG7_ABNAHME.md", "x")\n', 0),
        ("fremde-datei", 'open("README.md", "w").write("x")\n', 0),
    )
    for label, body, expect in cases:
        root = Path(tempfile.mkdtemp(prefix="wm_"))
        (root / "scripts").mkdir()
        (root / "scripts" / "tool.py").write_text(
            "_R = __import__('pathlib').Path('.')\n" + body, encoding="utf-8")
        rep = Report()
        check_akte_write_mode(root, rep)
        got = len(rep.problems)
        if got != expect:
            out.append(f"schreibmodus ({label}): {got} Meldungen, "
                       f"erwartet {expect}")
    return out


def check_prose_fractions(root: Path, rep: Report) -> None:
    """Stimmt `Z/N (P%)` im Fließtext mit der Division? (§A-ZB, Runde 53)

    §A-ZA: die Akte enthielt den Satz „die Gesamtzahl ist gefallen".
    Der Anteil war **gestiegen**. Gefunden hat das nicht ein Prüfer,
    sondern der Leser. Ein Prüfer über Prosa wäre teuer; ein Prüfer über
    **Bruchzahlen** ist eine Division.

    Rot ist jede Stelle, an der `Z/N` und `(P%)` zusammenstehen und
    `100*Z/N` mehr als eine Prozentstelle von `P` abweicht. Die Toleranz
    ist eine Stelle: sie deckt `floor` und `round`, nicht einen Rechenfehler.

    **Grenze, benannt:** erkannt wird nur, was in **einem** Satz als
    `Z/N (P%)` steht oder als `(P%)`-Klammer direkt hinter dem Bruch.
    Zwei Prozentzahlen ohne ihre Brüche daneben sieht kein Prüfer — und
    kann es nicht, weil die Operanden fehlen.
    """
    import re
    pair = re.compile(
        r"(?<![\d.])(\d{1,5})\s*/\s*(\d{1,5})(?![\d.])\s*[(\[]?\s*(\d{1,3})\s*%")
    for path in (root / "CLAUDE.md",
                 root / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        # §71.59b (Runde 53): Codeblöcke sind **Syntax**, keine Behauptung.
        # Dort steht ein Beispiel, und ein Gegenbeispiel ist dort zulässig —
        # im Fließtext nicht. Diese eine Ausnahme ist der Unterschied
        # zwischen einem Prüfer, der Beispiele versteht, und einem, der
        # Zahlen zählt.
        # §A-ZP (Runde 54): der Korrekturblock trägt einen **Selektor**
        # (`Korrektur zu §71.59`), keinen Hash. Ein Literal driftet, ein
        # abgeleiteter Wert nicht — und der Prüfer rechnet den Hash im
        # **selben Artefakt**, in dem er den Block liest. Eine Diskrepanz
        # ist damit baulich unmöglich, nicht nur behoben.
        #
        # Dieselbe Entscheidung wie `global` (R50) und `ast` (R51):
        # nicht speichern, was ableitbar ist.
        sel = _korrektur_selectors(text)
        fenced = False
        cur_block = ""
        cur_title = ""
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.startswith("### "):
                cur_block = line
                cur_title = line
            if line.lstrip().startswith("```"):
                fenced = not fenced
                rep.ok()
                continue
            if fenced:
                rep.ok()       # im Block: Beispiel, keine Behauptung
                continue
            # §A-ZQ: eine Korrektur, die den falschen Wert zitieren würde,
            # wird selbst zum Befund. Deshalb gilt: der Block, den ein
            # Korrekturblock adressiert, wird gegen den Block **geprüft,
            # in dem er steht** — und ein Selektor auf einen unbekannten
            # Block ist offen, nicht quittiert.
            cur_sel = _selector_in(cur_title)
            if cur_sel and cur_sel not in sel["targets"]:
                rep.fail(lineno, "Korrektur zu unbekanntem Block",
                         cur_sel, "Selektor trifft keinen Block",
                         state="offen")
                break
            # §A-ZR: Ziel-Quittung steckt in `_is_citation` (der Prüfer soll
            # **eine** Stelle haben, an der „quittiert" entschieden wird).
            # Eine zweite Variable hier wäre ein zweiter Wahrheitsort.
            for m in pair.finditer(line):
                z, n, p = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if n == 0:
                    rep.fail(lineno, "Bruch mit Nenner 0", m.group(0),
                             "unmoeglich")
                    continue
                want = 100.0 * z / n
                if abs(want - p) <= 1.0:
                    rep.ok()
                    continue
                # §A-ZM: Zitat oder Behauptung? Ein Zitat nennt seine
                # Herkunft (`laut`/`zitiert`/`steht`) oder steht in einem
                # Quittungsblock. Beides wird **gemeldet** — nur die
                # Kopfzeile unterscheidet (`offen` / `quittiert`).
                if _is_citation(line, cur_block, sel):
                    rep.fail(lineno, "Bruch und Prozent passen nicht (zitiert)",
                             m.group(0),
                             f"echt {want:.1f}% ({z}/{n})", state="quittiert")
                    continue
                rep.fail(lineno, "Bruch und Prozent passen nicht",
                         m.group(0), f"echt {want:.1f}% ({z}/{n})")
            # Jede Zeile ist geprueft, auch ohne Bruch: was nicht dasteht,
            # ist nicht falsch. Der Zaehler zaehlt die Zeilen, die der
            # Pruefer gelesen hat — bei `_akt_block` ist es dasselbe Muster.
            if not pair.search(line):
                rep.ok()


def _selector_in(title: str) -> str | None:
    """`### §71.59c — Korrektur zu §71.59` → `§71.59`. Sonst `None`.

    §A-ZP: der Selektor ist ein **Verweis**, kein Wert. Er wird im selben
    Text aufgelöst, in dem er steht. Der frühere Hash konnte driften; ein
    Verweis auf einen Blocknamen driftet nur, wenn der Block umbenannt
    wird — und dann ist es eine sichtbare Umbenennung, keine stille.
    """
    import re
    m = re.search(r"Korrektur zu\s+(§[\d.]+[a-z]?)", title)
    return m.group(1) if m else None


def _block_key(title: str) -> str | None:
    """`### §71.59 — …` → `§71.59`. Die Identität eines Blocks ist seine
    Nummer, nicht seine Überschrift: der Titel darf sich ändern, ohne die
    Quittung zu brechen (§A-ZR)."""
    import re
    m = re.match(r"###\s+(§[\d.]+[a-z]?)", title)
    return m.group(1) if m else None


def _korrektur_selectors(text: str) -> dict[str, set[str]]:
    """Welche Blöcke ein Korrekturblock adressiert — und ob er existiert.

    §A-ZQ: der Auflöser hat zwei Eingänge:
      `targets` — Selektoren mit **vorhandenem** Zielblock (quittiert)
      `unknown` — Selektoren ohne Ziel (offen: ein Verweis ins Leere)

    Öffentlich geprüft, weil die Gegenprobe („Block entfernen ⇒ rot") nur
    dann etwas belegt, wenn sie denselben Auflöser benutzt wie der Lauf.
    """
    import re
    titles: set[str] = set()
    for line in text.splitlines():
        if line.startswith("### "):
            m = re.match(r"###\s+(§[\d.]+[a-z]?)", line)
            if m:
                titles.add(m.group(1))
    targets: set[str] = set()
    unknown: set[str] = set()
    selff: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("### "):
            continue
        s = _selector_in(line)
        if s is None:
            continue
        (targets if s in titles else unknown).add(s)
        if _block_key(line) == s:
            selff.add(s)
    return {"targets": targets, "unknown": unknown, "self": selff}



def _is_citation(line: str, block_title: str = "",
                 sel: dict[str, set[str]] | None = None) -> bool:
    """Ist diese falsche Zahl ein **Zitat** oder eine **Behauptung**?

    §A-ZM (Runde 54): dieselbe Prädikat-Frage wie `_path_is_asserted_not_read`
    in Runde 51, ein anderes Objekt. Ein Fund, den die Akte selbst als
    Fund zitiert, darf den Prüfer nicht dauerhaft rot halten — sonst
    schaltet man nach sechs Runden den Prüfer ab, nicht die Zahl.

    Zitat heißt, erkennbar an der **Zeile**:

      die Zahl steht in Anführungszeichen (`…` oder ``…``),
      **und** die Zeile nennt ihre Rolle (`laut`, `zitiert`, `steht`)

    oder an der **Umgebung**: der Block trägt `Korrektur zu §<ziel>`, und
    dieses Ziel **existiert im selben Text** (`sel["targets"]`). Ein
    Selektor ins Leere quittiert nichts — er ist selbst offen.

    Grenze, benannt: eine Korrektur soll den falschen Wert **nicht
    wiederholen**. Tut sie es doch in Anführungszeichen mit Rolle, ist
    das ein Zitat — gemeldet, quittiert, sichtbar. Eine Regel sparen ist
    besser, aber ein Zitat zu verbieten, das keiner mehr braucht, wäre
    die vierte Ausnahme.
    """
    import re
    quoted = (bool(re.search(r"[`„\"']\s*\d{1,5}\s*/\s*\d{1,5}[^`\"'„“]*[`\"'„“]", line))
              or "``" in line)
    role = any(w in line for w in ("laut", "zitiert", "steht"))
    if quoted and role:
        return True
    if "Berichtigung" in block_title:
        return True
    # §A-ZS: **Selbstquittung ist keine Quittung.** Ein Block, der sich
    # selbst adressiert, hebt seine eigenen Funde nicht auf — sonst wäre
    # die Regel ein Freibrief mit einem Satz Präambel.
    s = _selector_in(block_title)
    if s is not None:
        k = _block_key(block_title)
        if k == s:
            return False
        return bool(sel and s in sel["targets"])
    # §A-ZR: der **Zielblock** selbst. Adressiert ihn ein Korrekturblock,
    # quittiert das seine Fundstellen — außer der Zielblock hat sich in
    # `self` selbst adressiert.
    if sel:
        k = _block_key(block_title)
        if not k or k not in sel["targets"]:
            return False
        return k not in sel.get("self", set())
    return False


def _self_test_block_kind() -> list[str]:
    """§A-ZU/ZV: Ist der Typ ableitbar — und zählt die Auswahl 1/0/mehr?

    Fünf Runden Dauerrot kamen aus `[-1]`: der Selbsttest verglich den
    **Beleg aus §71.45** mit dem Lauf aus §71.54. Dauerrot ist so
    aussagelos wie dauergrün; beide messen den Zustand nicht.

    Fünf Behauptungen, alle prüfbar ohne Dateisystem:
      Fließtext, der `Karte:` **erwähnt**, ist keine Messung
      `total=` ohne `Karte:` ist ein Beleg
      `Korrektur zu §…` ist eine Korrektur
      zwei Messungen derselben Karte sind ein **Fehler**, kein Tie-Break
      keine Messung ist `nicht gemessen`, nicht `grün`
    """
    out: list[str] = []
    # §A-ZW: die Erwartung ist **abgeleitet**, nicht getippt. Ein Literal
    # im Test ist eine zweite Meinung über den Prüfling; der Selbsttest
    # meldet genau das („Erwartung aus dem Pruefling"). Darum: die
    # Blocktexte werden gezählt, die Erwartung folgt aus der Zahl.
    fall = [
        ("### A — x\n\nEin Absatz: `Karte: abc` und `total=1`.\n", "Text"),
        ("### A — x\n\nBeleg\n\n```\ntotal=1\n```\n", "Beleg"),
        ("### §71.59c — Korrektur zu §71.59\n\nText\n", "Korrektur"),
        ("### A — x\n\n```\ntotal=1\nKarte: fp\n```\n", "Messung"),
    ]
    for text, want in fall:
        got = split_blocks(text)[0]["kind"]
        if got != want:
            out.append(f"Akte-Typ: {got} statt {want}")
    # Auswahl: der Text ist die Wahrheit, die Zahl folgt aus ihm.
    eins = "### A — x\n\n```\ntotal=1 chain=0\nKarte: fp\n```\n"
    zwei = eins.replace("### A — x", "### B — y") + "\n" + eins
    bloecke = {"leer": "### A — x\n", "eins": eins, "zwei": zwei}
    for name, text in bloecke.items():
        # Die Erwartung ist die Zahl der Blöcke **dieses Textes**, die als
        # Messung zählen — keine getippte Konstante.
        erwartet = sum(1 for b in split_blocks(text) if b["kind"] == "Messung")
        got = _select_messungen(text, "fp")
        if got != erwartet or (name != "leer" and got == 0):
            out.append(f"Akte-Auswahl: {name} nicht erkannt ({got})")
    # §A-ZX (Runde 55): **Uneinigkeit, nicht Anzahl.** Runde 54 machte aus
    # „zwei Blöcke" einen Fehler; richtig ist „zwei **verschiedene**
    # Aussagen". Die Probe ist der Unterschied, und sie wird gemessen:
    # gleiche Werte → eine Werte-Menge, verschiedene → zwei.
    gleich = zwei
    # §A-ZX: der ungleiche Fall wird **gebaut**, nicht ersetzt. Ein
    # `replace` mit mehrdeutigem Anker ist selbst ein stiller Griff.
    ungleich = ("### A — x\n\n```\ntotal=1 chain=0\nKarte: fp\n```\n\n"
                "### B — y\n\n```\ntotal=2 chain=0\nKarte: fp\n```\n")
    w_gleich = {_block_werte(b) for b in split_blocks(gleich)
                if b["kind"] == "Messung"}
    w_ungleich = {_block_werte(b) for b in split_blocks(ungleich)
                  if b["kind"] == "Messung"}
    if len(w_gleich) != 1:
        out.append("Akte-Faltung: Wiederholung als Widerspruch gelesen")
    if len(w_ungleich) != 2:
        out.append("Akte-Faltung: Widerspruch als Wiederholung gelesen")
    # Provenienz zählt nicht als Wert: die Kopfzeile trägt den Prüfer-Hash.
    kopf = ("### A — x\n\n```\ntotal=1\nKarte: fp\n"
            "kopfzeile: 8 gemessen · Prüfer aaa\n```\n")
    if len({_block_werte(b) for b in split_blocks(kopf)
            if b["kind"] == "Messung"}) != 1:
        out.append("Akte-Faltung: Kopfzeile zählt als Messwert")
    # §A-ZX: die Faltung der Treffermenge — die Entscheidung, die aus
    # „>1 = Fehler" die richtige Regel macht. Sie hängt **nicht** am Baum
    # und wird darum hier gefahren, nicht im Wirkungs-Fixture.
    ms = [b for b in split_blocks(zwei) if b["kind"] == "Messung"]
    if len({_block_werte(b) for b in ms}) != 1:
        out.append("Akte-Faltung: gleiche Werte nicht gefaltet")
    wd = {_block_werte(b) for b in split_blocks(ungleich) if b["kind"] == "Messung"}
    if len(wd) != len(ms):
        out.append("Akte-Faltung: Widerspruch nicht erkannt")
    if not _falte_gruen(ms) or _falte_gruen([b for b in split_blocks(ungleich)
                                             if b["kind"] == "Messung"]):
        out.append("Akte-Faltung: grün/rot vertauscht")
    # §A-ZY (Runde 56): Die **leere** Menge ist nicht grün — sie ist gar
    # nichts. `<= 1` hat sie grün gefaltet; keiner der drei Gegenläufe hat
    # das je gefragt, weil der Aufrufer vorher abfängt.
    try:
        _falte_gruen([])
        out.append("Akte-Faltung: leere Treffermenge gilt als grün")
    except ValueError:
        pass
    # §A-ZZ: die Auswahl als reine Funktion — drei Ausgänge, ohne Baum.
    # Das ist die Deckung, die Runde 55 mit „kein .git/" begründet hatte.
    # Die Erwartung ist **hier benannt**, nicht aus `stufen` gelesen: sonst
    # ist sie ableitbar und misst sich selbst.
    karte = "total=1 chain=0\nKarte: fp\n"
    blk = split_blocks(zwei)
    ohne_messung = [b for b in blk if b["kind"] != "Messung"]
    widerspruch = split_blocks(ungleich)
    # Die drei Ausgänge, jeder mit **einem** Namen — dann ist der Prüfling
    # nicht mehr aus dem Ausdruck ableitbar, sondern eine benannte Größe.
    kein_treffer = _auswahl_fehler(ohne_messung, karte)
    genau_einer = _auswahl_fehler(blk, karte)
    uneinig = _auswahl_fehler(widerspruch, karte)
    if not kein_treffer:
        out.append("Akte-Auswahl: keine Messung nicht rot")
    if genau_einer:
        out.append("Akte-Auswahl: eine Messung rot")
    if not uneinig:
        out.append("Akte-Auswahl: Widerspruch nicht rot")
    if kein_treffer == genau_einer:
        out.append("Akte-Auswahl: keine und eine nicht unterschieden")
    # §A-ZZ2: ein Notizfeld ist nie Wert — und ein neues Wertfeld zählt.
    # Die Sonden leiten sich **hier** aus `_WERT_FELDER` ab (erstes Feld =
    # Wert, `kopfzeile:` = Notiz), damit der Test nicht gegen eine alte
    # Kopie der Liste läuft. Kein Modulglobal: der Selbsttest braucht
    # keinen Zustand, den ein anderer Lauf zurücksetzen müßte.
    wert_sonde = "total=1"
    notiz_sonde = "kopfzeile: Prüfer aaa"
    notiz = ("### A — x\n\n```\n" + wert_sonde + "\nKarte: fp\n"
             + notiz_sonde + "\n```\n")
    notiz2 = notiz.replace(notiz_sonde, notiz_sonde + "x")
    if len({_block_werte(b) for b in split_blocks(notiz)
            if b["kind"] == "Messung"}) != 1:
        out.append("Akte-Feldtaxonomie: Notiz zählt als Wert")
    if _block_werte({"kind": "Messung", "lines": notiz.splitlines()}) != \
            _block_werte({"kind": "Messung", "lines": notiz2.splitlines()}):
        out.append("Akte-Feldtaxonomie: Notizänderung gilt als Wertänderung")
    wert2 = notiz.replace(wert_sonde, "total=2")
    if wert_sonde.split("=")[0] not in _WERT_FELDER:
        out.append("Akte-Feldtaxonomie: Wertsonde trifft kein Wertfeld")
    if _block_werte({"kind": "Messung", "lines": notiz.splitlines()}) == \
            _block_werte({"kind": "Messung", "lines": wert2.splitlines()}):
        out.append("Akte-Feldtaxonomie: Wertänderung gilt als Notiz")
    # §A-ZZZZ1 (Runde 57): die Einschlußliste scheitert **offen** — ein
    # umbenanntes Feld ist nicht „eine Notiz", sondern eine Lücke, durch die
    # die Faltung blind ist. Wird es gefunden?
    voll = calibration_card()
    if _feldpruefung(voll):
        out.append("Akte-Feldtaxonomie: vollständiger Block gilt als lückenhaft")
    umbenannt = voll.replace("total=2 chain_total=0", "total_=2 chain_total=0", 1)
    if not _feldpruefung(umbenannt):
        out.append("Akte-Feldtaxonomie: umbenanntes Feld bleibt grün")
    # Und die Gegenprobe: ein **fehlendes** Feld ist ebenfalls ein Befund,
    # nicht eine Notiz — sonst wäre „weniger ist auch ok" die Regel.
    # §A-ZZZZ1 (Selbstfund): die Felder stehen **in einer Zeile**; ein
    # Zeilenfilter entfernt hier nichts und prüft dann nichts. Entfernt
    # wird das Feld, nicht die Zeile.
    fehlt = voll.replace("chain_total=0 reported=2",
                         "chain_total_entfernt=0 reported=2", 1)
    if not _feldpruefung(fehlt):
        out.append("Akte-Feldtaxonomie: fehlendes Feld bleibt grün")
    # §A-ZZZZ0 (Runde 57): die Kopfzeile wird **gegen den Block** gerechnet.
    # Ohne diesen Test ist `_kopfzeile_errors` ein Prüfer ohne Probe —
    # genau der Vorwurf, den diese Runde gegen die Vorrunde richtet.
    # Der **Prüfer-Hash**-Abstand ist kein Fehler (der Block ist Vorzustand,
    # jeder Edit ändert den Hash) und wird darum nicht gezählt — sonst
    # wäre der Test an sein eigenes Schreiben gekoppelt und dauerrot.
    hart = [e for e in _kopfzeile_errors()
            if "Block ist Vorzustand" not in e]
    if hart:
        out.append(f"Kopfzeile: committeter Block weicht ab: {hart}")
    # Die Gegenprobe: `U > 0` **ohne** `unvollstaendig` muß rot sein. Das
    # ist der Fehler der Vorrunde, nachgestellt.
    #
    # §A-ZZZZ2 (Runde 58): Runde 57 hatte **einen** Gegenlauf — und der
    # prüfte nur die Abwesenheit von Rauschen. `sieben gemessen` und ein
    # fehlender `·` fallen aus dem Muster; ein Filter, der nur prüft, was
    # er erkennt, ist bei Unbekanntem grün. Drei Fälle, alle nötig:
    #
    #   muster-konform und falsch   → Meldung mit Begründung
    #   muster-fremd (kein `·`)     → „Form nicht lesbar"
    #   Zahl durch Wort ersetzt     → dasselbe, nicht still
    import tempfile as _tf, shutil as _sh
    _d = Path(_tf.mkdtemp())
    try:
        (_d / "order_execution_engine" / "ops").mkdir(parents=True)
        (_d / "order_execution_engine" / "ops" / "KOPFZEILE.md").write_text(
            "<gemessen> <unvollständig> <keine>\n", encoding="utf-8")
        kopf = ("### §71.x — x\n\n```\ntotal=1 chain=0\n"
                "kopfzeile: 8 gemessen · 1 nicht gemessen · "
                "Prüfer aaa\nKarte: fp\n```\n")
        for name, text, wort in (
                ("unvollstaendig fehlt", kopf, "nicht als unvollstaendig"),
                ("ohne Trenner", kopf.replace(" gemessen · 1", " gemessen 1"),
                 "nicht lesbar"),
                ("Wort statt Zahl", kopf.replace("8 gemessen", "sieben gemessen"),
                 "nicht lesbar")):
            (_d / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md").write_text(
                text, encoding="utf-8")
            got = _kopfzeile_errors(_d)
            if not any(wort in g for g in got):
                out.append(f"Kopfzeile: {name} bleibt grün ({got})")
    finally:
        _sh.rmtree(_d, ignore_errors=True)
    return out


def _self_test_auswahl_truthiness() -> list[str]:
    """§A-ZZZZ6 (Runde 58): `if r:` auf `(0, [])` ist immer wahr.

    Die fünfte Fehlerklasse dieser Akte in ihrer allgemeinen Form: eine
    Bedingung, die wahr ist, wenn der Gegenstand **fehlt**. Ein
    `Auswahl(ok=…)`-Objekt wurde versucht und wieder verworfen — es
    bricht den Sammler (`carries_case` vergleicht `<= 0`) für einen
    Fehler, der im **Aufrufer** sitzt. Die Wache ist darum hier: jede
    Funktion in `scripts/`/`check_fixtures.py`, die irgendwo ein Tupel
    zurückgibt, darf nicht per Wahrheitswert gegated werden.
    """
    import ast as _ast
    out: list[str] = []
    hier = Path(__file__).resolve().parent
    for datei in (Path(__file__).resolve(), hier / "check_fixtures.py"):
        try:
            tree = _ast.parse(datei.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        tupel = {
            n.name for n in _ast.walk(tree) if isinstance(n, _ast.FunctionDef)
            for r in _ast.walk(n)
            if isinstance(r, _ast.Return) and isinstance(r.value, _ast.Tuple)}
        for n in _ast.walk(tree):
            if not isinstance(n, _ast.If):
                continue
            t = n.test
            if (isinstance(t, _ast.Call) and isinstance(t.func, _ast.Name)
                    and t.func.id in tupel):
                out.append(f"Akte-Truthiness ({datei.name}): "
                           f"`if {t.func.id}(...)` prüft einen Tupel — "
                           "`(0, [])` ist wahr")
    return out


def _falte_gruen(messungen: list[dict]) -> bool:
    """§A-ZX: Die Treffermenge ist grün, wenn alle **dasselbe** sagen.

    Eine Funktion, nicht eine Bedingung an zwei Orten: der Prüfer und der
    Selbsttest müssen dieselbe Frage stellen, sonst prüft der Test eine
    andere Regel als die, die läuft.

    §A-ZY (Runde 56, Selbstfund): Runde 55 hatte `<= 1` — und
    `len(set()) == 0`, also war die **leere** Treffermenge grün. Eine
    Funktion, die „grün" heißt, sagte „grün", wenn es nichts zu prüfen
    gab: dieselbe Form wie `if root is not None` (§A-ZW) — vierter
    Auftritt. Keiner der drei Gegenläufe hat sie je mit `[]` aufgerufen;
    sie haben den **Aufrufer** geprüft, nicht die Funktion.

    Der `raise` ist die Antwort, nicht ein `== 1`: er zwingt den Aufrufer,
    „nicht gemessen" **vor** der Faltung zu entscheiden. Damit ist die
    Reihenfolge erzwungen statt unterstellt.
    """
    if not messungen:
        raise ValueError("_falte_gruen: leere Treffermenge — "
                         "„nicht gemessen\" gehört vor die Faltung")
    return len({_block_werte(b) for b in messungen}) == 1


# §A-ZZ2 (Runde 56): **Einschlußliste, nicht Ausschlußliste.**
#
# Runde 55 hat `kopfzeile:` ausgenommen, weil der Prüfer-Hash sich mit
# jedem Edit ändert. Das hält bis zum nächsten neuen Feld — und Felder,
# die nichts beeinflussen dürfen, ziehen den Fehler an.
#
# Ein Messblock hat drei Sorten Feld, und sie verhalten sich verschieden:
#
#   Werte      `37/37`, `total=`, Zähler   → **verglichen**
#   Identität  `Karte: <fp>`               → **ausgewählt**
#   Notizen    Prüfer-Hash, Datum, dirty   → **nirgends**
#
# Was nicht in `_WERT_FELDER` steht, ist Notiz. Ein neues Feld ist damit
# automatisch harmlos, statt bis zum nächsten Selbstfund schädlich.
_WERT_FELDER = ("total", "chain_total", "reported", "unclassified",
                "unchecked", "unclassified_checkers")
# §A-ZZZZ1 (Runde 57, Selbstfund): Runde 56 hatte hier
# `inventare`, `testpfade`, `schreibmodus` stehen — **deutsche Namen für
# Felder, die der Block englisch trägt**. Die Liste war nie vollständig;
# sie war nur nie geprüft. Die Vollständigkeitsprüfung unten hat es in
# der ersten Ausführung gefunden. Alle übrigen Zeilen des Blocks sind
# Notizen (`Zeilen:`, `Wellen:`, …) und gehen nicht in die Werte ein.
# §A-ZZZZ1 (Runde 57): **Die Einschlußliste scheitert offen.** Runde 55
# hatte eine Ausschlußliste: ein neues Feld wurde falsch-rot (laut).
# Runde 56 hatte eine Einschlußliste: ein **umbenanntes** Feld
# (`total_` statt `total`) wird nicht eingeschlossen, beide Blöcke haben
# danach dieselben Restwerte, `_falte_gruen` sagt grün — **still**.
#
# Der Ausweg ist nicht eine dritte Liste, sondern die
# Vollständigkeitsprüfung: die Feldmenge, die **tatsächlich** in einem
# Block vorkommt, muß exakt `_WERT_FELDER` sein. Ein Feld zu viel oder zu
# wenig ist ein Fehler, nicht eine Notiz.
def _feldpruefung(block_text: str) -> list[str]:
    """§A-ZZZZ1: Trägt der Block **genau** die erwarteten Wertfelder?

    Gelesen wird die `kopfzeile:`-Zeile (die kanonische Form) und die
    Schlüssel der Blockzahlen. Jeder Schlüssel, der nicht in
    `_WERT_FELDER` steht, ist ein Befund — denn entweder ist er eine
    Umbenennung (dann fehlt das Original und die Faltung ist blind) oder
    ein neues Feld (dann gehört es in die Liste, bewusst).
    """
    out: list[str] = []
    gesehen: list[str] = []
    for line in block_text.splitlines():
        line = line.strip()
        if not line or line.startswith(("Karte:", "Bezug:", "kopfzeile:")):
            continue
        if "=" in line and " " in line:
            for part in line.split():
                if "=" in part:
                    gesehen.append(part.split("=", 1)[0])
    fehlend = [f for f in _WERT_FELDER if f not in gesehen]
    fremd = [f for f in gesehen if f not in _WERT_FELDER]
    if fremd:
        out.append(f"Akte-Feldtaxonomie: unbekannte Wertfelder {fremd} — "
                   f"umbenannt oder neu, beides muß entschieden werden")
    if fehlend:
        out.append(f"Akte-Feldtaxonomie: Wertfelder fehlen {fehlend} — "
                   f"die Faltung wäre blind für sie")
    return out
# Die einzige Zeile, die **auswählt** statt zu vergleichen.
_IDENT_FELDER = ("Karte",)


def _block_werte(block: dict) -> tuple:
    """Die **Werte** eines Messblocks — die Vergleichsgröße der Faltung.

    §A-ZX: zwei Messungen derselben Karte sind nur dann ein Widerspruch,
    wenn sie verschiedene Werte tragen.

    §A-ZZ2 (Runde 56): gelesen wird eine **Einschlußliste** — Schlüssel
    aus `_WERT_FELDER` in `k=v`-Zeilen. Alles andere (Notizen, Identität,
    Prosa) geht nicht ein. `kopfzeile:` ist darum nicht „ausgenommen",
    sondern **nie eingeschlossen**.
    """
    body = "\n".join(block["lines"])
    zaeune = body.split("```")
    body = zaeune[1] if len(zaeune) >= 3 else ""
    werte = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        # Kopfzeilen-Form: `total=37 chain_total=20 …`
        if "=" in line and " " not in line.split("=", 1)[0].strip():
            for part in line.split():
                if "=" in part:
                    k = part.split("=", 1)[0]
                    if k in _WERT_FELDER:
                        werte.append(part)
            continue
        # `Schlüssel: wert` — nur die Identität ist hier relevant, und die
        # wird vom Aufrufer gelesen, nicht gefaltet.
        if ":" in line:
            k = line.split(":", 1)[0].strip()
            if k in _WERT_FELDER:
                werte.append(line)
    return tuple(werte)


def _select_messungen(text: str, fp: str) -> int:
    """Die Auswahl selbst — ein Ort, den der Prüfer und der Selbsttest
    teilen. Zwei Implementierungen wären zwei Wahrheiten (§A-ZW)."""
    return len([b for b in split_blocks(text)
                if b["kind"] == "Messung"
                and f"Karte: {fp}" in "\n".join(b["lines"])])


def _self_test_akte_guard() -> list[str]:
    """§A-NS: verweigert der Guard den Schrumpf, und räumt er `.tmp` weg?

    Der echte Vorfall als Fixture: viele Zeilen, drei Blöcke → drei Zeilen
    mit einem Block. Der Guard muß `ok=False` liefern **und die Datei
    unverändert lassen** — die Zusicherung ist, daß nichts passiert,
    nicht daß etwas gemeldet wird.
    """
    import tempfile
    import sys as _sys
    out: list[str] = []
    _sys.path.insert(0, str(Path(__file__).parent))
    import akte_guard as G
    d = Path(tempfile.mkdtemp(prefix="ag_"))
    akte = d / "TAG7_ABNAHME.md"
    body = ("# Akte\n\n### §71.01 — eins\n\n" + "Text.\n" * 20
            + "\n### §71.02 — zwei\n\n" + "Text.\n" * 20
            + "\n### §71.03 — drei\n\n" + "Text.\n" * 20)
    akte.write_text(body, encoding="utf-8")
    before = akte.read_text(encoding="utf-8")
    ok, msg = G.guarded_write(akte, "### §71.03 — drei\n\nnur das\n")
    if ok:
        out.append(f"akte_guard: Schrumpf 60 -> 3 Zeilen wurde GESCHRIEBEN ({msg})")
    if akte.read_text(encoding="utf-8") != before:
        out.append("akte_guard: Datei veraendert, obwohl der Guard abbrach")
    if any(p.name.endswith(".tmp") for p in d.iterdir()):
        out.append("akte_guard: .tmp liegt noch da — Baum waechst bei "
                   "jedem Fehlversuch")
    # Anhaengen ist erlaubt und verliert nichts
    ok2, _ = G.append_block(akte, "### §71.04 — vier\n\nneu\n")
    if not ok2 or "§71.04" not in akte.read_text(encoding="utf-8"):
        out.append("akte_guard: Anhaengen wurde verweigert")
    # Und der Fall, der durchgehen MUSS: mehr Bloecke, mehr Zeilen.
    if G.check_shrink(body, body + "\n### §71.05 — fünf\n\nmehr\n"):
        out.append("akte_guard: Wachstum wurde als Verlust gemeldet")
    # §A-ZE (Runde 53): **gleiche Zeilenzahl**, ein Satz ersetzt. Runde 52
    # war hier gruen — `zeilen >= vorher` ist eine Zahl, keine Menge.
    # Der Anker ist das **erste Zeichen** der Zeile, nicht das ganze Wort —
    # `"Text."` steht inzwischen in mehreren Fixtures (§A-ZI).
    same_lines = body.replace("\nText.", "\nText!!", 1)
    if len(same_lines.splitlines()) != len(body.splitlines()):
        out.append("akte_guard: Fixture veraendert die Zeilenzahl — "
                   "der Hash-Fall ist nicht isoliert")
    hits = G.check_shrink(body, same_lines)
    if not any("geändert" in h for h in hits):
        out.append(f"akte_guard: Inhaltsaenderung bei gleicher Zeilenzahl "
                   f"nicht erkannt ({hits})")
    return out


def _self_test_prose_fractions() -> list[str]:
    """§A-ZB: findet der Prüfer den Satz, der in der Akte stand?

    Der Selbsttest ist die **Negativprobe**: die alte Form
    (`14/21 (66%)` neben `53% → 66%`) muß rot sein, die Rundung
    (`14/21 (67%)`) grün, `7/21 (33%)` grün. Ein Prüfer, der im
    Quelltext steht und nie feuert, ist der Fehler, um den es geht.
    """
    import tempfile
    out: list[str] = []
    d = Path(tempfile.mkdtemp(prefix="pf_"))
    (d / "order_execution_engine" / "ops").mkdir(parents=True)
    akte = d / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md"
    (d / "CLAUDE.md").write_text("", encoding="utf-8")
    cases = [
        ("14/21 (99%)\n", 1, "falsche Prozentzahl"),
        ("7/21 (33%)\n", 0, "richtige Ableitung"),
        ("14/21 (67%)\n", 0, "gerundete Prozentzahl"),
        ("14/21 (66%)\n", 0, "abgerundete Prozentzahl"),
        ("Kein Bruch in dieser Zeile.\n", 0, "Zeile ohne Bruch"),
        # §A-ZM: Zitat ist nicht Behauptung — gemeldet, aber quittiert.
        ("laut Akte steht dort `14/21 (99%)`\n", 1, "zitiert, quittiert"),
        ("```\n14/21 (99%)\n```\n", 0, "im Codeblock: Beispiel"),
        # §A-ZP/ZQ/ZS: Selektor statt Hash — gültig, ins Leere, gegen sich selbst.
        ("### §71.59 — a\n14/21 (99%)\n### §71.59c — Korrektur zu §71.59\n",
         1, "gueltiger Selektor quittiert den Zielblock"),
        ("### §71.59 — a\n14/21 (99%)\n### §71.59c — Korrektur zu §71.99\n",
         2, "Selektor ins Leere quittiert nichts (+ eigener Befund)"),
        ("### §71.59 — Korrektur zu §71.59\n14/21 (99%)\n",
         1, "Selbstquittung ist keine Quittung"),
    ]
    for text, want, label in cases:
        akte.write_text(text, encoding="utf-8")
        rep = Report()
        check_prose_fractions(d, rep)
        got = len(rep.problems)
        if got != want:
            out.append(f"check_prose_fractions: {label} — {got} Befunde, "
                       f"erwartet {want} ({text.strip()})")
    return out


def _self_test_status_line_none() -> list[str]:
    """§A-NM (Runde 51): sagt die Kopfzeile `None` statt `0`?

    Vierter Punkt der Runde 51: ein Prüfer, der `0` sagt, ist nur glaubwürdig, wenn
    dieselbe Regel **einmal rot war**. Für die Kopfzeile heißt rot:
    `problems=None` (keine Differenzmessung, kein `.git/`) darf **keine
    Zahl** ergeben — weder `0` noch eine gerenderte Klammer-Fußnote.
    Der Lauf in Runde 51 hat das gemessen: der Staging-Baum schrieb
    `, 0 Abweichungen` und den Grund in Klammern darunter.
    """
    out: list[str] = []
    c = Checks(223, 210, 0)
    got = _status_line(c, None, Path("/tmp/_none"))
    if got is not None:
        out.append(f"_status_line(problems=None) gibt {got!r} statt None")
    if _status_line(c, 0, Path("/tmp/_ok")) is None:
        out.append("_status_line(problems=0) gibt None — der gesunde Fall "
                   "ist verloren")
    # Kein Baum: gar keine Zahl.
    if _status_line(c, 0, None) is not None:
        out.append("_status_line(root=None) gibt eine Zahl — kein Baum "
                   "heißt nicht gemessen")
    # Gemessene 0 mit zweiter Zahl: die drei Zahlen stehen getrennt da
    # (§A-NM) — `0 gemessen`, die nicht gemessenen, die ohne Skript. Die
    # alte Form `0 Abweichungen` mit Fussnote ist verboten: sie sieht aus
    # wie eine Summe ueber alles.
    line = _status_line(c, 0, Path("/tmp/_x"), unmessured=["a", "b"],
                        ohne_skript=["s1", "s2"])
    # §A-NV: `gemessen` = PRUEFER_UMFANG - nicht gemessen (2).
    want_first = f"{PRUEFER_UMFANG - 2} gemessen · 2 nicht gemessen · 2 ohne Skript"
    if line is None or want_first not in line:
        out.append(f"gemessene 0 fehlt: {line!r}")
    elif "Abweichungen" in line:
        out.append(f"alte Fussnotenform in der Kopfzeile: {line!r}")
    return out


def _self_test_ignored_test_paths() -> list[str]:
    """§A-NN (Runde 51): meldet der `.gitignore`-Pruefer **und** schweigt
    er im heilen Fall? (roter Lauf vor grünem.)

    Zwei Bäume, gleicher Prüfer: einer mit einem Test, der eine ignorierte
    Datei **vorfindet** (muß rot sein), einer mit einem Test, der sie
    **erzeugt** (muß grün sein). Ohne den roten Lauf wäre `0` eine
    Behauptung — dieselbe Form wie `_checker_gap` in Runde 48.
    """
    import tempfile
    out: list[str] = []
    for label, gitignore, body, expect in (
        ("vorgefunden", "data/\n*.jsonl\n",
         'p = _ROOT / "data" / "x" / "feat.jsonl"\n'
         'if not p.is_file():\n    raise SystemExit(1)\n', 1),
        ("erzeugt", "data/\n*.jsonl\n",
         'p = _ROOT / "data" / "x" / "feat.jsonl"\np.unlink()\n'
         'p.write_text("{}")\n', 0),
        # §A-NM: Verzeichnismuster mit Unterpfad — der Fall aus Runde 50,
        # den die alte Fassung **nie** gesehen hat (`fnmatch` gegen `data/`).
        ("dir-muster", "data/synthetic/\n",
         'import json\njson.load(open("data/synthetic/f.jsonl"))\n', 1),
        # §A-NM: dasselbe Muster, aber als Verbotsliste — gewollt, grün.
        ("verbotsliste", "data/\n",
         '_FORBIDDEN = ("/data/raas/worm",)\n'
         'def test_a():\n    assert "/data/raas/worm" in _FORBIDDEN\n', 0),
    ):
        root = Path(tempfile.mkdtemp(prefix="gi_"))
        (root / ".gitignore").write_text(gitignore, encoding="utf-8")
        (root / "scripts").mkdir()
        (root / "scripts" / "test_x.py").write_text(
            "_ROOT = __import__('pathlib').Path('.')\n" + body,
            encoding="utf-8")
        rep = Report()
        # Index: leer — `data/` ist ausgeschlossen, nichts dort ist im Index.
        _in_index._cache = {"README.md"}  # type: ignore[attr-defined]
        check_test_paths_ignored(root, rep)
        got = len(rep.problems)
        if got != expect:
            out.append(f"gitignore-Pruefer ({label}): {got} Meldungen, "
                       f"erwartet {expect}")
        if expect == 0 and rep.checked == 0:
            out.append("gitignore-Pruefer: heiler Baum wurde nicht geprueft "
                       "(0 Angaben — still statt gruen)")
    # §A-NM: und das Muster selbst — der Fall, der blind war.
    if _gitignore_hit("data/synthetic/f.jsonl", ["data/synthetic/"]) is None:
        out.append("gitignore-Muster `dir/` trifft keinen Unterpfad — "
                   "der Pruefer ist blind fuer Verzeichnismuster")
    if _gitignore_hit("docs/f.jsonl", ["data/"]) is not None:
        out.append("gitignore-Muster `data/` trifft `docs/` — Praefix zu weit")
    return out


def _self_test_probe_anchors_self() -> list[str]:
    """Misst `_probe_anchors` sich selbst? (§A-MO, Runde 44)

    Die Probe der Runde: gegen den **eigenen Funktionsteil**
    angewendet, nicht gegen die ganze Datei. Gegen die ganze Datei
    ergeben sich die echten Anker — das ist richtig und beweist nichts.
    Gegen den Teil ab `def _probe_anchors` muss es **0** sein: dort
    stehen nur Fixtures, und ein Fixture ist von einem Anker nur durch
    `tokenize.COMMENT` unterscheidbar. Zaehlte es sich selbst, waere es
    wieder der Fehler aus Runde 41 — nur mit dem neuen Marker.
    """
    out: list[str] = []
    src = Path(__file__).read_text(encoding="utf-8")
    i = src.index("def _probe_anchors")
    hits = _probe_anchors(src[i:])
    if hits:
        out.append(f"_probe_anchors zaehlt sich selbst: {len(hits)} Anker "
                   f"im eigenen Funktionsteil — {hits[:2]}")
    # Der Marktplatz: ein Fixture-String ist kein Anker, ein Kommentar an
    # einer Code-Zeile ist einer.
    A = "\u00a7A" + "-KR-ANCHOR"
    if _probe_anchors('x = "# ' + A + '"\nprint("# ' + A + '")\n'):
        out.append("_probe_anchors zaehlt einen String als Anker")
    if not _probe_anchors("g()  # " + A + " grund\n"):
        out.append("_probe_anchors findet den echten Anker nicht")
    return out


def _load_swarm_health(root: Path):
    import importlib.util
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

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
_RESET_GLOBALS = ("_SNAPSHOT_SEEN _test_results _ROOT_CACHE _SNAPSHOT_CACHE "
                  # §A-NU (Runde 52): das `.gitignore`-Orakel haelt Antworten
                  # und ihre Herkunft. Beides ist Zustand — der Reset muss ihn
                  # leeren, sonst traegt ein Test die Antwort des vorigen.
                  "_IGNORE_CACHE _GITIGNORE_SOURCE")
# §A-JY: die dritte Kategorie. Ein Global, das **nie** zurueckgesetzt werden
# darf, weil es der Reset selbst braucht, um zu wissen, wohin er zurueckgeht.
# Eine Referenz ist deklariert und geprueft — aber vom Reset ausgenommen.
# Ohne diese Kategorie muesste `_START_CWD` in `_RESET_GLOBALS` stehen, und
# `reset_all()` wuerde ihn auf `Path.cwd()` setzen — also auf den Zustand,
# den er gerade reparieren soll. Beim ersten Durchlauf faellt das nicht auf
# (cwd ist sauber), erst beim zweiten gescheiterten `chdir`-Fall landet die
# Referenz in `/tmp`.
_REFERENCE_GLOBALS = "_START_CWD _SOURCE_LINES"
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
               "_PRUEFER_UMFANG _NO_ANSWER _RESET_GLOBALS _STATE_FREE")


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


def _root_forwarding_violations() -> list[str]:
    """Welche Funktion mit `root`-Parameter ruft eine andere ohne `root`?

    §A-KK: Runde 38s Suche fragte nach `Path.cwd()` — dem **Fund** aus
    zweier Vorrunden, nicht dem **Fehler**. Der Fehler ist: ein Aufrufer hat
    `root` und reicht es nicht weiter. Das sind zwei Mengen, und die zweite
    ist groesser. `_save_count_snapshot` fiel durch, weil die Suche sie
    nie gestellt hat.

    §A-KM: der erste Anlauf filterte auf `root: Path | None` — und liess
    damit `check_line_counts(text, root: Path, rep)` aus, die wichtigste
    Gruppe. **Der Parameter heisst `root`, sein Typ ist Nebensache.** Die
    zweite Suche fragt nach dem Namen, nicht nach dem Fund.

    Die Regel ist mechanisch pruefbar: ruft eine Funktion, die `root`
    nimmt, eine andere, die `root` nimmt, muss `root` im Aufruf stehen —
    ausser der Aufruf ist bewusst der Default-Zweig (`root=None`, dann
    steht `()` da und die Funktion hat keinen `root`-Parameter).
    """
    return _forwarding_violations(Path(__file__).read_text(encoding="utf-8"))


def _forwarding_violations(src: str) -> list[str]:
    """Die Kernlogik, testbar an beliebigem Quelltext (§A-KU).

    Der erste Anlauf las `__file__` **in** der Prueffunktion — und war
    damit nur gegen die eigene Datei testbar. Ein Pruefer, den man nur
    gegen den Baum richten kann, den er prueft, ist ein Pruefer ohne
    Gegenprobe; die Presets laufen jetzt an Mini-Quellen.
    """
    import ast
    tree = ast.parse(src)
    # §A-KQ: `root_funcs[name]` ist die **Position** von `root` in der
    # Signatur (0-basiert) oder -1. Der erste Anlauf speicherte
    # `ps[0] == "root"` — und damit fiel `check_line_counts(text, root, rep)`
    # als "root ist nicht erstes Argument" durch: dreizehn Falschmeldungen fuer
    # einen Fehler. Ein Pruefer, der Positionsargumente nicht zaehlt,
    # misst die Form, nicht die Uebergabe.
    root_funcs: dict[str, int] = {}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            ps = [a.arg for a in n.args.args]
            if "root" in ps:
                root_funcs[n.name] = ps.index("root")

    def calls_without_root(fn: ast.FunctionDef, label: str = '') -> list[str]:
        """Nur die Aufrufe **im eigenen Rumpf**, nicht in Kind-`def`s (§A-KL/KN).

        §A-LD: das Kind wird nicht uebersprungen, sondern **eigenstaendig**
        geprueft. Ein `g()` in einem Kind, das selbst kein `root` bindet,
        ist dort korrekt — es ist ein Verstoss der **Kind**funktion nur,
        wenn sie `root` hat. Runde 39 warf alle Kindknoten weg; das Preset
        K4 zeigt, dass damit auch ein echter Verstoss im Kind verloren
        geht (er wird nie gemeldet).
        """
        found: list[str] = []

        def visit(node: ast.AST, node_fn: ast.FunctionDef) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.FunctionDef):
                    # Kind: eigener Scope, eigene Bindung, eigene Meldung.
                    # §A-LD: nur wenn das Kind `root` **selbst bindet**.
                    if _binds_root(child, tree):
                        found.extend(calls_without_root(child, child.name))
                    continue
                if isinstance(child, (ast.AsyncFunctionDef, ast.Lambda)):
                    continue          # Scope ohne `root`; nicht unsere Frage
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    name = child.func.id
                    if name in root_funcs and name != fn.name:
                        has_kw = any(k.arg == "root" for k in child.keywords)
                        pos = root_funcs[name]
                        # §A-KS: "Argument vorhanden" ist nicht "root
                        # uebergeben". Der Zwilling `f(Path.cwd())` fuellte
                        # `child.args` und galt als korrekt — genau der
                        # Fehler, den der Pruefer finden soll, nur an
                        # anderer Stelle. Gezaehlt wird der **Name** im
                        # AST, nicht die Anzahl der Argumente.
                        if len(child.args) > pos:
                            arg = child.args[pos]
                            passed = (isinstance(arg, ast.Name)
                                      and arg.id in _root_aliases(node_fn, child, tree))
                        else:
                            passed = False
                        if not has_kw and not passed:
                            # Ein Aufruf ohne `root` ist **nur** erlaubt,
                            # wenn der Test genau den Default-Zweig prueft
                            # (§A-KR). Das ist keine Duldung, sondern eine
                            # benannte Liste: `_DEFAULT_PROBE_ANCHORS`.
                            # Gebunden heisst: **die Funktion selbst** hat
                            # `root` (Parameter, Zuweisung, with-as). Ein
                            # Kind, das `root` nur als Closure sieht,
                            # uebergibt nichts — es hat nichts zu uebergeben.
                            # §A-NI (Runde 49): die Rolle statt der
                            # Markerliste. Ein Aufruf in einem
                            # Selbsttest prueft den Default-Zweig; der
                            # Fund ist dort das Ziel. Dieselbe Bewegung
                            # wie bei `_CWD_READERS`: von vielen Ausnahmen
                            # auf eine Regel.
                            if _binds_root(node_fn, tree) and \
                                    not _in_self_test(child.lineno, tree):
                                found.append(
                                    f"{label or fn.name} -> {name}() @L{child.lineno}")
                visit(child, node_fn)

        for stmt in fn.body:
            # §A-LG: `visit(stmt)` fuer einen `def`-Knoten hiesse, in das
            # Kind hineinzulaufen, **ohne** es als Kind zu behandeln. Der
            # Einstieg muss dieselbe Regel haben wie die Rekursion: ein
            # Kind mit eigener `root`-Bindung wird eigenstaendig geprueft,
            # eines ohne wird nicht betreten.
            if isinstance(stmt, ast.FunctionDef):
                if _binds_root(stmt, tree):
                    found.extend(calls_without_root(stmt, stmt.name))
                continue
            if isinstance(stmt, (ast.AsyncFunctionDef, ast.Lambda)):
                continue
            visit(stmt, fn)
        return found

    out: list[str] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.FunctionDef):
            continue
        # §A-KO: der Aufrufer muss nicht in `root_funcs` stehen — er
        # braucht `root` **selbst gebunden**.
        # §A-LF: der erste Anlauf lief per `ast.walk(tree)` ueber **alle**
        # `def`s, auch die verschachtelten, und `_names_in_scope` fand
        # dort `root` als Closure der Elternfunktion. Damit wurde `inner`
        # zweimal geprueft — einmal als Kind (richtig, keine Bindung) und
        # einmal als Wurzel (falsch, Closure als Bindung). Gefragt ist
        # `_binds_root`: hat **diese** Funktion `root`, oder sieht sie es
        # nur?
        if _binds_root(n, tree):
            out.extend(calls_without_root(n))
    return out


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


# §A-KR: die **erlaubten** Aufrufe ohne `root`. Kein Wildcard, keine
# Mustererkennung: **Textanker** statt Zeilennummern — die Zeile wandert
# mit jedem Edit, der Anker nicht. Jeder Anker traegt seinen Grund im
# selben Code. Wird der Aufruf umgeschrieben, findet die Wache ihren
# Anker nicht mehr und schlaegt an: "Ausnahme ohne Wache ist eine Duldung".
# §A-KY: der erste Stand hing an Zeilennummern und brach beim
# ersten Einfuegen darueber. Das ist derselbe
# Fehler wie ein Cache ohne Schluessel: die Ausnahme zeigte auf eine
# Position statt auf einen Inhalt.
_DEFAULT_PROBE_LINES: frozenset[int] = frozenset()

# §A-KZ: die Ankerliste **war** die Abschrift, die §2b gerade abschaffte.
# Acht Literale, von Hand gepflegt, und die Wache pruefte ihre eigene
# Abschrift: die Liste zaehlte sich selbst mit, weil sie ihre Marker als
# Literale trug.
# Jetzt wird **abgeleitet**: der Quelltext ist die Quelle, `§A-KR` die
# Markierung, der Zeileninhalt der Anker. Die Zahl entsteht aus dem Code.
#
# Der Preis, benannt: wer Anker **und** Marker loescht, verschwindet
# spurlos — abgeleitete Mengen sind zirkulaer, wenn die Quelle dieselbe
# ist, die sie prueft. Deshalb steht daneben ein **Groessen-Guard** mit
# einer dokumentierten Zahl und ihrer Herkunft (§A-LA).
_PROBE_ANCHOR_EXPECTED = 18
_PROBE_ANCHOR_SELFTEST_EXPECTED = 0
_PROBE_ANCHOR_ORIGIN = (
    "Runde 40, Marker §A-KR: vier Default-Zweig-Aufrufe (check_counts x2, "
    "_snapshot_path, _snapshot_path im --json-report) und vier Aufrufe mit "
    "absichtlich fremdem Ort (_delta_line(1), _snapshot_path(root) gegen "
    "_snapshot_path(), repo_root(None) zweimal). §A-MF (Runde 43): die "
    "neun _status_line-Aufrufe im --self-test plus ihr Formprobe-Partner: "
    "**18**, alle in `main`s Pfad, alle Produktion. Die 9 sind nicht "
    "'Pruefstand' — das war die falsche Buchung aus Runde 42. "
    "Nachgezaehlt: `grep -c 'A-KR-ANCHOR' scripts/check_claude_md.py`.")
# §A-MF (Runde 43): **eine dritte Kategorie gibt es nicht.** Runde 42
# buchte neun Aufrufe als "Pruefstand" — sie stehen aber in
# `self_test_check_counts`, das `main` aufruft. Ein `--self-test`-Aufruf
# ist Produktionscode, der den Pruefstand aufruft. Ob er `root` braucht,
# haengt an der **Aufrufstelle**. Der hier gegebene Grund ("Formprobe,
# kein Baum") ist ein Grund, keine Ausnahme — und die Formprobe steht
# als **Paar** da: derselbe Aufruf mit Baum in `_status_line`-Zwillingsprobe.


def _probe_anchors(src: str | None = None) -> tuple[str, ...]:
    """Leitet die erlaubten Aufrufe aus dem Quelltext ab (§A-MG).

    **Zwei Marker, zwei Bedeutungen.** Runde 42 unterschied Anker und
    Erklaerung an der Zeilenform (`# §A-KR` allein = Prosa, Code + Marker
    = Anker). Das hielt nur, solange niemand umbrach: eine mehrzeilige
    Erklaerung ueber einem Anker hat dieselbe Form wie der Anker. Jetzt
    ist die Suche ein eindeutiges Wort statt einer Zeilenform:

        §A-KR-ANCHOR   die Sache (eine erlaubte Zeile)
        §A-KR          die Erklaerung

    Der Rot-Beleg aus Runde 42 zeigte den Preis: mit dem alten
    Diskriminator zaehlte dieselbe Datei mehr Zeilen als Anker — die
    Prosa trug den Marker mit.

    Gezaehlt wird nur Code **vor** diesem Block: weder die Ableitung selbst
    noch ihre Beschreibung.
    """
    text = src if src is not None else Path(__file__).read_text(encoding="utf-8")
    marker = "§A" + "-KR-ANCHOR"     # zur Laufzeit gebaut (siehe unten)
    lines = text.split("\n")
    try:
        cut = next(i for i, ln in enumerate(lines)
                   if ln.startswith("def _probe_anchors"))
    except StopIteration:
        cut = len(lines)
    # §A-LA: zwei weitere Schnitte, beide benannt. Der Markerblock (§A-KZ)
    # und der Herkunftstext des Groessen-Guards nennen den Marker als
    # Prosa — sie beschreiben die Ausnahmen, sie sind keine.
    for start in ("# §A-KR:", "_PROBE_ANCHOR_ORIGIN"):
        try:
            cut = min(cut, next(i for i, ln in enumerate(lines)
                                if ln.lstrip().startswith(start)))
        except StopIteration:
            pass
    out: list[str] = []
    # §A-MJ (Runde 44): "Code-Zeile" hiess bisher "faengt nicht mit `#` an".
    # Blind-Fixture, das den Marker als String baut, zaehlt sich mit.
    # Genau dieser Fall war in Runde 41 der Fehler (`10 statt 8`), nur mit
    # dem alten Marker. **Ein Kommentar ist, was `tokenize` als COMMENT
    # liefert** — ein String ist es nicht, ein Docstring auch nicht.
    import io
    import tokenize
    comments: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT and marker in tok.string:
                comments[tok.start[0]] = tok.string
    except (tokenize.TokenError, IndentationError):
        comments = {}
    for lineno in sorted(comments):
        if lineno > cut:
            continue
        line_no = lineno - 1
        body = lines[line_no]
        stripped = body.lstrip()
        # Reiner Kommentar (nichts davor) ist Prosa; ein Kommentar **an**
        # einer Code-Zeile ist ein Anker.
        if stripped.startswith("#"):
            continue
        anchor = body.strip()
        if anchor:
            out.append(anchor)
    return tuple(out)


_SOURCE_LINES: list[str] = []


def _marked(lineno: int) -> bool:
    """Steht `§A-KR-ANCHOR` auf dieser Zeile? (Quelltext, einmal gelesen)

    §A-MG: der Anker ist der eindeutige Marker, nicht die Prosa-Marke.
    """
    if not _SOURCE_LINES:
        _SOURCE_LINES.extend(
            Path(__file__).read_text(encoding="utf-8").split("\n"))
    if not (1 <= lineno <= len(_SOURCE_LINES)):
        return False
    return ("§A" + "-KR-ANCHOR") in _SOURCE_LINES[lineno - 1]


def _default_probe_lines_valid() -> list[str]:
    """Sind die erlaubten Aufrufe **abgeleitet** — und ihre Zahl belegt?

    Drei Fragen, drei Antworten (§A-KZ):
    1. **Anwesenheit:** jeder abgeleitete Anker steht wortgleich im Code.
    2. **Groesse:** die abgeleitete Menge hat `_PROBE_ANCHOR_EXPECTED`
       Elemente. Ohne diese Zahl ist die Ableitung zirkulaer: wer Anker
       **und** Marker loescht, verschwindet aus der Menge, und eine
       kleinere Menge ist fuer sich kein Fehler. Die Herkunft der Zahl
       steht daneben, nicht hier.
    3. **Rechtfertigung:** jede Ausnahme nennt ihren Grund. Ein Anker
       ohne Grund ist eine Erlaubnis ohne Ablaufdatum — genau der Zustand,
       den §A-KZ abschafft.
    """
    src = Path(__file__).read_text(encoding="utf-8")
    lines = src.split("\n")
    out: list[str] = []
    anchors = _probe_anchors(src)
    joined = "\n".join(ln.strip() for ln in lines)
    for anchor in anchors:
        if anchor not in joined:
            out.append(f"Anker fehlt: {anchor!r}")
    if len(anchors) != _PROBE_ANCHOR_EXPECTED + _PROBE_ANCHOR_SELFTEST_EXPECTED:
        out.append(
            f"{len(anchors)} abgeleitete Ausnahmen, erwartet "
            f"{_PROBE_ANCHOR_EXPECTED} Produktion + "
            f"{_PROBE_ANCHOR_SELFTEST_EXPECTED} Pruefstand"
            f" — Herkunft: {_PROBE_ANCHOR_ORIGIN}")
    if len(set(anchors)) != len(anchors):
        out.append(f"{len(anchors) - len(set(anchors))} doppelte Ausnahme(n)")
    # Jede Markierung muss einen Grund tragen: mehr als das blosse
    # nicht *warum*.
    for ln in lines:
        if ("§A" + "-KR-ANCHOR") in ln:
            tail = ln.split("§A" + "-KR-ANCHOR", 1)[1].strip(" #\t")
            if not tail and "root=None" not in ln:
                out.append(f"Ausnahme ohne Grund: {ln.strip()!r}")
    return out


def _git_callers_without_cwd(src: str) -> list[str]:
    """Welche Funktion ruft `git` ohne `cwd=`? (§A-LK)

    §A-LJ war das Glied. Der Glieder-Pruefer (`_forwarding_violations`)
    fand es nicht, weil `_resolve_test_root` keinen Parameter `root`
    hatte — nur `doc_root`. **Der Pruefer fragt nach dem Namen, der
    Fehler haengt an der Wirkung.** Diese Pruefung fragt nach der
    Wirkung: ein `subprocess.run(["git", ...])` ohne `cwd` liest immer
    das Prozess-Arbeitsverzeichnis, egal wie die Funktion heisst.

    Erlaubt sind Aufrufe, deren Repo **explizit** genannt wird
    (`-C <pfad>` im Argumentvektor) — das ist ein Repo ohne `cwd`.
    """
    import ast
    tree = ast.parse(src)
    out: list[str] = []

    def walk(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = owner
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{owner}.{child.name}" if owner else child.name
                # Der Rumpf gehoert dem Kind — mit dessen Namen weiterlaufen,
                # sonst steht die Fundstelle ohne Owner (§A-LM).
                for sub in ast.iter_child_nodes(child):
                    walk(sub, name)
                continue
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                f = child.func
                if (isinstance(f.value, ast.Name) and f.value.id == "subprocess"
                        and f.attr == "run" and child.args):
                    first = child.args[0]
                    if isinstance(first, (ast.List, ast.Tuple)):
                        words = [e.value for e in first.elts
                                 if isinstance(e, ast.Constant)
                                 and isinstance(e.value, str)]
                        # Ein Nicht-Literal hinter dem Subkommando ist ein
                        # Pfad-Ausdruck (`str(root)`) — das Repo ist damit
                        # genannt, auch ohne `cwd=` (§A-LL).
                        expr_arg = any(
                            not isinstance(e, ast.Constant) for e in first.elts)
                    else:
                        words = []
                        expr_arg = False
                    if words[:1] == ["git"]:
                        has_cwd = any(k.arg == "cwd" for k in child.keywords)
                        has_dash_c = "-C" in words
                        sub_cmd = words[1] if len(words) > 1 else ""
                        if not has_cwd and not has_dash_c and not expr_arg:
                            out.append(f"{name} -> git {sub_cmd} @L{child.lineno}")
            walk(child, name)

    for node in tree.body:
        walk(node, "")
    return out


def _binds_root(fn: object, tree: object = None) -> bool:
    """Bindet **diese** Funktion einen Pfad, der in den Lesepfad eingeht?

    §A-LE (Runde 45): der Scope-Resolver in `_names_in_scope` laeuft ueber
    den ganzen Funktionsbaum und findet `root` auch als Closure der
    Elternfunktion. Fuer die Frage „haette sie `root` weiterreichen
    koennen" ist das zu grosszuegig.

    §A-NJ (Runde 49): und der Name `root` ist die falsche Eigenschaft.
    Drei Anlaeufe der vorigen Probe scheiterten daran — eine Zuweisung galt,
    ein abweichender Name nicht, ein ungenutzter Parameter galt auch.
    Gefragt ist nicht **wie** die Variable heisst, sondern **was mit ihr
    passiert**: bindet die Funktion einen Namen, dessen Wert in einen
    Lesepfad eingeht?

        Parameter / Zuweisung / with-as
          → benutzt in `Path(x)`, `x / ...`, `x.glob()`, `open(x)`,
            `(x / ...).read_text()`, als `cwd=`/`root=`-Argument

    `root_` zaehlt. Ein `root`-Parameter, der nie gelesen wird, zaehlt
    **nicht** — er haette nichts zu reichen. Die Rolle bleibt dieselbe:
    ein Kind ohne Pfadbindung hat nichts zu uebergeben.
    """
    import ast
    args = getattr(fn, "args", None)
    if args is None:
        return False
    bound: set[str] = {a.arg for a in (*getattr(args, "posonlyargs", []),
                                       *args.args, *args.kwonlyargs)
                       if a.arg not in ("self", "cls")}
    for node in ast.iter_child_nodes(fn):  # type: ignore[arg-type]
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda)):
                continue        # Kind-`def`s binden fuer sich
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    if isinstance(t, ast.Name):
                        bound.add(t.id)
            if isinstance(child, (ast.With, ast.AsyncWith)):
                for item in child.items:
                    if isinstance(item.optional_vars, ast.Name):
                        bound.add(item.optional_vars.id)
    if not bound:
        return False
    return _used_as_path(fn, bound, tree)


_PATH_CALLS = frozenset({"Path", "PurePath", "open", "listdir", "scandir"})
_PATH_METHODS = frozenset({"glob", "rglob", "exists", "is_dir", "is_file",
                           "iterdir", "read_text", "read_bytes", "open",
                           "resolve", "stat", "mkdir", "unlink", "walk"})


def _path_returning(tree: object) -> set[str]:
    """Funktionen der Datei, die einen **Pfad** nehmen und einen geben.

    §A-NJ: `repo_root(root: Path | None = None) -> Path` ist der Fall.
    Eine Handliste waere wieder eine Liste, die veraltet — die Eigenschaft
    steht in der Signatur: Parameter mit `Path`-Annotation, Rueckgabe
    `Path`.
    """
    import ast
    if tree is None:
        return set()
    out: set[str] = set()
    for n in getattr(tree, "body", []):
        if not isinstance(n, ast.FunctionDef):
            continue
        ret = n.returns
        if not (isinstance(ret, ast.Name) and ret.id == "Path"):
            continue
        if any(any(isinstance(x, ast.Name) and x.id == "Path"
                   for x in ast.walk(a)) for a in n.args.args):
            out.add(n.name)
    return out


def _path_names(fn: object, tree: object = None) -> set[str]:
    """Alle gebundenen Namen, deren Wert in einen Lesepfad eingeht.

    §A-NJ: dieselbe Eigenschaft wie in `_binds_root`, aber als **Menge** —
    `_root_aliases` braucht die Wurzel, von der aus Aliasse aufgeloest
    werden, und die heisst nicht immer `root`.
    """
    import ast
    args = getattr(fn, "args", None)
    if args is None:
        return set()
    bound: set[str] = {a.arg for a in (*getattr(args, "posonlyargs", []),
                                       *args.args, *args.kwonlyargs)
                       if a.arg not in ("self", "cls")}
    for node in ast.iter_child_nodes(fn):  # type: ignore[arg-type]
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda)):
                continue
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    if isinstance(t, ast.Name):
                        bound.add(t.id)
            if isinstance(child, (ast.With, ast.AsyncWith)):
                for item in child.items:
                    if isinstance(item.optional_vars, ast.Name):
                        bound.add(item.optional_vars.id)
    return {n for n in bound if _used_as_path(fn, {n}, tree)}


def _used_as_path(fn: object, names: set[str],
                  tree: object = None) -> bool:
    """Geht einer der Namen in einen Lesepfad ein?

    Vier Formen, alle im AST sichtbar:

        Path(x)            Konstruktor
        x / "..."          Div auf einem Namen
        x.glob(...)        Pfadmethode
        f(cwd=x)           Schlüsselwort an einen Aufruf

    Und die fuenfte (§A-NJ): `g(x)` an eine Funktion dieser Datei, die
    `Path` nimmt und `Path` gibt — `repo_root(doc_root)` ist
    Durchreichung, nicht Fremdquelle.
    """
    import ast
    path_fns = _path_returning(tree)
    for node in ast.iter_child_nodes(fn):  # type: ignore[arg-type]
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda)):
                continue
            if isinstance(child, ast.Call):
                if (isinstance(child.func, ast.Name)
                        and (child.func.id in _PATH_CALLS
                             or child.func.id in path_fns)):
                    if any(isinstance(a, ast.Name) and a.id in names
                           for a in child.args):
                        return True
                if (isinstance(child.func, ast.Attribute)
                        and child.func.attr in _PATH_METHODS
                        and isinstance(child.func.value, ast.Name)
                        and child.func.value.id in names):
                    return True
                if any(isinstance(k.value, ast.Name) and k.value.id in names
                       for k in child.keywords):
                    return True
            if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Div):
                if any(isinstance(s, ast.Name) and s.id in names
                       for s in (child.left, child.right)):
                    return True
    return False


def _root_aliases(fn: object, at: object,
                  tree: object = None) -> set[str]:
    """Namen, die **denselben Wert** tragen wie `root` (§A-KT).

    `root_repo = root`, `case = root / ...`, `other_root = root / ...` —
    drei verschiedene Pfade, die alle von `root` abstammen. Wer sie
    uebergibt, reicht `root` durch. Der erste Anlauf verglich den
    Bezeichner `root`; `check_counts(..., root_repo)` galt damit als
    Nichtuebergabe. **Derselbe Fehler wie §3: nach dem Namen gefragt,
    nicht nach der Herkunft.**

    Aufgeloest wird transitiv: ein Name ist Alias, wenn sein Wert ein
    Ausdruck ist, der `root` oder einen bereits erkannten Alias
    enthaelt. Kein Interpreter — nur Zuweisungen vor `at`.
    """
    import ast
    limit = 10 ** 9 if at is None else getattr(at, "lineno", 10 ** 9)
    seeds = _names_in_scope(fn, None)
    # §A-NJ (Runde 49): die Wurzel ist nicht der Name `root`, sondern der
    # **gebundene Pfad** — wie bei `_binds_root`. `_resolve_test_root`
    # traegt `doc_root` und reicht es korrekt durch; die namensbasierte
    # Wurzel meldete das als Verstoss. Dieselbe Eigenschaft wie dort:
    # welcher Name geht in einen Lesepfad ein?
    # §A-NJ: die Wurzel ist der **Pfadparameter** — der Parameter, dessen
    # Wert in einen Lesepfad eingeht. `_resolve_test_root(doc_root)` und
    # `_akt_block_mismatch(root)` sind derselbe Fall mit zwei Namen.
    # `base = root or ...` wird darueber transitiv als Alias erkannt.
    params = {a.arg for a in (*getattr(getattr(fn, "args", None),
                                       "posonlyargs", []),
                              *getattr(getattr(fn, "args", None),
                                       "args", []),
                              *getattr(getattr(fn, "args", None),
                                       "kwonlyargs", []))}
    roots = (_path_names(fn, tree if tree is not None else fn) & params)
    aliases = roots & seeds if roots else ({"root"} & seeds)
    changed = True
    while changed:
        changed = False
        for n in ast.walk(fn):  # type: ignore[arg-type]
            if getattr(n, "lineno", 10 ** 9) > limit:
                continue
            if not isinstance(n, (ast.Assign, ast.AnnAssign)):
                continue
            value = n.value
            if value is None:
                continue
            used = {x.id for x in ast.walk(value) if isinstance(x, ast.Name)}
            if not (used & aliases):
                continue
            tgts = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in tgts:
                if isinstance(t, ast.Name) and t.id not in aliases:
                    aliases.add(t.id)
                    changed = True
    return aliases


def _names_in_scope(fn: object, at: object) -> set[str]:
    """Namen, die an `at` (innerhalb `fn`) gebunden sind (§A-KO).

    Kein vollstaendiger Scope-Resolver — nur `root`: Parameter,
    Zuweisungsziele, `with ... as`, `for ... in`, Tupel-Entpackung.
    Frage nicht "ist es ein Parameter", sondern "gibt es den Wert".
    """
    import ast
    names: set[str] = set()
    for a in getattr(fn, "args", ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[])).args:
        names.add(a.arg)
    limit = 10 ** 9 if at is None else getattr(at, "lineno", 10 ** 9)

    def targets(node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for e in node.elts:
                targets(e)

    for n in ast.walk(fn):  # type: ignore[arg-type]
        if getattr(n, "lineno", 10 ** 9) > limit:
            continue
        if isinstance(n, ast.Assign):
            for t in n.targets:
                targets(t)
        elif isinstance(n, ast.AnnAssign) and n.target is not None:
            targets(n.target)
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for item in n.items:
                if item.optional_vars is not None:
                    targets(item.optional_vars)
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            targets(n.target)
        elif isinstance(n, ast.NamedExpr):
            targets(n.target)
    return names


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


def repo_measurement_available(root: Path | None = None) -> bool:
    """Findet der Pruefer in **diesem** Baum ein Repo? (§A-NM, Runde 51)

    `repo_root` gibt ohne Repo die Projektwurzel zurueck — richtig fuer
    Dateizugriffe, falsch fuer die Frage „kann ich messen". Die beiden
    Zustaende sind:

      Repo vorhanden     → Differenz gegen Vorlauf messbar
      kein `.git/`       → **nicht** messbar (Hook-Staging-Export)

    Ohne diese Unterscheidung schrieb die Kopfzeile `0 Abweichungen`
    und den Grund in Klammern — die Null war die Summe der gemessenen
    Abweichungen und sah aus wie die Summe ueber alles.
    """
    try:
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                           cwd=str(repo_root(root)),
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and bool(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


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


def _doc_tracked(root: Path | None = None) -> str:
    """Ist die Rundentabelle im Commit — und stimmt der Inhalt?

    Gemessen mit `git ls-files --error-unmatch` und `git log -1`: eine
    Abnahme im Arbeitsbaum ist keine Doku, sie ist ein Entwurf.

    §A-KW: vorher stand hier `git status --porcelain`. Das ist
    eine **mtime**-Aussage: `touch TAG7_ABNAHME.md` — Inhalt unveraendert —
    liess die Zeile „geaendert" sagen, obwohl der Inhalt zum Commit
    passt. Und der umgekehrte Fall ist schlimmer: „committet <sha>" stand ueber
    einem Inhalt, der nicht <sha> war. Beides sind **Zeitpunkt**aussagen;
    die Zeile behauptet eine **Inhalts**aussage.

    Deshalb: `git show <sha>:<pfad>` gegen den Arbeitsbaum hashen. Kein
    `git diff` (das ist wieder indexabhaengig), sondern `sha256` beider
    Seiten. Das kostet einen Blob-Read — und misst genau, was dasteht.
    """
    rel = "order_execution_engine/ops/TAG7_ABNAHME.md"
    base = repo_root(root)
    try:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                           cwd=str(base), capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return "NICHT im Repo"
        c = subprocess.run(["git", "log", "-1", "--format=%h", "--", rel],
                           cwd=str(base), capture_output=True, text=True, timeout=5)
        sha = c.stdout.strip() or "?"
        if sha == "?":
            return "kein Commit"
        blob = subprocess.run(["git", "show", f"{sha}:{rel}"],
                              cwd=str(base), capture_output=True, timeout=5)
        if blob.returncode != 0:
            return f"Commit {sha} nicht lesbar"
        work = base / rel
        try:
            current = work.read_bytes()
        except OSError:
            return f"Datei fehlt im Arbeitsbaum (Commit {sha})"
        if hashlib.sha256(current).digest() == hashlib.sha256(blob.stdout).digest():
            return f"committet {sha} (Inhalt identisch, sha256:{hashlib.sha256(current).hexdigest()[:12]})"
        return f"geaendert nach {sha} (Inhalt weicht ab, sha256:{hashlib.sha256(current).hexdigest()[:12]})"
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

    __slots__ = ("n", "excluded", "claims")

    # §A-KF: warum `__setattr__` von Hand und nicht `@dataclass(frozen=True)`?
    # `frozen=True` erzeugt genau diese Sperre (plus `__delattr__`) — die
    # eigene Fassung hat also **keinen** Vorteil, ausser: das Modul importiert
    # `dataclasses` sonst nicht, und `Checks` hat eine `@property` (`total`),
    # die in einem `frozen`-Dataclass als `field(init=False)` deklariert
    # werden muesste — mehr Zeilen als die zwei hier. Der Grund ist also
    # **nicht** "spart Importkosten", sondern "haelt die Klasse klein".
    #
    # §A-KG: die Sperre ist eine **Dunder-Liste** und damit ein Nenner.
    # Gesperrt: `__setattr__`, `__delattr__`. Nicht gesperrt, weil strukturell
    # anders: `object.__setattr__` (umgeht jede Fassung, auch `frozen=True`),
    # `copy`/`pickle` (bauen ueber `__init__`, hier unkritisch, aber nicht
    # getestet), `vars()` (leer, weil `__slots__` kein `__dict__` gibt).
    # Wer einen weiteren Weg findet, traegt ihn hier ein — sonst ist die
    # Liste still unvollstaendig.

    def __init__(self, n: int, excluded: int = 0, claims: int = 0) -> None:
        # §A-KA: `frozen` — `total` ist eine Eigenschaft des Objekts, nicht
        # des Zugriffszeitpunkts. Ohne das koennte `n` zwischen Druck und
        # Pruefung kippen. Nebenwirkung: kein In-Place-Zaehler; wer
        # `checked += 1` braucht, baut `Checks(n+1, excluded)`. Zaehlort
        # ist `Report.ok()`/`Report.fail()`, die `Report.checked` als int
        # fuehren und beim Druck in `Checks` uebergeben (eine Stelle).
        object.__setattr__(self, "n", int(n))
        object.__setattr__(self, "excluded", int(excluded))
        object.__setattr__(self, "claims", int(claims))
        if self.n < 0 or self.excluded < 0 or self.claims < 0:
            raise ValueError("Pruefungen, Ausschluesse und Zusagen sind nicht negativ")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Checks ist ein Wert (frozen)")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Checks ist ein Wert (frozen)")

    @property
    def total(self) -> int:
        """**Alle** Angaben: geprueft + ausgeschlossen + zugesagt.

        §A-KH: bis Runde 38 hiess `total` "checked + excluded" — und die
        Zusagen (`Report.claims`) fielen heraus, obwohl die Zeile "Angaben
        gezaehlt" sagte. Zusagen sind keine Messung, aber sie sind Angaben
        im Dokument; sie weglassen hiess, den Namen zu behalten und die
        Menge zu aendern. Drei Einheiten, drei Zahlen, ein Name.

        **Definitionsaenderung, datiert: 2026-10-17, Runde 40.** Vorher
        `total = n + excluded` (Druck: `433 gezaehlt`), danach
        `total = n + excluded + claims` (Druck: `461 gezaehlt (433
        gemessen + 28 Zusagen)`). Wer die Rundenserie liest, muss an
        dieser Zeile sehen, dass die Zahl um Zusagen gewachsen ist und
        nicht um Pruefungen: welcher Posten wann dazukam.
        """
        return self.n + self.excluded + self.claims

    @property
    def measured(self) -> int:
        """Geprueft + ausgeschlossen — ohne Zusagen. Die alte `total`.

        Wer die Messmenge braucht (Delta, Snapshot), nimmt `measured`
        und nicht `total`: ein Delta ueber Zusagen waere keins.
        """
        return self.n + self.excluded

    def __str__(self) -> str:
        return f"{self.n} Angaben geprueft"

    def __repr__(self) -> str:
        return f"Checks({self.n}, {self.excluded}, {self.claims})"

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Checks) and self.n == other.n
                and self.excluded == other.excluded
                and self.claims == other.claims)

    def __hash__(self) -> int:
        return hash(("Checks", self.n, self.excluded, self.claims))


def _gitignore_patterns(root: Path) -> list[str]:
    """Die Muster aus `.gitignore`, ohne Kommentare und Leerzeilen (§A-NN).

    §3 der Runde 51: `.gitignore` **ist** ein Prüfer, der schon im Repo
    steht — er wird nur nicht gelesen. Ein Fixture, das von einer Datei
    abhängt, die dort ausgeschlossen ist, ist per Definition keines.
    """
    gi = root / ".gitignore"
    if not gi.exists():
        return []
    out: list[str] = []
    for raw in gi.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("!"):
            continue
        out.append(s)
    return out


def _fnmatch_pattern(pat: str) -> str:
    """`.gitignore`-Muster → `fnmatch`-Muster (Anker-Slash entfernen)."""
    p = pat.lstrip("/")
    return p


def _gitignore_hit(lit: str, pats: list[str],
                   root: Path | None = None) -> str | None:
    """Wird `lit` von `.gitignore` ausgeschlossen? (§A-NM/§A-NU, Runde 52)

    Runde 51 hat eine eigene Formenliste gebaut (Endung, Präfix, Pfad) —
    und damit `.gitignore` **nachgebaut**. Wer `.gitignore` nachbaut, baut
    es falsch: Negationen (`!muster`), `**/` und „letzter Treffer gewinnt"
    fehlen. Die Semantik gehört nicht hierher.

    **Deshalb: `git check-ignore -z --stdin` als Orakel**, wenn ein Baum
    da ist. `root=None` (Klon ohne `.git/`, Unit-Tests) fällt auf die
    Formenliste zurück — dann ist die Aussage schwächer, und der Prüfer
    sagt das über `_GITIGNORE_SOURCE[0]`.

    Rückgabe: das **treffende Muster** (für die Meldung), nicht der
    Pfad — `check-ignore -v` liefert `quelle:zeile:muster\tpfad`.
    """
    if root is not None:
        hit = _check_ignore_ask(lit, root)
        if hit is not _NO_ANSWER:
            _GITIGNORE_SOURCE[0] = "git check-ignore"
            return hit  # type: ignore[return-value]
    _GITIGNORE_SOURCE[0] = "formenliste (kein Baum)"
    import fnmatch
    base = lit.rsplit("/", 1)[-1]
    for p in pats:
        if not p:
            continue
        if p.endswith("/"):
            if lit.lstrip("/").startswith(p.lstrip("./")):
                return p
            continue
        if "/" in p:
            if fnmatch.fnmatch(lit.lstrip("./"), p.lstrip("./")):
                return p
            continue
        if fnmatch.fnmatch(base, p) or fnmatch.fnmatch(lit, p):
            return p
    return None


class _NoAnswer:
    """Sentinel: das Orakel konnte nicht antworten (kein `.git/`)."""

    def __repr__(self) -> str:                           # pragma: no cover
        return "<keine Antwort>"


_NO_ANSWER = _NoAnswer()
# §A-NU: zwei Modulglobale mit Zustand, deklariert — der Pruefer aus
# Runde 43 verlangt das. `_GITIGNORE_SOURCE` nennt, **wer** geantwortet
# hat (Git oder die Formenliste); `_IGNORE_CACHE` haelt die Antworten.
_GITIGNORE_SOURCE: list[str] = ["unbekannt"]
_IGNORE_CACHE: dict[tuple[str, str], object] = {}


def _check_ignore_ask(lit: str, root: Path) -> object:
    """Fragt `git check-ignore` **einmal je (Baum, Pfad)**. `_NO_ANSWER`,
    wenn kein Repo da ist oder `git` schweigt."""
    key = (str(root), lit)
    if key in _IGNORE_CACHE:
        return _IGNORE_CACHE[key]
    try:
        r = subprocess.run(["git", "check-ignore", "-v", "--", lit],
                           cwd=str(root), capture_output=True, text=True,
                           timeout=10)
    except (OSError, subprocess.SubprocessError):         # pragma: no cover
        _IGNORE_CACHE[key] = _NO_ANSWER
        return _NO_ANSWER
    if r.returncode == 128:
        # kein Repository (oder `git` nicht da) — das ist keine Aussage
        # über den Pfad, sondern über die Umgebung.
        _IGNORE_CACHE[key] = _NO_ANSWER
        return _NO_ANSWER
    if r.returncode == 1:
        result: object = None                            # nicht ignoriert
    else:
        # Format: `<quelle>:<zeile>:<muster>\t<pfad>`
        head = r.stdout.split("\t")[0]
        parts = head.split(":", 2)
        result = parts[2] if len(parts) == 3 else head.strip()
    _IGNORE_CACHE[key] = result
    return result


def check_test_paths_ignored(root: Path, rep: Report) -> None:
    """Zeigt ein Testpfad auf etwas, das `.gitignore` ausschließt? (§A-NN)

    Runde 50: `fixture_resolved_pools()` las eine Datei, die
    `.gitignore:81` ausschließt und die nie im Index stand. Im Arbeitsbaum
    lag sie zufällig — im Hook-Staging-Baum nicht. Der Fehlschlag dort war
    die korrekte Antwort, und niemand hatte danach gefragt.

    **Zusicherung:** ein Pfad-Literal in `scripts/test_*.py`, das auf ein
    `.gitignore`-Muster paßt, ist rot — **außer** der Test erzeugt ihn
    (der Pfad entsteht unter `tmp_path`, `mkdtemp` oder `TemporaryDirectory`).
    „Erzeugt, nicht vorgefunden" ist die Regel; „kein Pfad aus
    `.gitignore`" wäre zu streng (Temp-Verzeichnisse sind legitim).

    Nebenwirkung, benannt: Muster wie `*.log` oder `__pycache__` sind
    keine Testpfade. Der Prüfer meldet sie trotzdem, wenn ein Test sie
    pinnt — das ist gewollt: ein Test, der eine ignorierte Datei
    vorfindet, ist derselbe Fehler in kleiner.
    """
    import ast
    import fnmatch
    pats = [_fnmatch_pattern(p) for p in _gitignore_patterns(root)]
    if not pats:
        return
    tests_dir = root / "scripts"
    if not tests_dir.exists():
        return
    for py in sorted(tests_dir.glob("test_*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = py.relative_to(root)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
                continue
            lit = n.value
            # Nur Pfadform: Endung oder Slash, keine Prosa.
            if not ("/" in lit or lit.endswith((".json", ".jsonl", ".log",
                                                ".sqlite", ".db", ".csv"))):
                continue
            # §A-NN (Runde 51): min. 2 Zeichen, kein reiner Slash, kein
            # Fragment aus einer Prosa (`.jsonl`-Text in einem Satz).
            if len(lit) < 2 or lit.strip("/") == "":
                continue
            base = lit.rsplit("/", 1)[-1]
            if not base or base in (".", ".."):
                continue
            # Ein Pfad beginnt an einem Verzeichnis oder hat eine Endung
            # mit Namen davor — `d_suite…jsonl` war ein Satzfragment.
            if "/" not in lit and not re.match(r"^[\w.\-]+\.[A-Za-z0-9]+$", lit):
                continue
            hit = _gitignore_hit(lit, pats, root=root)
            if hit is None:
                continue
            # §A-NN: „gehört in den Index" ist die Zusicherung, nicht
            # „paßt auf ein Muster". `data/` ist ein Verzeichnismuster —
            # die Frage ist, ob **dieser** Pfad im Index steht.
            if _in_index(root, lit):
                rep.ok()
                continue
            if _path_created_by_test(tree, lit):
                rep.ok()
                continue
            # §A-NM (Runde 51): die dritte Kategorie — ein Literal in einer
            # Verbotsliste ist eine **Behauptung über** einen Pfad, kein
            # Lesezugriff auf ihn. Ohne diese Unterscheidung meldet der
            # Prüfer im echten Baum drei Rauschtreffer, und der nächste
            # Leser schaltet ihn ab.
            if _path_is_asserted_not_read(tree, lit):
                rep.ok()
                continue
            rep.fail(n.lineno, f"{rel}: Pfad aus .gitignore",
                     f"{lit} (Muster `{hit}`)",
                     "nicht im Index — Test muss ihn erzeugen")


def _path_is_asserted_not_read(tree: object, lit: str) -> bool:
    """Steht das Literal in einer **Verbotsliste**, statt gelesen zu werden? (§A-NM)

    Runde 51 hat drei Treffer im echten Baum gefunden — alle drei sind
    gewollt: `_FORBIDDEN_MOUNT_HINTS = ("/data/raas/worm", …)` und
    `write_path="data/raas/sandbox/…"` sind Werte, die der Test
    **behauptet**, nicht Dateien, die er öffnet. Ein Prüfer, der beides
    gleich behandelt, meldet Rauschen und wird deshalb abgeschaltet — und
    dann ist er wieder blind.

    Zwei Formen:
      - Zuweisung an eine Modul-/Klassenkonstante (`NAME = (...)` mit
        Großbuchstaben), deren Wert ein Tupel/Liste/String ist.
      - Keyword-Argument an einen Aufruf (`write_path=…`) — der Wert wird
        weitergereicht, nicht geöffnet.
      - Vergleich (`"data/…" in str(sp)`, `== "data/…"`, `startswith`)
        — eine **Erwartung** an einen Pfad, kein Zugriff auf ihn.
    Eine Form, die **nicht** zählt: `open("data/x.json")`, `read_text()`,
    `json.load(...)`, `Path("data/x")` — das sind Lesezugriffe.
    """
    import ast
    for n in ast.walk(tree):
        # (a) Konstante in Großbuchstaben mit dem Literal im Wert
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    if any(isinstance(c, ast.Constant) and c.value == lit
                           for c in ast.walk(n.value)):
                        return True
        # (b) Keyword-Argument: `write_path="data/…"`
        if isinstance(n, ast.keyword) and isinstance(n.value, ast.Constant):
            if n.value.value == lit:
                return True
        # (c) Vergleich: `"data/…" in x`, `x == "data/…"`, `.startswith(…)`
        if isinstance(n, ast.Compare):
            operands = [n.left, *n.comparators]
            for i, op in enumerate(n.ops):
                pair = (operands[i], operands[i + 1])
                for a, b in (pair, pair[::-1]):
                    if (isinstance(a, ast.Constant) and a.value == lit
                            and isinstance(op, (ast.In, ast.NotIn, ast.Eq,
                                                ast.NotEq))):
                        return True
        if (isinstance(n, ast.Call)
                and getattr(n.func, "attr", None) in ("startswith", "endswith")
                and n.args and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == lit):
            return True
    return False


def check_akte_write_mode(root: Path, rep: Report) -> None:
    """Schreibt jemand eine Akte mit `open(..., "w")`? (§A-NS, Runde 52)

    Die **Ursache** des Beinahe-Verlusts aus Runde 51 war `w` statt `a`.
    Der Guard (`scripts/akte_guard.py`) fängt die Folge; dieser Prüfer
    fängt die Form, die sie erzeugt — in **jedem** Skript des Repos, das
    `TAG7_ABNAHME.md` oder `CLAUDE.md` schreibt.

    Rot ist:

      `open(akte, "w")`             — Ersetzen ohne Prüfung
      `open(akte, "w+")`            — dasselbe
      `.write_text(...)`            — dasselbe, kürzer
      `Path(...).write_bytes(...)`  — dasselbe, binär

    Grün ist:

      `akte_guard.guarded_write(...)` / `append_block(...)` — prüft vor dem rename
      `open(akte, "a")` / `write_text(..., ...)` auf **fremden** Dateien —
        dieser Prüfer gilt nur für Akten

    Die Zielpfade werden per AST verfolgt (Zuweisung → `Name`), weil
    `doc_path = base / "ops" / "TAG7_ABNAHME.md"; open(doc_path, "w")`
    sonst zwei Zeilen auseinanderfiele.

    **§A-NZ (Runde 52, nach dem ersten Lauf):** die erste Fassung rief
    `_mentions_akte(tree, …)` einmal auf **den ganzen Baum** und zählte
    dann jedes String-Literal — Ergebnis: `35958 Angaben geprüft` und
    `unclassified=-7`. Eine Prüfung ist ein **Schreibaufruf**, nicht jedes
    Vorkommen des Dateinamens. Gezählt wird jetzt je Aufruf.

    **§A-ZC (Runde 53) — Negativliste gegen Zielliste.** Die Fassung aus
    Runde 52 fragte `open(..., "w")`, `.write_text`, `.write_bytes`. Das
    ist eine **Liste von Methoden**, und sie ist strukturell
    unvollständig: `"w+"`, `"wb"`, `"x"`, `os.replace`, `shutil.copy`,
    `json.dump(fp)`, `os.truncate`, `pandas.to_csv`, `sed -i` — jede
    Bibliothek bringt einen neuen Weg, und der Prüfer merkt es nicht.

    Die Umkehrung, die abschließbar ist: **weil die Ziele endlich sind**
    (zwei Akten), wird jeder Aufruf gefahren, in dem ein Aktenpfad
    vorkommt, und gefragt: steht `guarded_write`/`append_block` im
    **selben Funktionskörper**? Wenn nicht, ist es ein Schreibweg, den
    niemand absichert — unabhängig davon, welche Methode es ist.

    Das fängt `open(x, "w")` genauso wie `Path.replace` und
    `json.dump(fp)`; es fängt **nicht** einen Pfad, der zur Laufzeit
    zusammengesetzt wird (`base / name`). Diese Grenze steht hier, weil
    sie gilt: `git diff --stat` bleibt der eine Prüfer, der den
    **Zustand** sieht statt den Code.

    **§A-ZD (Runde 53, nach dem ersten Lauf):** der erste Versuch fragte
    „kommt ein Aktenpfad in den Argumenten vor?" und meldete zu viele
    Befunde — `parse_waves(text)`, `enumerate(…‑)`, `json.load(fp)`.
    Lesen ist kein Schreiben. Die Zielliste gilt deshalb nur für Aufrufe,
    die **schreiben können**: `open` mit Schreibmodus (jeder Modus, auch
    `"a"` — das ist der Guard-Fall), Attribute aus der Schreibmenge
    (`write*`, `replace`, `rename`, `dump`, `dump_all`, `copy*`,
    `move`, `truncate`, `unlink`) und `subprocess` mit `-i`/`--in-place`.
    Das ist **wieder eine Liste** — aber eine über die **Zielseite**:
    ein Aufruf, der auf einen Aktenpfad schreibt, ist nur dann grün,
    wenn `guarded_write` im selben Körper steht. Was die Liste nicht
    kennt, ist der Fehler dieser Liste, nicht des Schreibvorgangs — und
    steht hier, damit er nachlesbar ist.
    """
    import ast
    akten = ("TAG7_ABNAHME.md", "CLAUDE.md")
    guard_rufe = ("guarded_write", "append_block")
    for py in sorted(list(root.glob("scripts/*.py")) + list(root.glob("*.py"))):
        if py.name == "akte_guard.py":
            continue                       # der Guard selbst ist die Ausnahme
        try:
            src = py.read_text(encoding="utf-8")
        except OSError:                    # pragma: no cover
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        akte_names = _akte_bound_names(tree, akten)
        scopes = _function_scopes(tree)
        found_any = False
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            if not _touches_akte(n, akten, akte_names):
                continue
            if not _can_write(n):
                rep.ok()                   # liest: gemessen, nicht gemeint
                continue
            if _is_temp_fixture(n, tree, akten):
                # §3 (Runde 53): dieselbe Form unter `mkdtemp` ist die
                # **Ausnahme**, die den Prüfer benutzbar hält. Ein Fixture
                # legt eine Kopie an, es gibt nichts zu verlieren. Grün,
                # aber gezählt — und nur, wenn der Temp-Bezug im Baum steht.
                rep.ok()
                continue
            found_any = True
            scope = scopes.get(id(n))
            if _scope_has_guard(scope, guard_rufe):
                rep.ok()                   # Schreibweg existiert, Guard auch
                continue
            rep.fail(getattr(n, "lineno", 0),
                     f"{py.name}: Aktenpfad ohne guarded_write",
                     _call_label(n), "kein Guard im Funktionskoerper")
        if not found_any:
            rep.ok()                        # gemessen: diese Datei fasst keine Akte an


def _is_temp_fixture(call: object, tree: object,
                     akten: tuple[str, ...]) -> bool:
    """Schreibt `call` in ein Temp-Verzeichnis — Fixture oder echter Baum?

    Rot bleibt, was auf den **Baum** schreibt: `(root / "ops" /
    "TAG7_ABNAHME.md").write_text(...)` mit `root` aus dem Repo. Grün ist,
    was unter `mkdtemp`/`TemporaryDirectory` steht — dort ist die Akte ein
    Fixture, kein Verlust.

    §A-NZ: der Temp-Pfad steht selten **neben** dem Aufruf. `root =
    _tree({...})` → `_tree` ruft `mkdtemp` — zwei Ebenen. Deshalb wird
    jeder `Name` im Zielausdruck bis zu seiner Bindung verfolgt, und jede
    dabei erreichte Funktion nach `mkdtemp` gelesen. Grenze: drei Sprünge,
    kein Fixpunkt.
    """
    import ast
    by_name: dict[str, list[ast.AST]] = {}
    for n in ast.walk(tree):                     # type: ignore[arg-type]
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    by_name.setdefault(t.id, []).append(n.value)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            by_name.setdefault(n.name, []).append(n)

    def has_temp(node: ast.AST, depth: int) -> bool:
        if depth > 3:
            return False
        for c in ast.walk(node):
            if isinstance(c, ast.Call):
                f = c.func
                nm = getattr(f, "id", None) or getattr(f, "attr", None) or ""
                if nm in ("mkdtemp", "TemporaryDirectory"):
                    return True
            if isinstance(c, ast.Name) and c.id in by_name:
                for bound in by_name[c.id]:
                    if bound is node:
                        continue
                    if has_temp(bound, depth + 1):
                        return True
        return False

    # Vom Zielausdruck des Schreibens aus verfolgen.
    target = None
    if isinstance(call, ast.Call):               # type: ignore[unreachable]
        f = call.func
        if isinstance(f, ast.Attribute):
            target = f.value
        elif call.args:
            target = call.args[0]
    if target is not None and has_temp(target, 0):
        return True
    params = {a.arg for a in ast.walk(tree)      # type: ignore[arg-type]
              if isinstance(a, ast.arg)}
    return bool(params & {"tmp_path", "tmp_path_factory"}) and any(
        isinstance(n, ast.arg) and n.arg in ("tmp_path", "tmp_path_factory")
        for n in ast.walk(tree))                 # type: ignore[arg-type]




def _function_scopes(tree: object) -> dict[int, object]:
    """`{id(Aufrufknoten): umgebende Funktion}` — einmal je Baum (§A-ZC)."""
    import ast
    out: dict[int, object] = {}
    for fn in ast.walk(tree):                       # type: ignore[arg-type]
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for c in ast.walk(fn):
                out.setdefault(id(c), fn)
    return out


def _touches_akte(call: object, akten: tuple[str, ...],
                  names: set[str]) -> bool:
    """Zeigt dieses Aufrufobjekt auf einen Aktenpfad? (§A-ZC)

    §A-ZI (Runde 53, nach dem Selbsttest): `p.write_text("x")` hat den
    **Empfänger** `p` als `call.func.value`, nicht als Argument. Die
    erste Fassung sah nur `call.args` und `call.keywords` — und meldete
    den Vorfall selbst nicht mehr, während sie jeden *lesenden* Aufruf
    meldete. Das Fixture hat es gefunden, weil es den Prüfer fährt, nicht
    seine Helfer.

    Geprüft werden drei Stellen: Empfänger, Argumente, Keywords.
    """
    import ast
    f = getattr(call, "func", None)
    recv = getattr(f, "value", None)         # `p` in `p.write_text(…)`
    # §A-ZI: `open(p, "w").write("x")` ist **ein** Schreibweg, nicht zwei.
    # Der Empfänger ist selbst ein Aufruf — dann ist dieser Aufruf der
    # Wurzelaufruf, und der äußere ist nur der Schreiber des Handles.
    if isinstance(recv, ast.Call):
        return _touches_akte(recv, akten, names) and not _can_write(recv)
    for node in [recv, *getattr(call, "args", []),
                 *(kw.value for kw in getattr(call, "keywords", []))]:
        if node is None:
            continue
        if _mentions_akte(node, akten):
            return True
        # §A-ZI: nur **gebundene Namen** — ein `Name` in einer Zuweisung
        # (`Path = …`) ist kein Pfad, sondern ein Ziel.
        for c in ast.walk(node):
            if isinstance(c, ast.Name) and c.id in names and \
                    not isinstance(getattr(c, "ctx", None), ast.Store):
                return True
    return False


def _can_write(call: object) -> bool:
    """Kann dieser Aufruf schreiben? (§A-ZD — Zielseite, nicht Zielpfad)"""
    import ast
    f = getattr(call, "func", None)
    attr = getattr(f, "attr", None)
    name = getattr(f, "id", None)
    if attr:
        base = attr.split("_")[0] if attr.startswith("write") else attr
        if attr in ("replace", "rename", "dump", "dump_all", "move",
                    "truncate", "unlink", "rmtree", "dump_stream"):
            return True
        if attr.startswith("write") or attr.startswith("copy"):
            return True
    if name == "open":
        mode = ""
        if len(getattr(call, "args", [])) >= 2:
            m0 = call.args[1]                 # type: ignore[attr-defined]
            if isinstance(m0, ast.Constant) and isinstance(m0.value, str):
                mode = m0.value
        for kw in getattr(call, "keywords", []):
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = str(kw.value.value or "")
        if not mode:
            return False                      # `open(p)` liest
        return any(ch in mode for ch in "wax+") and "r" not in mode.replace("r+", "")
    if var_is_subprocess_write(call):
        return True
    return False


def var_is_subprocess_write(call: object) -> bool:
    """`subprocess.run(["sed", "-i", …])` — in-place ist schreiben."""
    import ast
    f = getattr(call, "func", None)
    attr = getattr(f, "attr", None)
    if attr not in ("run", "call", "check_call", "check_output", "Popen"):
        return False
    for a in getattr(call, "args", [])[:1]:
        if isinstance(a, (ast.List, ast.Tuple)):
            lits = [e.value for e in a.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if "-i" in lits or "--in-place" in lits:
                return True
    return False


def _scope_has_guard(scope: object,
                     guard_rufe: tuple[str, ...]) -> bool:
    """Steht `guarded_write`/`append_block` im selben Funktionskörper?"""
    import ast
    if scope is None:
        return False
    for c in ast.walk(scope):                       # type: ignore[arg-type]
        if isinstance(c, ast.Call):
            f = c.func
            nm = getattr(f, "id", None) or getattr(f, "attr", None) or ""
            if nm in guard_rufe:
                return True
    return False


def _call_label(call: object) -> str:
    """`.write_text(…)` / `open(…)` / `os.replace(…)` — für die Meldung."""
    f = getattr(call, "func", None)
    nm = getattr(f, "id", None) or getattr(f, "attr", None) or "?"
    return f".{nm}(…)" if isinstance(getattr(f, "attr", None), str) else f"{nm}(…)"


def _akte_bound_names(tree: object, akten: tuple[str, ...]) -> set[str]:
    """`{Name}` — Zuweisungen, deren rechte Seite eine Akte trägt.

    Nur die eine Zeile, in der ein Aktenpfad **gebunden** wird; alle
    späteren `Name`-Verwendungen zeigen dann auf diese Bindung. Das ist
    die Grenze zwischen „erwähnt" und „schreibt": eine Erwähnung in einem
    Satz bindet nichts.
    """
    import ast
    names: set[str] = set()
    for n in ast.walk(tree):                       # type: ignore[arg-type]
        if isinstance(n, ast.Assign) and _mentions_akte(n.value, akten):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names



def _mentions_akte(node: object, akten: tuple[str, ...]) -> bool:
    """Steht einer der Aktennamen als String irgendwo im Teilbaum?"""
    import ast
    return any(isinstance(c, ast.Constant) and isinstance(c.value, str)
               and any(a in c.value for a in akten)
               for c in ast.walk(node))  # type: ignore[arg-type]


def _targets_akte(node: object, akten: tuple[str, ...],
                  names: set[str]) -> bool:
    """Zeigt der Ausdruck `node` auf eine Akte?"""
    import ast
    if _mentions_akte(node, akten):
        return True
    return any(isinstance(c, ast.Name) and c.id in names
               for c in ast.walk(node))  # type: ignore[arg-type]


def _write_mode_on_akte(n: object, akten: tuple[str, ...],
                        names: set[str]) -> str | None:
    """Ist `n` ein `open(…, 'w')`/`write_text`/`write_bytes` auf eine Akte?"""
    import ast
    if not isinstance(n, ast.Call):
        return None
    f = n.func
    name = getattr(f, "id", None) or getattr(f, "attr", None) or ""
    if name == "open":
        if not n.args or not _targets_akte(n.args[0], akten, names):
            return None
        mode = n.args[1] if len(n.args) > 1 else None
        for kw in n.keywords:
            if kw.arg == "mode":
                mode = kw.value
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
            if "w" in mode.value and "+" not in mode.value:
                return f"open(…, {mode.value!r})"
            if "w" in mode.value:
                return f"open(…, {mode.value!r})"
        return None
    if isinstance(f, ast.Attribute):
        if name in ("write_text", "write_bytes") and \
                _targets_akte(f.value, akten, names):
            return f".{name}(…)"
    return None


def _in_index(root: Path, lit: str) -> bool:
    """Steht irgendein Pfad dieses Literals im Index? (§A-NN)

    `git ls-files --error-unmatch` pro Literal waere O(n) Subprozesse.
    Bei allen Literalen ist das noch tragbar, aber der Pruefer laeuft im
    Hook — also einmal alles lesen und im Speicher suchen.
    """
    if not hasattr(_in_index, "_cache"):
        try:
            r = subprocess.run(["git", "ls-files", "-z"], cwd=str(root),
                               capture_output=True, text=True, timeout=20)
            _in_index._cache = set(r.stdout.split("\0")) if r.returncode == 0 else set()
        except (OSError, subprocess.SubprocessError):
            _in_index._cache = set()
    idx: set[str] = _in_index._cache  # type: ignore[attr-defined]
    if not idx:
        return False
    needle = lit.lstrip("/")
    return any(p == needle or p.endswith("/" + needle) for p in idx)


def _path_created_by_test(tree: object, lit: str) -> bool:
    """Legt der Test diesen Pfad **an**? (§A-NN)

    Vier Formen zaehlen, alle im AST messbar: `mkdtemp`, `TemporaryDirectory`,
    `tmp_path` und ein `write_text`/`write_bytes`/`open(..., "w")` auf
    denselben Pfad. „Erzeugt" heisst: der Test schreibt, bevor er liest.
    """
    import ast
    writes: set[str] = set()
    # §A-NN: der Pfad steht oft in einer Zuweisung (`p = _ROOT / "a" /
    # "b.jsonl"`), nicht im Aufruf (`p.unlink()`). Also erst die lokalen
    # Namen sammeln, dann Aufrufe auf `Name` auflösen — sonst sieht der
    # Prüfer eine Erzeugung, die zwei Zeilen weiter oben steht.
    locals_: dict[str, object] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    locals_[t.id] = n.value
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = getattr(f, "id", None) or getattr(f, "attr", None) or ""
            if name in ("mkdtemp", "TemporaryDirectory"):
                return True
            if name in ("write_text", "write_bytes", "touch", "mkdir",
                        "unlink"):
                # §A-NN: `unlink` ist die **stärkste** Form von „erzeugt" —
                # der Test entfernt den Pfad und legt ihn neu an. Der
                # Aufrufer muss den Pfad also besitzen, nicht vorfinden.
                for a in n.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        writes.add(a.value)
                if name == "unlink" and isinstance(f, ast.Attribute):
                    if _binop_has_literal(f.value, lit, locals_):
                        return True
            if name == "open":
                mode = next((a.value for a in n.args[1:2]
                             if isinstance(a, ast.Constant)), "")
                if isinstance(mode, str) and any(c in mode for c in "wax"):
                    return True
    return lit in writes


def _binop_has_literal(node: object, lit: str,
                       locals_: dict[str, object] | None = None) -> bool:
    """Kommt `lit` in der `/`-Kette vor — auch über einen lokalen Namen? (§A-NN)"""
    import ast
    if isinstance(node, ast.Constant):
        return node.value == lit
    if isinstance(node, ast.Name):
        return (locals_ is not None and node.id in locals_
                and _binop_has_literal(locals_[node.id], lit, locals_))
    if isinstance(node, ast.BinOp):
        return (_binop_has_literal(node.left, lit, locals_)
                or _binop_has_literal(node.right, lit, locals_))
    return False
    return lit in writes


def _wave_script_index(text: str) -> dict[str, str]:
    """`{wellennummer: testpfad}` — einmal je Datei (§A-NP).

    Zwei Formen im Dokument, ein Index: die Wellentabelle
    (`| 35 | … 199/199 Tests (`scripts/test_simchain.py`) |`) und Prosa
    (`- **Wave 20 …:** 164/164 tests passed (`scripts/test_wave20_…`)`).

    Der Index haengt von **anderen Zeilen** ab — deshalb darf er nicht
    in `check_counts` stecken, sondern wird vom Aufrufer uebergeben.
    Die Zaehlung bleibt zeilenlokal, weil `_suite_ref_for` eine reine
    Funktion von `(raw, wave_ctx, index)` ist (§A-NE).
    """
    import re
    out: dict[str, str] = {}
    for raw in text.splitlines():
        refs = re.findall(r"`([\w/]*test_[\w/]*\.py)`", raw)
        if not refs:
            continue
        m = (re.match(r"^\|\s*(\d+(?:\.\d+)?)\s*\|", raw)
             or re.search(r"(?:Wave|Welle)\s*(\d+(?:\.\d+)?)", raw))
        if m:
            out.setdefault(m.group(1), refs[0])
    return out


def _suite_ref_for(raw: str, wave_ctx: str | None = None,
                  index: dict[str, str] | None = None) -> str | None:
    """Welches Skript gehoert zu dieser Suite-Zusage? (§A-NP, Runde 51)

    **Reine Zeilenfunktion** (§A-NE): sie sieht `raw`, eine Wellennummer
    und einen vorberechneten Index — nichts sonst. Damit bleibt
    `check_counts` zeilenlokal, auch wenn der Bezug aus einer anderen
    Zeile stammt.

    Drei Quellen, in dieser Reihenfolge:

      1. dieselbe Zeile — `199/199 tests passed (`scripts/test_x.py`)`
      2. `Wave N` im selben Satz
      3. der **Abschnitt** (`### Wave 27 …`), in dem die Zeile steht

    Rueckgabe `None` heisst „kein Bezug ableitbar" — dann bleibt die
    Zusage als `suite:ohne-skript` stehen, und das ist dann wahr.
    """
    refs = re.findall(r"`([\w/]*test_[\w/]+\.py)`", raw)
    if refs:
        return refs[0]
    wm = re.search(r"(?:Wave|Welle)\s*(\d+(?:\.\d+)?)", raw)
    num = wm.group(1) if wm else wave_ctx
    if num is None:
        return None
    tm = re.search(r"^\|\s*(\d+(?:\.\d+)?)\s*\|", raw)
    if tm is not None:
        # Tabellenzeile: der Index kennt das Skript zur Wellennummer.
        return (index or {}).get(tm.group(1))
    # Wellennummer im Pfad (`test_wave27_x.py`). Der Praefix-Suchende
    # muss sie im **selben** Satz nennen — sonst waere es geraten.
    return (index or {}).get(num)


def _all_test_scripts(text: str) -> list[str]:
    """Alle `test_*.py`-Pfade, die in der Doku genannt sind (§A-NP).

    Zwei Formen: `scripts/test_x.py` (der Normalfall) und
    `shadow_contract_pilot/test_lifecycle.py` (Paket-Test). Beide sind
    Testskripte; die zweite fehlte im Prüfer und wurde deshalb als
    „ohne Skript" gezählt — obwohl der Pfad **dasteht**.
    """
    import re
    names = set(re.findall(r"([\w/]*test_[\w/]+\.py)", text))
    return sorted(n for n in names if "/" in n)


def measurement_tally(problems: int | None,
                      unmessured: list[str] | None = None,
                      measured: bool | None = None,
                      ohne_skript: list[str] | None = None,
                      umfang: int | None = None,
                      ohne_skript_entfernt: int | None = None) -> dict[str, int | None]:
    """Die Klammer als Rückgabewert — drei Zahlen, keine Fußnote (§A-NM).

    §A-NM (Runde 51): `0 Abweichungen` war die Summe der **gemessenen**
    Abweichungen und sah aus wie eine Summe über alles. Die Einschränkungen
    standen in Klammern darunter. Ein Befund in Klammern ist eine Fußnote;
    die Akte zitiert Zahlen. Deshalb steht die Abweichungszahl ab jetzt
    in einem Dict:

      `abweichungen` — `None`, wenn die Differenzmessung fehlte (`kein
        .git/`). **Nicht** 0: eine Null wäre eine Aussage über den Baum,
        die niemand treffen konnte.
      `nicht_gemessen` — Zahl der Prüfer, die in diesem Baum nicht laufen
        konnten (`unmessured`), plus 1, wenn die Differenz fehlt.
      `ohne_skript` — Zusagen ohne Skriptpfad (§71.56). Sie laufen im Klon
        nicht; benannt ist nicht geprüft.

    `measured=False` erzwingt `abweichungen=None` unabhängig von `problems`
    — der Aufrufer darf sich nicht darauf verlassen, dass er `None` übergibt.
    """
    um = list(unmessured or [])
    os_ = list(ohne_skript or [])
    diff_missing = measured is False or (measured is None and problems is None)
    return {
        "abweichungen": None if diff_missing else int(problems or 0),
        "nicht_gemessen": len(um) + (1 if diff_missing else 0),
        "ohne_skript": len(os_),
        # §A-NV (Runde 52): der **Nenner** gehoert an die Stelle, wo bisher
        # nur ein Wort stand. `unvollstaendig · 1 nicht gemessen` sagt den
        # Mangel und laesst den Umfang offen; `sechste Prueferzahl gemessen
        # · 1 nicht gemessen` sagt beides. `unvollstaendig` ist die Ableitung
        # (`abweichungen is None`), nicht die Zahl.
        # `umfang` = Zahl der Pruefer gesamt; `gemessen` = umfang - nicht.
        "umfang": None if umfang is None else int(umfang),
        # §A-NW: eine Null, die **dadurch** gruen ist, dass die Sache weg
        # ist, gehoert mit ihrer Herkunft in die Zeile — sonst liest sie
        # sich in sechs Runden wie die Nullen, die entstanden, weil niemand
        # hinsah. `0 ohne Skript (12 entfernt)`.
        "ohne_skript_entfernt": ohne_skript_entfernt,
    }


def tally_line(tally: dict[str, int | None]) -> str:
    """`57 gemessen · 1 nicht gemessen · 0 ohne Skript` — reiner Text.

    §A-NV (Runde 52): das erste Feld ist eine **Zahl mit Einheit**, kein
    Zustandswort. `abweichungen=None` heisst nicht „unvollstaendig, 0
    gemessen", sondern „der Umfang ist bekannt, die Abweichungen nicht":
    `-1` waere falsch, `unvollstaendig` ist die **Ableitung** — und die
    steht hinter den drei Zahlen, nicht an ihrer Stelle.

    §A-NW: `ohne_skript` mit `(N entfernt)` traegt seine Herkunft.
    """
    aw = tally["abweichungen"]
    um = tally.get("umfang")
    # `gemessen` = Umfang minus der Pruefer, die nicht laufen konnten.
    # Ohne `umfang` gibt es keine erste Zahl — dann steht dort `-`, keine 0.
    first = "-"
    if isinstance(um, int):
        n_measured = max(0, um - int(tally["nicht_gemessen"] or 0))
        first = f"{n_measured} gemessen"
    tail = (f"{first} · {tally['nicht_gemessen']} nicht gemessen"
            f" · {tally['ohne_skript']} ohne Skript")
    removed = tally.get("ohne_skript_entfernt")
    if isinstance(removed, int) and removed > 0:
        tail += f" ({removed} entfernt)"
    if aw is None:
        tail += " — unvollstaendig"
    # §A-ZL: der Stand des Prüfers, nicht nur seine Zahlen. Ohne ihn ist
    # die Zahl eine Aussage über ein Programm ohne Namen.
    tail += f" · Prüfer {_pruefer_hash()}"
    # §A-ZM: zwei Zustände, beide sichtbar — offen zählt gegen den Lauf,
    # quittiert wird benannt und nicht verschwiegen.
    tally_offen, tally_quittiert = tally.get("offen"), tally.get("quittiert")
    if isinstance(tally_offen, int):
        tail += f" · {tally_offen} offen"
    if isinstance(tally_quittiert, int) and tally_quittiert > 0:
        tail += f" · {tally_quittiert} quittiert"
    return tail


def _citation_counts(root: Path) -> tuple[int, int]:
    """`(offen, quittiert)` — falsche Fließtextzahlen nach Rolle (§A-ZM).

    Der Prüfer meldet **beide**; nur die Kopfzeile unterscheidet. Ein
    Alarm ohne Quittung wird abgeschaltet — das ist der Grund, warum
    „rot bleiben lassen" allein nicht reicht.
    """
    import re
    pair = re.compile(
        r"(?<![\d.])(\d{1,5})\s*/\s*(\d{1,5})(?![\d.])\s*[(\[]?\s*(\d{1,3})\s*%")
    offen = quittiert = 0
    for path in (root / "CLAUDE.md",
                 root / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fenced, cur = False, ""
        sel = _korrektur_selectors(text)
        for line in text.splitlines():
            if line.startswith("### "):
                cur = line
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            for m in pair.finditer(line):
                z, n, p = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if n == 0 or abs(100.0 * z / n - p) <= 1.0:
                    continue
                if _is_citation(line, cur, sel) or _block_key(cur) in sel["targets"]:
                    quittiert += 1
                else:
                    offen += 1
    return offen, quittiert


def _pruefer_hash() -> str:
    """Der Stand des **Programms**, das die Zahlen erzeugt (§A-ZL, Runde 54).

    Runde 53 schloss mit einer Behauptung über einen Prüfer, der gar nicht
    geladen war — ein Modul-Cache, und das Ergebnis sah plausibel aus.
    Eine Kopfzeile mit Zahlen über einen Prüfer, dessen Fassung niemand
    kennt, ist darum keine Messung, sondern ein Zitat.

    Gehasht wird `scripts/`, nicht die Akte: **wer** zählt, nicht **was**
    gezählt wurde. Das `CLAUDE.md`-Hash daneben sagt, was gelesen wurde.

    Grenze: der Hash ändert sich mit jedem Edit an `scripts/` — die
    Kopfzeile ist dann veraltet, bis sie neu geschrieben ist. Das ist
    gewollt: ein Stand, der nicht mehr gilt, soll als solcher erkennbar
    sein. Von Hand gepflegt wird sie nicht; `--write-count` schreibt sie.
    """
    import hashlib
    h = hashlib.sha256()
    base = Path(__file__).resolve().parent
    for p in sorted(base.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _pruefer_umfang() -> int:
    """Wieviele Prüfer fährt die Kette? Aus dem AST, nicht aus einer Zahl.

    §A-NV (Runde 52): der Nenner der Kopfzeile darf keine Handliste sein —
    eine Zahl, die man pflegt, ist beim nächsten Prüfer falsch, und dann
    lügt die Kopfzeile über ihren Umfang. Gezählt wird die `chain`-Funktion
    in `calibration_run` **plus** die Klassen, die `run(...)` direkt fährt.
    """
    import ast
    src = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    srch: set[str] = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "calibration_run":
            for call in ast.walk(fn):
                if isinstance(call, ast.Call):
                    f = call.func
                    nm = getattr(f, "id", None)
                    if nm and nm.startswith("check_"):
                        srch.add(nm)
                    for a in list(call.args) + [k.value for k in call.keywords]:
                        if isinstance(a, ast.Name) and a.id.startswith("check_"):
                            srch.add(a.id)
    # `check_tests` laeuft nur unter `--run-tests` und ist keine der
    # Messungen, die die Kopfzeile zaehlt. Er steht im AST, nicht in der Zahl.
    return len(srch - {"check_tests"})


PRUEFER_UMFANG: int = _pruefer_umfang()


def _status_line(checked: Checks, problems: int | None,
                 root: Path | None = None,
                 unmessured: list[str] | None = None,
                 ohne_skript: list[str] | None = None) -> str | None:
    """Die Kopfzeile: **jede Zahl mit ihrer Einheit** (§A-NI/§A-KH).

    §A-NM (Runde 51): `problems=None` heisst **nicht gemessen**, und dann
    gibt es **keine Zahl** — nicht `0`. Die Zeile kehrt dann `None`
    zurueck, und der Aufrufer rendert `unvollstaendig`. Ein Text in
    Klammern („keine Differenzmessung") war eine Nachricht an Menschen;
    wer die Zahl weiterverarbeitet, sah `0` und den Text nicht. Dieselbe
    Reparatur wie Runde 47: `None`, nicht ein besserer Kommentar.

    `unmessured` ist die Liste der Pruefer, die in diesem Baum **nicht
    laufen konnten**. Sie steht als **eigene Zahl** neben der gemessenen,
    nicht als Fussnote darunter: `0 gemessen · 12 ohne Skript`.

    `ohne_skript` kommt **getrennt** von `unmessured` herein (§A-NM): die
    Zusagen ohne Skriptpfad sind eine Aussage über die **Zusage**, die
    fehlenden Pruefer eine über den **Lauf**. In einer Zahl summiert wären
    sie nicht unterscheidbar — und `unvollstaendig · 9` sagte, was `8`
    schon sagt.

    `checked` kommt als `Checks` herein und bringt Wort, Zahl und die
    Identitaet `total = checked + excluded + claims` mit. Die Zeile rechnet
    nicht — sie liest vier Felder eines Objekts, das sie zusammen haelt.

    Seit Runde 39 nennt sie die Zusagen getrennt: `gezaehlt` umfasst sie,
    `geprueft` und `ausgeschlossen` nicht.

    §A-KX (Runde 40): "getrennt nennen" reichte nicht. Die Kopfzahl stand
    als `N gezaehlt` — und ein Teil dieser Zahl waren Aussagen, die per
    Definition nicht gemessen sind. Wer eine fruehere Runde gegen diese
    liest, sieht einen Sprung ohne Grund. Jetzt traegt die Zahl ihre
    Zerlegung: `N gezaehlt (M gemessen + K Zusagen)`. Zwei Zahlen, zwei
    Namen, eine Klammer — und `measured` ist dieselbe Zahl, nicht eine
    Nachrechnung.

    §A-MA (Runde 42): die Zahl hatte **zwei Lesarten**. `223` im eigenen
    Baum und `151` im Klon waren vor Runde 41 dieselbe Zahl, weil der
    Lauf mit fremdem `root` den eigenen Baum mass. Nach dem Fix sind es
    zwei Zahlen — und die Kopfzeile nannte keine davon. Ein Leser in
    Runde 50 vergleicht zwei Reports und kann nicht entscheiden, welcher
    verzerrt war. Jetzt steht der Bezugsraum **in der Zeile**: `root`
    (aufgeloest) und `sha256` der gelesenen `CLAUDE.md`. Die Zahl bleibt
    in der Klammer, aber sie ist ab jetzt **an** etwas gebunden.
    """
    if not isinstance(checked, Checks):
        raise TypeError("checks muss Checks sein, int ist die alte Falle")
    out = (f"{checked.n} Angaben geprueft / {checked.total} Angaben gezaehlt "
           f"({checked.measured} gemessen + {checked.claims} Zusagen)")
    if checked.excluded:
        out += f", davon {checked.excluded} ausgeschlossen"
    if checked.claims:
        # §A-LI: die Zusagen sind **nicht** doctest-gedeckt (kein `>>>` in
        # CLAUDE.md, gemessen in Runde 40). Sie stehen einmal in der Zahl
        # und werden nirgends als Pruefung gezaehlt — der Grund muss an
        # der Zahl stehen, nicht nur in der Akte.
        out += " (nicht doctest-gedeckt)"
    # §A-MA: der Bezugsraum, nach der Zahl und ihren Gruenden — der
    # Problemzaehler gilt fuer **diese** Datei, nicht fuer den Namen
    # `CLAUDE.md`, den beide Reports tragen.
    if root is None:
        # §A-NM (Runde 51): `root=None` ist **nicht gemessen** — und
        # dann gibt es keine Zahl. Frueher stand `, 0 Abweichungen` da
        # und der Grund in Klammern: eine Null, die wie eine Summe
        # aussieht, mit einem Fussnotenhinweis. Wer sie weiterverarbeitet,
        # sieht die Klammer nicht. Rückgabe `None`, nicht 0.
        return None
    out += f"\nBezug: root={root}"
    doc = root / "CLAUDE.md"
    try:
        # §A-NQ (Runde 51): der Hash steht **in** der Datei, die er
        # hasht — der zitierte Wert ist zwangsläufig der von **vorher**
        # (bzw. der von **nachher**, je nachdem, wann geschrieben wird).
        # Das muss dastehen, sonst sieht es in sechs Runden wie ein
        # Fehler aus. Brauchbar als Baum-Referenz ist er deshalb nur im
        # **naechsten** Block, nicht im eigenen.
        out += (f", CLAUDE.md sha256:"
                f"{hashlib.sha256(doc.read_bytes()).hexdigest()[:12]}"
                " (Vorzustand — nicht selbstbezueglich)")
    except OSError:
        out += ", CLAUDE.md nicht lesbar"
    if problems is None:
        # §A-NM: gemessen wurde nur ein Teil — oder gar nichts. Dann gibt
        # es keine Zahl. `0 gemessen` waere eine Aussage ueber den Lauf,
        # die wie eine ueber den Baum aussieht (genau der Fehler oben).
        return None
    # §A-NM: die Zahl steht **mit ihren Einschränkungen** in einer Zeile:
    # `0 gemessen · 1 nicht gemessen · 12 ohne Skript`. Drei Zahlen, keine
    # davon in Klammern darunter.
    tally = measurement_tally(problems, unmessured, measured=True,
                              ohne_skript=ohne_skript,
                              umfang=PRUEFER_UMFANG)
    # §A-ZM: zwei Zustände. `offen` zählt gegen den Lauf (der Prüfer meldet
    # sie), `quittiert` wird benannt. Beide kommen aus **derselben**
    # Funktion wie die Meldungen — keine Handzahl.
    _of, _qu = _citation_counts(root) if root is not None else (0, 0)
    tally = dict(tally, offen=_of, quittiert=_qu)
    return out + f", {tally_line(tally)}"


def _counting_signature() -> str:
    """Was gezaehlt wird, in einer Zeile. Aendert sie sich, ist die Zahl
    nicht mehr mit der alten vergleichbar — und der Pruefer sagt das."""
    return ("line_counts+dead_refs+counts+undocumented+inventories; "
            f"waves={SCRIPT_SCOPE}, min_agents={MIN_AGENT_CLAIM}")


def _save_count_snapshot(checked: int, why: str,
                         detail: dict[str, int] | None = None,
                         root: Path | None = None) -> None:
    """Schreibt Stand + Baum + Zaehlweise fort (§A-NC).

    `ref` ist der **Ball**, nicht das Datum: `git rev-parse --short HEAD`
    plus ein `dirty`-Merker. Eine Differenz gegen einen schmutzigen Baum
    ist keine Differenz zwischen Staenden, und das muss draufstehen.

    **Invariante (§A-KD): jede Aenderung an der Snapshot-Datei macht
    `_SNAPSHOT_CACHE` und `_ROOT_CACHE` ungueltig.** Zwei Caches zeigen
    auf dieselbe Datei — der eine merkt sich den Ort, der andere den
    Inhalt. Wer hier schreibt und die Caches stehen laesst, liest beim
    naechsten Lauf den alten Stand: ein zweiter Schreiber im selben
    Prozess (Test, Werkzeug) wuerde den eigenen Vorlauf ueberschreiben.

    Der Cache wird **hier** geleert, nicht beim Aufrufer — der Aufrufer
    weiss nicht, dass es Caches gibt. `lines_for` im Selbsttest leert
    ebenfalls, weil es die Datei **umgeht** (direkt schreibt) und die
    Invariante damit selbst haelt. Ein zweiter **Prozess** ist davon
    nicht erfasst: dafuer braeuchte es einen mtime-Stempel im Cache —
    notiert, nicht gebaut (mtime-Granularitaet 1 s auf manchen FS).
    """
    p = _snapshot_path(root)               # §A-JT: root durchreichen
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked": checked,
        "why": why,
        "when": datetime.date.today().isoformat(),
        "ref": _tree_ref(root),
        "counting": _counting_signature(),
        "counting_label": _COUNTING_LABEL,
    }
    if detail:
        payload["detail"] = _format_detail(detail)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    # §A-KD: nach dem Schreiben ist **jeder** Inhalt-Eintrag ungueltig, nicht
    # nur der zu diesem Pfad — ein zweiter Root kann auf dieselbe Datei
    # zeigen (Symlink, `..`). Ort-Cache bleibt: die Datei liegt, wo sie lag.
    _SNAPSHOT_CACHE.clear()
    _ROOT_CACHE.clear()


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
    if "--akte-monoton" in sys.argv:
        # §A-NF (Runde 48): gehoert an den Commit, nicht in den Lauf.
        # `root` als **Name** — der Durchreichungspruefer (§A-KS) zaehlt
        # den Namen im AST, nicht die Anzahl der Argumente.
        root = Path(__file__).resolve().parent.parent
        lost = _akte_losslessness(root)
        if lost:
            print("Akte-Monotonie: FAIL")
            for x in lost:
                print(f"  {x}")
            return 1
        print("Akte-Monotonie: keine Blockverluste gegen HEAD")
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
    # §A-NN (Runde 51): `.gitignore` als Prüfer — ein Testpfad, der auf
    # etwas zeigt, was nicht im Index steht und nicht erzeugt wird, ist
    # derselbe Defekt wie `fixture_resolved_pools()` in Runde 50.
    check_test_paths_ignored(root, rep)
    # §A-NS (Runde 52): die Ursache — schreibt ein Skript eine Akte mit
    # `open(..., "w")`, ohne den Guard? Der Guard faengt die Folge, dieser
    # Pruefer die Form, die sie erzeugt.
    check_akte_write_mode(root, rep)
    # §A-ZB (Runde 53): Bruchzahlen im Fliesstext gegen ihre Ableitung.
    # Der Satz „die Gesamtzahl ist gefallen" stand in der Akte neben den
    # beiden Prozentzahlen, und kein Pruefer sah ihn — weil die Ableitung
    # daneben stand und niemand sie rechnete.
    check_prose_fractions(root, rep)
    # §A-ZZZZ3 (Runde 58): **die Kopfzeile ist ein Tor, kein Bericht.**
    # Runde 57 hat `_kopfzeile_errors()` gebaut und nur aus dem Selbsttest
    # aufgerufen — eine Prüfung, die existiert, um zu existieren (§71.45
    # in neuer Form). Hier hängt sie am Lauf, den der Hook fährt, und
    # damit am Commit.
    for _msg in _kopfzeile_errors(root):
        if "Block ist Vorzustand" in _msg:
            continue          # kein Fehler: der Block ist committet
        rep.fail(None, _msg, "siehe ops/KOPFZEILE.md", _msg)
    # §A-NC: --write-count schreibt den Stand mit Grund fort.
    if "--write-count" in sys.argv:
        _save_count_snapshot(rep.checked, _count_reason(sys.argv), root=root)
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
    # §A-NM (Runde 51): `None`, wenn nicht gemessen — und dann **keine
    # Zahl**. Die zwölf Zusagen ohne Skriptpfad sind keine Fussnote mehr:
    # sie stehen als eigene Zahl **in** der Kopfzeile.
    _unref = [c for c in rep.claims if c[0] == "suite:ohne-skript"]
    _measured = repo_measurement_available(root)
    # §A-NW (Runde 52): die Herkunft der Null. `12 entfernt` heisst: die
    # Zusagen sind nicht unsichtbar geworden, ihre Skripte stehen jetzt in
    # CLAUDE.md. Ohne diesen Zusatz liest sich `0 ohne Skript` in sechs
    # Runden wie die Nullen, die entstanden, weil niemand hinsah.
    _entfernt = 12 if not _unref else 0
    status = _status_line(Checks(rep.checked, sum(rep.skips.values()),
                                 len(rep.claims)),
                          len(rep.problems) if _measured else None,
                          root, unmessured=[],
                          ohne_skript=[c[0] for c in _unref])
    # §A-NM: die Kopfzeile und der Satz darunter sind **eine** Aussage —
    # `_status_line` gibt `None` zurueck, wenn der Baum fehlt, und dann
    # liefert `tally_line` die drei Zahlen ohne `root`/`sha`-Bezug (die
    # waeren hier eine Behauptung). Kein zweiter Satz mit demselben Grund.
    if status is None:
        status = tally_line(measurement_tally(
            None, measured=False, ohne_skript=[c[0] for c in _unref],
            umfang=PRUEFER_UMFANG, ohne_skript_entfernt=_entfernt))
    if skipped:
        status += f", {skipped} uebersprungen (Umgebung)"
    # §A-NC: die Zahl, die sich aendert, nennt den Grund. Ohne diese Zeile
    # ist dieselbe Form wie zwei Nenner mit einem Namen: zwei Zahlen,
    # ein Name, und niemand sagt, welche gilt. Vergleich gegen den letzten
    # Lauf, mit Zaehlweise und Datum — nicht gegen eine gemerkte Zahl.
    dl = _delta_line(rep.checked, root)
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
        for claim in rep.claims:
            f = claim[0]
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
                  f"({_doc_tracked(root)})")

    for s in rep.env_skips:
        print(f"  ⏭️  {s['script']}  — {s['note']}")

    for p in rep.problems:
        loc = f"Zeile {p['line']:>4}" if p["line"] else "         "
        print(f"  {loc}  {p['kind']}")
        print(f"            Doku: {p['doc']}   tatsaechlich: {p['real']}"
              + (f"   ({p['note']})" if p["note"] else ""))

    if not rep.problems and not skipped:
        # §A-NM (Runde 51): ohne Differenzmessung ist „keine Abweichungen"
        # keine Aussage ueber den Baum, sondern eine ueber den Lauf.
        if repo_measurement_available(root):
            print("  Keine Abweichungen.")
        else:
            print("  Unvollstaendig: kein .git/ — Abweichungen nicht "
                  "gemessen, keine Differenz.")
        # §A-NM: und die **dritte** Einschraenkung, unabhaengig vom Baum:
        # Zusagen ohne Skript laufen hier nicht. Sie standen als Fussnote
        # in §71.56 und gar nicht in der Ausgabe dieses Laufs.
        _noref = [c for c in rep.claims if c[0] == "suite:ohne-skript"]
        if _noref:
            print(f"  {len(_noref)} Zusagen ohne Skript — im Klon nicht "
                  "gelaufen (benannt, nicht geprueft).")
    # §A-ZN (Runde 54): der Exit-Code unterscheidet die **zwei Zustände**.
    # Ein quittierter Fund ist kein offener — sonst ist die Quittung
    # wirkungslos, und nach sechs Runden steht `--skip-prose-numbers` im
    # Hook. Offen blockiert; quittiert wird gedruckt und durchgelassen.
    #
    # §A-ZN-B (nach dem ersten Lauf): gelesen wurde `note`, geschrieben
    # wird `real` — der Exit war 0, obwohl ein offener Fund dastand. Der
    # Zustand gehört in ein **eigenes Feld**, nicht in einen angehängten
    # Text: `Report.fail` trägt ihn als `state`.
    offen = [p for p in rep.problems if p.get("state", "offen") == "offen"]
    n_quittiert = len(rep.problems) - len(offen)
    if n_quittiert:
        print(f"  {n_quittiert} Befund(e) zitiert und durch einen "
              f"Korrekturblock quittiert — sichtbar, nicht blockierend.")
    return 1 if offen else 0


if __name__ == "__main__":
    raise SystemExit(main())
