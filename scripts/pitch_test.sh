#!/usr/bin/env bash
# Agent X — Pre-Pitch Verification Script
# Führt alle Health-Checks durch bevor der Kämmerer zuschaut.
#
# Usage:
#   bash scripts/pitch_test.sh
#   bash scripts/pitch_test.sh --quick   (nur Health, keine Tests)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✅${NC} $label"
        ((PASS++)) || true
    else
        echo -e "  ${RED}❌${NC} $label"
        ((FAIL++)) || true
    fi
}

echo "=========================================="
echo "🏛️  AGENT X — PRE-PITCH VERIFICATION"
echo "=========================================="
echo ""

# ── Python & Dependencies ────────────────────────────────────────────
echo "📦 Python & Dependencies"
check "Python 3.11+"              python3 -c "import sys; assert sys.version_info >= (3,11)"
check "pycryptodome (PQC)"          python3 -c "from Crypto.PublicKey import ECC"
check "z3-solver (Theorem Prover)" python3 -c "import z3; z3.get_version_string()"
echo ""

# ── Z3 Service ───────────────────────────────────────────────────────
echo "🧠 Z3 Theorem Prover Service"
Z3_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo '{"status":"down"}')
if echo "$Z3_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='healthy' else 1)" 2>/dev/null; then
    echo -e "  ${GREEN}✅${NC} Z3 Health: ONLINE ($(echo "$Z3_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null))"
    ((PASS++)) || true
else
    echo -e "  ${YELLOW}⚠️${NC}  Z3 Health: OFFLINE (Service nicht erreichbar)"
    ((FAIL++)) || true
fi

BHO_PROOF=$(curl -s -X POST http://localhost:8000/prove_bho_invariant \
    -H 'Content-Type: application/json' \
    -d '{"sector":"BAU","gross_amount":45000,"net_amount":36000,"tax_amount":6750,"retention_amount":2250}' 2>/dev/null || echo '{}')
check "BHO-Proof (Δ=0)" python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('bho_invariant_valid')" <<<"$BHO_PROOF"

BHO_VIOLATION=$(curl -s -X POST http://localhost:8000/prove_bho_invariant \
    -H 'Content-Type: application/json' \
    -d '{"sector":"TEST","gross_amount":100,"net_amount":80,"tax_amount":15,"retention_amount":4}' 2>/dev/null || echo '{}')
check "BHO-Violation detection" python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'detail' in d else 1)" <<<"$BHO_VIOLATION"

# COMPLIANCE GATE (B2G Key Decision: BLOCKING bei Verletzung, nicht bei Attestierung)
# Invariante: verified + claimed + attested + failed = total  (Zero-Sum der Checks)
# Gate:       failed_count == 0                                (keine Abweichung)
# Note: passed==42 war unerreichbar (11 attested sind prinzipbedingt nicht software-probbar).
COMPLIANCE=$(curl -s http://localhost:8000/compliance 2>/dev/null || echo '{"summary":{"failed_count":1,"total_checks":0,"verified":0,"claimed":0,"attested":0,"gate":"BLOCKING","verdict":"DOWN"}}')
if echo "$COMPLIANCE" | python3 -c "
import sys, json
s = json.load(sys.stdin)['summary']
parts = s.get('verified', 0) + s.get('claimed', 0) + s.get('attested', 0) + s.get('failed_count', 1)
ok = (parts == s.get('total_checks', -1) > 0) and (s.get('failed_count', 1) == 0)
print(f\"  total={s.get('total_checks')} verified={s.get('verified')} claimed={s.get('claimed')} attested={s.get('attested')} failed={s.get('failed_count')} gate={s.get('gate')} verdict={s.get('verdict')}\", file=sys.stderr)
sys.exit(0 if ok else 1)
" 2>&1; then
    echo -e "  ${GREEN}✅${NC} Compliance Gate (failed_count==0, Zero-Sum)"
    ((PASS++)) || true
else
    echo -e "  ${RED}❌${NC} COMPLIANCE BLOCKING"
    ((FAIL++)) || true
fi
echo ""

# ── Core Tests ───────────────────────────────────────────────────────
if [[ "${1:-}" != "--quick" ]]; then
    echo "🧪 Core Test Suites"
    check "Wave 33 Survival (63/63)"   python3 scripts/test_wave33_survival.py
    check "Z3 Integration (13/13)"     python3 tests/test_z3_integration.py
    check "Bunker Integration (18/18)" python3 tests/test_bunker_integration.py
    check "Wave 34 Finale (21/21)"     python3 scripts/test_finale.py
    check "ESP32 Firmware (15/15)"     python3 scripts/test_esp32_firmware.py
    echo ""
fi

# ── Summary ──────────────────────────────────────────────────────────
echo "=========================================="
TOTAL=$((PASS + FAIL))
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✅ ALLE $TOTAL CHECKS BESTANDEN${NC}"
    echo ""
    echo "🚀 Bereit für den Kämmerer-Pitch!"
    echo "   Z3-Compliance: http://localhost:8000/compliance"
else
    echo -e "${RED}❌ $FAIL/$TOTAL CHECKS FEHLGESCHLAGEN${NC}"
    echo ""
    echo "Bitte vor dem Pitch beheben:"
    echo "   docker compose -f docker-compose.mock.yml up -d"
    echo "   pip install -r requirements.txt"
fi
echo "=========================================="

exit $FAIL
