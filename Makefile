# Agent X — Pitch & Development Makefile
# ============================================================================
# Ein-Klick-Start für die Live-Vorführung vor dem Kämmerer.
#
#   make pitch       Startet den vollständigen Demo-Stack (Bunker, Z3, HSM)
#   make test        Führt alle Test-Suiten aus (Wave 33, Bunker, Z3, Finale)
#   make stop        Stoppt alle Container
#   make verify      Pre-Pitch-Verifikation: Health-Checks + Compliance
#   make clean       Räumt alle Container, Images und Volumes auf

.PHONY: pitch test stop verify clean

# ── Pitch: Live-Vorführung ───────────────────────────────────────────

pitch:
	@echo "🏛️  AGENT X — PITCH-STACK"
	@echo "=========================="
	docker compose -f docker-compose.mock.yml up -d --build --wait
	@sleep 3
	@echo ""
	@echo "✅ Stack läuft:"
	@echo "   Kämmerer-Dashboard:  http://localhost:8501"
	@echo "   Z3-Theorem-Prover:   http://localhost:8000"
	@echo "   Compliance-Check:    http://localhost:8000/compliance"
	@echo "   Health:              http://localhost:8000/health"
	@echo ""
	@echo "   Bunker 01 Rathaus:   UDP :8881"
	@echo "   Bunker 02 Stadtwerke:UDP :8882"
	@echo "   Bunker 03 Klinikum:  UDP :8883"
	@echo "   Bunker 04 Feuerwehr: UDP :8884"
	@echo "   Bunker 05 Uni:       UDP :8885"
	@echo ""
	@echo "🚀 Pitch-Stack bereit. Jetzt: make verify"

# ── Test: Alle Suiten ────────────────────────────────────────────────

test:
	@echo "🧪 AGENT X — FULL TEST SUITE"
	@echo "============================="
	python3 scripts/test_wave33_survival.py
	python3 tests/test_bunker_integration.py
	python3 tests/test_bunker_e2e.py --demo
	python3 tests/test_z3_integration.py
	python3 scripts/test_finale.py
	python3 scripts/test_esp32_firmware.py
	@echo ""
	@echo "✅ Alle Test-Suiten durchlaufen"

# ── Verify: Pre-Pitch-Healthcheck ─────────────────────────────────────

verify:
	@echo "🔍 AGENT X — PRE-PITCH VERIFICATION"
	@echo "==================================="
	@echo ""
	@echo "0a. Dashboard Health:"
	@curl -s -o /dev/null -w "   HTTP %{http_code}" http://localhost:8501/_stcore/health 2>/dev/null && echo " ✅" || echo " ❌"
	@echo ""
	@echo "0b. SON-Report (Test-Suiten)..."
	@python3 scripts/check_claude_md.py --run-tests --json-report archive_b2g/son_report.json 2>/dev/null || true
	@echo ""
	@echo "0c. Bridge-Siegel (Manifest)..."
	@python3 scripts/check_bridge_seal.py || true
	@echo ""
	@echo "1. Z3 Health:"
	@curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "   ❌ Z3-Service nicht erreichbar"
	@echo ""
	@echo "2. Compliance:"
	@curl -s http://localhost:8000/compliance | python3 -c "import sys,json; d=json.load(sys.stdin); s=d['summary']; print(f'   verified={s[\"verified\"]} attested={s[\"attested\"]} failed={len(s[\"failed_probes\"])} — {s[\"verdict\"]}')" 2>/dev/null || echo "   ❌ Compliance-Endpoint nicht erreichbar"
	@echo ""
	@echo "3. BHO-Proof:"
	@curl -s -X POST http://localhost:8000/prove_bho_invariant \
	  -H 'Content-Type: application/json' \
	  -d '{"sector":"BAU","gross_amount":45000,"net_amount":36000,"tax_amount":6750,"retention_amount":2250}' \
	  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'   {d[\"status\"]}: Δ={d[\"bho_delta_eur\"]}€ ({d[\"proof_time_us\"]:.0f}µs)')" 2>/dev/null || echo "   ❌ BHO-Proof fehlgeschlagen"

