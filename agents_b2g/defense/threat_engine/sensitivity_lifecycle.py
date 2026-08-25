"""SENSITIVITY_RAISED / CLEARED pairing — no silent open raises."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


class _ActionRecorder(Protocol):
    def record_action(self, **kwargs) -> dict: ...


@dataclass
class OpenSensitivity:
    signature_id: int
    eoa_pseudonym: str
    raised_incident_id: int
    kfold_sensitivity: Optional[float] = None


@dataclass
class SensitivityLifecycle:
    """Every RAISED must get exactly one CLEARED (orchestrator-owned)."""

    store: _ActionRecorder
    observed_by_user_id: Optional[str] = None
    _open: dict[int, OpenSensitivity] = field(default_factory=dict)

    def raise_sensitivity(
        self,
        *,
        signature_id: int,
        eoa_pseudonym: str,
        kfold_sensitivity: float = 2.0,
        notes: Optional[str] = None,
    ) -> dict:
        if signature_id in self._open:
            raise RuntimeError(
                f"SENSITIVITY_RAISED already open for signature_id={signature_id}"
            )
        result = self.store.record_action(
            signature_id=signature_id,
            eoa_pseudonym=eoa_pseudonym,
            action_type="SENSITIVITY_RAISED",
            kfold_sensitivity=kfold_sensitivity,
            notes=notes or "lifecycle:raise",
            observed_by_user_id=self.observed_by_user_id,
        )
        if result.get("status") != "completed":
            return result
        incident_id = int(result["artifacts"][0]["incident_id"])
        self._open[signature_id] = OpenSensitivity(
            signature_id=signature_id,
            eoa_pseudonym=eoa_pseudonym,
            raised_incident_id=incident_id,
            kfold_sensitivity=kfold_sensitivity,
        )
        return result

    def clear_sensitivity(
        self,
        *,
        signature_id: int,
        notes: Optional[str] = None,
    ) -> dict:
        open_ = self._open.get(signature_id)
        if open_ is None:
            raise RuntimeError(
                f"no open SENSITIVITY_RAISED for signature_id={signature_id}"
            )
        result = self.store.record_action(
            signature_id=signature_id,
            eoa_pseudonym=open_.eoa_pseudonym,
            action_type="SENSITIVITY_CLEARED",
            kfold_sensitivity=1.0,
            notes=notes or f"lifecycle:clear raised={open_.raised_incident_id}",
            observed_by_user_id=self.observed_by_user_id,
        )
        if result.get("status") == "completed":
            del self._open[signature_id]
        return result

    def open_raises(self) -> list[OpenSensitivity]:
        return list(self._open.values())

    def assert_all_cleared(self) -> None:
        if self._open:
            ids = sorted(self._open)
            raise AssertionError(
                f"open SENSITIVITY_RAISED without CLEARED: signature_ids={ids}"
            )
