# tests/test_hsm_adapter.py
"""HSM Adapter Tests — SoftHSM2 Mock Mode."""
import os, sys, pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents_b2g.bunker.hsm_adapter import UnifiedPKCS11HSM

@pytest.fixture
def hsm():
    os.environ["HSM_MODE"] = "SOFTHSM"
    os.environ["HSM_PIN"] = "1234"
    return UnifiedPKCS11HSM()

def test_hsm_initialization(hsm):
    assert hsm.mode == "SOFTHSM"
    assert hsm._session is not None

def test_hsm_signature_length(hsm):
    sig = hsm.sign_transaction_hash(b"Test-Transaktion-2026")
    assert len(sig) == 64  # SHA-256 hex
    assert isinstance(sig, str)

def test_hsm_deterministic_signature(hsm):
    """Gleicher Input → gleiche Signatur (Mock-Mode)."""
    sig1 = hsm.sign_transaction_hash(b"test")
    sig2 = hsm.sign_transaction_hash(b"test")
    assert sig1 == sig2

def test_hsm_different_inputs_different_signatures(hsm):
    sig1 = hsm.sign_transaction_hash(b"input-1")
    sig2 = hsm.sign_transaction_hash(b"input-2")
    assert sig1 != sig2

def test_hsm_public_key_format(hsm):
    pk = hsm.get_public_key()
    assert pk.startswith("0x")
    assert len(pk) == 42

def test_hsm_health_check(hsm):
    assert hsm.is_healthy() is True