# ── Stop ──────────────────────────────────────────────────────────────

stop:
	docker compose -f docker-compose.mock.yml down

# ── Clean ─────────────────────────────────────────────────────────────

clean:
	docker compose -f docker-compose.mock.yml down -v
	docker system prune -f

# ═══════════════════════════════════════════════════════════════════════════
# Wave 35–37: SimChain · MultiChain · Demo Pipeline · Settlement
# ═══════════════════════════════════════════════════════════════════════════

.PHONY: demo-all demo-pipeline demo-chaos demo-coastal demo-valhalla demo-crew \
        demo-abfang demo-simchain demo-settlement demo-protocol \
        api dashboard full-pitch test-all

# ── All Demos (sequential) ────────────────────────────────────────────

demo-all: demo-settlement demo-abfang demo-simchain demo-chaos demo-crew \
          demo-coastal demo-valhalla demo-protocol
	@echo ""
	@echo "✅ All 8 demos complete"
	@echo ""

# ── Individual Demos ──────────────────────────────────────────────────

demo-pipeline:
	@echo "🎭 9-Agent Pipeline (Wave 37)"
	python3 -c "from agents_b2g.demo.demo_orchestrator import run_demo; run_demo()"

demo-abfang:
	@echo "💥 Z3 Intercept Demo"
	python3 scripts/demo_abfang.py

demo-simchain:
	@echo "📡 SimChain 100 Cycles"
	python3 scripts/demo_simchain.py 100

demo-chaos:
	@echo "💥 Chaos Matrix — 10 Attack Scenarios"
	python3 scripts/demo_chaos.py

demo-coastal:
	@echo "⚓ Coastal Defense Mission"
	python3 scripts/demo_coastal.py

demo-crew:
	@echo "🚢 Agent Crew Pipeline (Default-Deny)"
	python3 -c "import asyncio; from agents_b2g.crew import demo_crew_pipeline; asyncio.run(demo_crew_pipeline())"

demo-valhalla:
	@echo "🏛️ Valhalla ZK Honor Protocol"
	python3 -c "from agents_b2g.valhalla import demo_valhalla; demo_valhalla()"

demo-protocol:
	@echo "📡 Surface-Subsurface Protocol"
	python3 -c "from agents_b2g.protocol import demo_surface_protocol; demo_surface_protocol()"

# ── Settlement Demos (D01 → D02 → D03 → DAG → C09 → Forensic) ───────

demo-settlement:
	@echo "🌊 Settlement Pipeline"
	@echo "  ── D01 ZK Settlement ──"
	python3 -c "from agents_b2g.settlement import demo_zk_settlement; demo_zk_settlement()"
	@echo "  ── D02 Forensic Repair ──"
	python3 -c "from agents_b2g.settlement import demo_forensic_repair; demo_forensic_repair()"
	@echo "  ── D02 Forensic API ──"
	python3 -c "from agents_b2g.settlement import demo_forensic_api; demo_forensic_api()"
	@echo "  ── D03 Emergency Rescue ──"
	python3 -c "from agents_b2g.settlement import demo_emergency_rescue; demo_emergency_rescue()"
	@echo "  ── DAG State Transition ──"
	python3 -c "from agents_b2g.settlement import demo_state_transition; demo_state_transition()"
	@echo "  ── C09 Ingest Handler ──"
	python3 -c "from agents_b2g.settlement import demo_c09_ingest_handler; demo_c09_ingest_handler()"

# ── APIs ──────────────────────────────────────────────────────────────

