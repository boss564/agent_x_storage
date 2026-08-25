"""EOA pseudonymization — SHA-256(lower(address)); raw vault is tenant-scoped."""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from agents_b2g.defense.threat_engine.session import ThreatEngineSession

_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def eoa_pseudonym(address: str) -> str:
    addr = (address or "").strip()
    if not _ADDR_RE.match(addr):
        raise ValueError(f"invalid EOA address: {address!r}")
    return hashlib.sha256(addr.lower().encode("utf-8")).hexdigest()


def put_raw_vault(
    session: ThreatEngineSession,
    *,
    tenant_user_id: str,
    address: str,
) -> str:
    """Store raw address under tenant isolation. Returns pseudonym."""
    if not tenant_user_id:
        raise ValueError("tenant_user_id required for raw vault")
    pseudo = eoa_pseudonym(address)
    session.execute(
        """
        INSERT INTO wave28_eoa_raw_vault (tenant_user_id, eoa_pseudonym, eoa_address_raw)
        VALUES (%s, %s, %s)
        ON CONFLICT (tenant_user_id, eoa_pseudonym) DO UPDATE
          SET eoa_address_raw = EXCLUDED.eoa_address_raw
        """,
        (tenant_user_id, pseudo, address.strip()),
    )
    return pseudo


def resolve_raw(
    session: ThreatEngineSession,
    *,
    tenant_user_id: str,
    pseudonym: str,
) -> Optional[str]:
    """Resolve raw address for one tenant only (incident response)."""
    session.execute(
        """
        SELECT eoa_address_raw FROM wave28_eoa_raw_vault
         WHERE tenant_user_id = %s AND eoa_pseudonym = %s
        """,
        (tenant_user_id, pseudonym.lower()),
    )
    row = session.cursor.fetchone()
    return row[0] if row else None
