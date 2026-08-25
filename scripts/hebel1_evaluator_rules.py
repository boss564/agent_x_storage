"""Hebel 1 Follow-up: differentiated evaluation rules for the nine evaluators.

All rules operate on the SAME offer fields (contract_id, net, tax, ret, gross,
inflated). They are name-analogous checks, NOT live compliance-module calls
(that would be Strategy 2). Each rule returns a boolean verdict.

DESIGN CONSTRAINT (prereg): no rule may be always-PASS on the measurement
dataset. Dead rules (always-PASS) are detected by the measurement harness.
"""

from __future__ import annotations

from typing import Callable, Dict

# --- Frozen thresholds (per prereg, do not tune after data look) ---
BALANCE_TOL = 0.01              # standard balance tolerance
STRICT_TOL = 1e-9               # E01: strict zero-sum (no tolerance)
TAX_RATE_MAX_COMPLIANCE = 0.30  # E04: broad tax-rate bound
TAX_RATE_MAX_AUDITOR = 0.20     # E09: strict tax-rate bound
RETENTION_RATE_MAX = 0.10       # E05: retention-rate bound (VOB/B analog)
AMOUNT_SANITY_MAX = 1e7         # E07: absolute amount sanity bound
MIN_CONTRACT_ID_LEN = 4         # E06: contract_id minimum length


def _delta(net, tax, ret, gross):
    """Arithmetic balance: gross - (net + tax + ret)."""
    return round(gross - (net + tax + ret), 10)


def rule_bho_zero_sum(net, tax, ret, gross, inflated, contract_id):
    """E01-bho-checker: strict BHO zero-sum (no tolerance)."""
    return abs(_delta(net, tax, ret, gross)) < STRICT_TOL


def rule_z3_invariants(net, tax, ret, gross, inflated, contract_id):
    """E02-z3-prover: non-negativity of all amounts + balance."""
    return (net >= 0 and tax >= 0 and ret >= 0 and gross >= 0
            and abs(_delta(net, tax, ret, gross)) <= BALANCE_TOL)


def rule_gobd_completeness(net, tax, ret, gross, inflated, contract_id):
    """E03-gobd-auditor: strict positivity of main amounts + balance."""
    return (net > 0 and gross > 0 and tax >= 0
            and abs(_delta(net, tax, ret, gross)) <= BALANCE_TOL)


def rule_compliance_tax_rate(net, tax, ret, gross, inflated, contract_id):
    """E04-compliance: broad tax-rate plausibility (0-30%)."""
    if abs(_delta(net, tax, ret, gross)) > BALANCE_TOL:
        return False
    if net <= 0:
        return False
    return 0 <= (tax / net) <= TAX_RATE_MAX_COMPLIANCE


def rule_iot_retention(net, tax, ret, gross, inflated, contract_id):
    """E05-iot-verifier: retention-rate bound (VOB/B analog, <=10%)."""
    if abs(_delta(net, tax, ret, gross)) > BALANCE_TOL:
        return False
    if gross <= 0:
        return False
    return (ret / gross) <= RETENTION_RATE_MAX


def rule_qes_format(net, tax, ret, gross, inflated, contract_id):
    """E06-qes-validator: contract_id presence/format + balance."""
    if abs(_delta(net, tax, ret, gross)) > BALANCE_TOL:
        return False
    cid = str(contract_id) if contract_id is not None else ""
    if len(cid) < MIN_CONTRACT_ID_LEN:
        return False
    return True


def rule_geofence_bounds(net, tax, ret, gross, inflated, contract_id):
    """E07-geofence: absolute amount sanity bound + balance."""
    if abs(_delta(net, tax, ret, gross)) > BALANCE_TOL:
        return False
    return 0 < net < AMOUNT_SANITY_MAX


def rule_fraud_inflated(net, tax, ret, gross, inflated, contract_id):
    """E08-fraud-detector: reject inflated invoices + balance."""
    if abs(_delta(net, tax, ret, gross)) > BALANCE_TOL:
        return False
    return not inflated


def rule_tax_auditor(net, tax, ret, gross, inflated, contract_id):
    """E09-tax-auditor: strict tax-rate bound (0-20%, stricter than E04)."""
    if abs(_delta(net, tax, ret, gross)) > BALANCE_TOL:
        return False
    if net <= 0:
        return False
    return 0 <= (tax / net) <= TAX_RATE_MAX_AUDITOR


def rule_default(net, tax, ret, gross, inflated, contract_id):
    """Original rule (kept for reference/fallback): abs(delta) <= 0.01."""
    return abs(_delta(net, tax, ret, gross)) <= BALANCE_TOL


# Registry: evaluator_id -> rule
EVALUATOR_RULES: Dict[str, Callable] = {
    "E01-bho-checker": rule_bho_zero_sum,
    "E02-z3-prover": rule_z3_invariants,
    "E03-gobd-auditor": rule_gobd_completeness,
    "E04-compliance": rule_compliance_tax_rate,
    "E05-iot-verifier": rule_iot_retention,
    "E06-qes-validator": rule_qes_format,
    "E07-geofence": rule_geofence_bounds,
    "E08-fraud-detector": rule_fraud_inflated,
    "E09-tax-auditor": rule_tax_auditor,
}