api:
	@echo "🔌 Starting REST APIs..."
	@echo "   MultiChain API:    http://localhost:8600/docs"
	@echo "   Telemetry Ingest:  http://localhost:8000/docs"
	@echo "   Chaos Matrix:      http://localhost:8080/docs"
	@echo "   Press Ctrl+C to stop"
	uvicorn services.multichain_api:app --host 0.0.0.0 --port 8600 &
	uvicorn services.telemetry_ingest.main:app --host 0.0.0.0 --port 8000 &
	uvicorn services.chaos_matrix:app --host 0.0.0.0 --port 8080 &
	wait

# ── Dashboards ────────────────────────────────────────────────────────

dashboard:
	@echo "📊 Starting Streamlit Dashboards..."
	@echo "   SimChain Dashboard:  http://localhost:8501"
	@echo "   MultiChain Dashboard:http://localhost:8502"
	@echo "   Press Ctrl+C to stop"
	streamlit run agents_b2g/simchain/streamlit_app.py --server.port 8501 &
	streamlit run agents_b2g/multichain/streamlit_app.py --server.port 8502 &
	wait

# ── WASM Build (TinyGo required) ─────────────────────────────────────

.PHONY: wasm
TINYGO ?= $(shell which tinygo 2>/dev/null || echo /opt/homebrew/bin/tinygo)

.PHONY: wasm
wasm:
	@echo "🪂 Building WASM paratrooper modules..."
	@if [ ! -x "$(TINYGO)" ]; then \
		echo "  ⚠️ TinyGo not found at $(TINYGO)"; \
		echo "  Install: brew tap tinygo-org/tools && brew install tinygo go"; \
		exit 1; \
	fi
	@for src in agents/ephemeral/src/f0*.go; do \
		name=$$(basename $$src .go); \
		echo "  $(TINYGO) build -o agents/ephemeral/wasm/$$name.wasm -target wasi $$src"; \
		$(TINYGO) build -o agents/ephemeral/wasm/$$name.wasm -target wasi $$src || exit 1; \
	done
	@echo "✅ WASM modules ready in agents/ephemeral/wasm/"

# ── Full Pitch (start APIs + run all demos) ───────────────────────────

full-pitch:
	@echo ""
	@echo "████████████████████████████████████████████████████████████████████████"
	@echo "█                                                                      █"
	@echo "█              🎬 AGENT X — FULL PITCH DEMO                             █"
	@echo "█              30-Second Complete System Walkthrough                   █"
	@echo "█                                                                      █"
	@echo "████████████████████████████████████████████████████████████████████████"
	@echo ""
	@sleep 1
	@echo "ACT I: The Pipeline (9 Agents, 8 Unique Sicker Rates)"
	@echo "────────────────────────────────────────────────────────────"
	python3 -c "from agents_b2g.demo.demo_orchestrator import run_demo; run_demo()" 2>&1 | tail -12
	@sleep 1
	@echo ""
	@echo "ACT II: The Attacks (Z3 Intercept + Chaos Matrix)"
	@echo "────────────────────────────────────────────────────────────"
	python3 scripts/demo_abfang.py 2>&1 | tail -14
	@sleep 1
	@echo ""
	@echo "ACT III: The Defense (Coastal + Crew + Valhalla)"
	@echo "────────────────────────────────────────────────────────────"
	python3 scripts/demo_coastal.py 2>&1 | tail -8
	@sleep 1
	@echo ""
	@echo "ACT IV: The Depths (Settlement D01→D02→D03→C09)"
	@echo "────────────────────────────────────────────────────────────"
	python3 -c "from agents_b2g.settlement import demo_c09_ingest_handler; demo_c09_ingest_handler()" 2>&1 | tail -8
	@sleep 1
	@echo ""
	@echo "████████████████████████████████████████████████████████████████████████"
	@echo "  🎉 FULL PITCH COMPLETE"
	@echo "  Total elapsed: ~15 seconds"
	@echo "  Components demonstrated: 9 agents · 10 chaos scenarios · 3 divers"
	@echo "  Surface: 1000 TPS · Subsurface: ZK proofs · L1: Valhalla Verifier"
	@echo "████████████████████████████████████████████████████████████████████████"
	@echo ""

