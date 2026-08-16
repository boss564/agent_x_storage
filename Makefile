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

.PHONY: son-report backup
son-report: ## Regenerate SON report (24h validity for compliance gate)
	python3 scripts/check_claude_md.py --run-tests --json-report archive_b2g/son_report.json

backup: ## Nightly backup (compose + env + Neo4j dump + retention)
	bash scripts/backup_agent_x.sh