# ── All Test Suites ──────────────────────────────────────────────────

test-all:
	@echo "🧪 Running all test suites..."
	@echo ""
	python3 scripts/test_simchain.py 2>&1 | grep "Results:"
	python3 scripts/test_multichain.py 2>&1 | grep "Results:"
	python3 scripts/check_claude_md.py 2>&1 | grep "Abweichungen"
	@echo ""
	@echo "✅ All test suites complete"
	@echo "✅ Alle Container, Images und Volumes entfernt"

.PHONY: son-report backup raas-smoke raas-portal

raas-smoke: ## RaaS prototype E2E (upload→stress→certificate, gate sim)
	PYTHONPATH=. python3 scripts/test_raas_smoke.py

raas-hybrid-shell: ## Core/Shell pilot (untrusted shell → TrustedCoreGateway)
	PYTHONPATH=. python3 scripts/test_raas_hybrid_shell.py

raas-supranode: ## Ingress/Egress facade over TrustedCoreGateway
	PYTHONPATH=. python3 scripts/test_raas_supranode.py

raas-d-suite: ## D1–D4 application barriers (DSuiteEnforcer)
	PYTHONPATH=. python3 scripts/test_d_suite_enforcer.py

raas-bus-topology-gate: ## Gate 0: NATS Queue-Group 1-of-N vs broadcast
	PYTHONPATH=. python3 scripts/test_topology_bus_queuegroups.py

raas-stage1-edge-pilot: ## Stage-1 pilot: single edge P1→P2 Queue-Group
	PYTHONPATH=. python3 scripts/test_stage1_edge_bus_pilot.py

raas-stage1-edge-ring: ## Stage-1 ring: P1→…→P9→P1 Queue-Group sequential
	PYTHONPATH=. python3 scripts/test_stage1_edge_bus_ring.py

raas-live-z3-latency: ## Live HTTP latency vs infra-z3 (:8001)
	PYTHONPATH=. python3 scripts/test_live_z3_latency.py

raas-mev-redteam: ## MEV/Latency Red-Team plugin (sandbox + D2)
	PYTHONPATH=. python3 scripts/test_mev_latency_redteam.py

raas-oracle-anomaly: ## Oracle Anomaly Swarm plugin (P5 sandbox + D2)
	PYTHONPATH=. python3 scripts/test_oracle_anomaly_swarm.py

raas-os-isolation: ## D2 OS-isolation intent for Sub-Swarm Dockerfiles
	PYTHONPATH=. python3 scripts/test_os_isolation_subswarms.py

raas-prefilter-datagen: ## Phase 4A synthetic prefilter feature matrix
	PYTHONPATH=. python3 scripts/test_prefilter_datagen.py

raas-prefilter-batch-extremes: ## Phase 4A scale extremes synth (n=5000, severity_proxy)
	PYTHONPATH=. python3 scripts/generate_prefilter_synthetic_data.py --profile extremes --n 5000 --label-mode severity_proxy --out data/synthetic/prefilter/extremes
	PYTHONPATH=. python3 scripts/check_prefilter_synth_quality.py data/synthetic/prefilter/extremes

raas-prefilter-train: ## Phase 4A GBT train + queue metric (severity_proxy only)
	PYTHONPATH=. python3 scripts/test_prefilter_training.py

raas-prefilter-queue-seed-spread: ## Queue metric mean/std over ≥6 train seeds (§4.2)
	PYTHONPATH=. python3 scripts/check_prefilter_queue_seed_spread.py

raas-public-ingest-sondierung: ## §4.3 Public-Ingest — distribution profiles only (no train labels)
	PYTHONPATH=. python3 scripts/ingest_public_distributions.py

raas-prefilter-calibrated-smoke: ## §4.3 generator+profiles smoke (n=5000)
	PYTHONPATH=. python3 scripts/generate_prefilter_synthetic_data.py --profile extremes --n 5000 --label-mode severity_proxy --out data/synthetic/prefilter/calibrated_smoke
	PYTHONPATH=. python3 scripts/check_prefilter_synth_quality.py data/synthetic/prefilter/calibrated_smoke

raas-prefilter-calibrated-batch: ## §4.3 calibrated extremes batch (n=20000)
	PYTHONPATH=. python3 scripts/generate_prefilter_synthetic_data.py --profile extremes --n 20000 --label-mode severity_proxy --out data/synthetic/prefilter/calibrated
	PYTHONPATH=. python3 scripts/check_prefilter_synth_quality.py data/synthetic/prefilter/calibrated

raas-prefilter-paired-compare: ## §4.3 paired queue Δ vs baseline seed-spread
	PYTHONPATH=. python3 scripts/compare_prefilter_queue_paired.py

raas-prefilter-reference-diagnosis: ## §4.3.1 R1 repro + R3 5k-subset-from-20k
	PYTHONPATH=. python3 scripts/diagnose_prefilter_reference.py

raas-prefilter-r5-train-vs-holdout: ## §4.3.1 R5 isolate train-n vs holdout-n
	PYTHONPATH=. python3 scripts/diagnose_prefilter_r5_train_vs_holdout.py

raas-prefilter-n-robust-metric: ## §4.3.1 N-robust queue metric (bootstrap n0=1000)
	PYTHONPATH=. python3 scripts/diagnose_prefilter_n_robust_metric.py

raas-prefilter-fixed-vs-random-holdout: ## §4.3.1 isolate composition (fixed vs random H=1000)
	PYTHONPATH=. python3 scripts/diagnose_prefilter_fixed_vs_random_holdout.py

raas-prefilter-multi-holdout-freeze: ## §4.3.1 A — draw+hash holdout sets BEFORE eval (git-tracked manifest)
	PYTHONPATH=. python3 scripts/freeze_prefilter_multi_holdout.py

raas-prefilter-multi-holdout-eval: ## §4.3.1 A — baseline mean±σ across frozen sets (never best)
	PYTHONPATH=. python3 scripts/eval_prefilter_multi_holdout.py

raas-prefilter-m1-isolation-screen: ## M1 Proto §3.3 — isolation vs M2 negative control
	PYTHONPATH=. python3 scripts/screen_prefilter_m1_isolation.py

raas-prefilter-m1-e2e: ## M1 Proto §3.4 — path · envelope · WORM
	PYTHONPATH=. python3 scripts/test_prefilter_m1_e2e.py

raas-b2b-exporter-smoke: ## B2B P9 gutachten JSON/PDF/Merkle (core untouched)
	PYTHONPATH=. python3 scripts/test_raas_b2b_exporter.py

raas-paper-trading-smoke: ## Paper setup — feed·ledger·WORM·envelope hit-rate (no order send)
	PYTHONPATH=. python3 scripts/test_raas_paper_trading.py

raas-paper-slippage-compare: ## P3 fixed vs dynamic slippage wiring screen (not empirical)
	PYTHONPATH=. python3 scripts/raas_paper_slippage_compare.py

raas-paper-slippage-replay: ## P3 WORM SIM_FILL replay — fixed-tuple A/B (diagnostic)
	PYTHONPATH=. python3 scripts/raas_paper_slippage_replay.py

raas-depth-ingest: ## Phase B — passive Binance depth → logs/worm/depth_snapshots.jsonl
	PYTHONPATH=. python3 scripts/raas_depth_ingest.py

raas-depth-ingest-dry: ## Depth fetch smoke (no WORM append)
	PYTHONPATH=. python3 scripts/raas_depth_ingest.py --dry-run

raas-paper-report: ## Paper WORM → exports/reports/paper_trades_latest.md (no sample fills)
	PYTHONPATH=. python3 services/exporter/agent_x_raas_exporter.py --mode paper_trading --format markdown

raas-paper-collect: ## Long paper loop — live depth at fill (no order send; default 24h)
	bash scripts/raas_paper_collect_start.sh

raas-paper-collect-smoke: ## Paper collect smoke — 2 ticks, live depth (network)
	PYTHONPATH=. python3 scripts/raas_paper_collect.py --depth-mode live --max-ticks 2 --duration-s 30

raas-regime-drift-monitor: ## Baustein 2 — 9-Agent KS/Wasserstein Schwarm on paper WORMs
	PYTHONPATH=. python3 scripts/raas_regime_drift_monitor.py

raas-regime-drift-smoke: ## Baustein 2 unit + 9-agent swarm smoke
	PYTHONPATH=. python3 scripts/test_raas_regime_drift.py

raas-live-feed-prometheus-smoke: ## Mock-WS → WORM → daemon Prometheus counters
	PYTHONPATH=. python3 scripts/test_live_feed_prometheus.py

raas-regime-swarm-build: ## Build regime swarm production image
	docker build -f Dockerfile.regime-swarm -t agentx-regime-swarm .

raas-regime-swarm-up: ## Start regime swarm daemon (compose, detached)
	docker compose -f docker-compose.regime-swarm.yml up -d regime-swarm

raas-regime-swarm-logs: ## Follow regime swarm container logs
	docker compose -f docker-compose.regime-swarm.yml logs -f regime-swarm

raas-regime-swarm-daemon: ## Run regime swarm daemon locally (foreground)
	mkdir -p logs/audit logs/state logs/reports logs/worm/paper_runs
	SWARM_DATA_ROOT=./logs PYTHONPATH=. python3 scripts/run_regime_swarm_daemon.py --config config/regime_swarm.json

raas-regime-swarm-helm-lint: ## Lint regime swarm Helm chart
	helm lint charts/regime-swarm

raas-regime-swarm-helm-template: ## Render regime swarm manifests (dry-run)
	helm template regime-swarm charts/regime-swarm -f charts/regime-swarm/values-dev.yaml

raas-regime-swarm-helm-install: ## Install/upgrade regime swarm in namespace trading
	helm upgrade --install regime-swarm charts/regime-swarm -n trading --create-namespace \
		-f charts/regime-swarm/values-dev.yaml

raas-regime-swarm-live-shadow-install: ## Helm install with live-feed shadow overlay (IMAGE_REPO/TAG optional)
	helm upgrade --install regime-swarm charts/regime-swarm -n trading --create-namespace \
		-f charts/regime-swarm/values-dev.yaml \
		-f charts/regime-swarm/values-live-shadow.yaml \
		--set image.repository=$${IMAGE_REPO:-agentx-regime-swarm} \
		--set image.tag=$${IMAGE_TAG:-live-shadow} \
		--set image.pullPolicy=IfNotPresent

raas-regime-leader-z3: ## P6 — Z3/BFS leader invariant proofs (I1)
	PYTHONPATH=. python3 scripts/test_regime_leader_z3.py

raas-regime-shadow-up: ## Shadow cluster (2 replicas, chaos drills)
	bash scripts/regime_swarm_shadow_cluster.sh up

raas-regime-shadow-chaos: ## Shadow chaos battery (C-01…C-04, T-S1a/T-S2a ordinal)
	PYTHONPATH=. python3 scripts/regime_swarm_shadow_chaos.py

raas-regime-lease-t-s1a: ## T-S1a K8s Lease split-brain (requires kind-regime-shadow)
	PYTHONPATH=. python3 scripts/regime_swarm_lease_t_s1a.py

raas-regime-lease-t-s2b: ## T-S2b K8s Lease silent hang / renewal timeout
	PYTHONPATH=. python3 scripts/regime_swarm_lease_t_s2b.py

raas-regime-swarm-ha-smoke: ## HA leader ordinal + lease fallback smoke
	PYTHONPATH=. python3 scripts/test_regime_swarm_ha.py

raas-regime-swarm-infra-gates: ## A0/A2.5 infrastructure gate smoke (INFRASTRUCTURE_GATES_PASS/FAIL)
	PYTHONPATH=. python3 scripts/test_infrastructure_gates.py

raas-regime-swarm-infra-smoke: ## E2E WORM→A0/A2.5 smoke + audit JSON (REGIME_SWARM_INFRA_SMOKE_PASS/FAIL)
	PYTHONPATH=. python3 scripts/run_regime_swarm_infra_smoke.py

raas-regime-swarm-helm-pod-smoke: ## Pod-style smoke (ConfigMap env + threshold test)
	PYTHONPATH=. python3 scripts/helm_pod_smoke.py

raas-regime-swarm-helm-test: ## helm test infra smoke Job (cluster; smokeTest.enabled=true)
	helm test regime-swarm -n trading --timeout 5m

raas-regime-swarm-cluster-smoke: ## Full cluster runbook: baseline G0=20 + override G0=10 (needs cluster)
	chmod +x scripts/run_regime_swarm_cluster_smoke.sh
	./scripts/run_regime_swarm_cluster_smoke.sh full

raas-regime-lease-failover-forensic: ## Drill 2 lease timeline (kind shadow, post-release fix)
	PYTHONPATH=. python3 scripts/regime_swarm_lease_failover_forensic.py

raas-chaos-g1-harness: ## G1 chaos matrix offline harness (gate_core, 9 fixtures)
	PYTHONPATH=. python3 scripts/chaos_engineering_g1_harness.py

raas-chaos-g2-harness: ## G2 chaos matrix HTTP harness (fail-closed-gate /v1/evaluate)
	PYTHONPATH=. python3 scripts/chaos_engineering_g2_harness.py

raas-flash-crash-retro: ## Option 5 — Z3-Gate risk layer vs historical klines (MAP v0)
	PYTHONPATH=. python3 scripts/raas_flash_crash_retrospective.py --days 14

raas-flash-crash-retro-180: ## Option 5 full window (needs network for missing cache days)
	PYTHONPATH=. python3 scripts/raas_flash_crash_retrospective.py --days 180

raas-fn-belt-screen: ## FN-Gürtel Ursachen A–D (same definition_hash, no retune)
	PYTHONPATH=. python3 scripts/raas_fn_belt_screen.py --days 180

raas-barrier-cal-surface: ## P1 counterfactual FP/FN surface (labels only, prod edges frozen)
	PYTHONPATH=. python3 scripts/raas_barrier_cal_surface.py --days 180

raas-daily-paper-report: ## Cron entry: paper WORM → markdown (logs/cron_exporter.log)
	bash scripts/raas_daily_paper_report.sh

raas-notify-gate-blocks: ## Dry-run notify bridge (risk BLOCK only; --send to post)
	PYTHONPATH=. python3 scripts/raas_notify_gate_blocks.py

raas-gateway-prefilter-cutover: ## Phase 4A backlog priority cutover (no core skip)
	PYTHONPATH=. python3 scripts/test_gateway_prefilter_cutover.py

raas-portal: ## Start RaaS portal on :8020
	PYTHONPATH=. uvicorn services.raas_portal.main:app --host 0.0.0.0 --port 8020

raas-up: ## Compose: raas-portal + gate + redis (kein Z3/:8001)
	docker compose -f podman-compose.p9.yml up --build raas-portal

son-report: ## Regenerate SON report (24h validity for compliance gate)
	python3 scripts/check_claude_md.py --run-tests --json-report archive_b2g/son_report.json

backup: ## Nightly backup (compose + env + Neo4j dump + retention)
	bash scripts/backup_agent_x.sh
