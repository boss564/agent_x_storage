"""Control-plane test defaults.

Sets CONTROL_PLANE_TEST_MODE so gatectl's L1 Drive-Boundary deny of the
production audit folder id applies to in-process and subprocess tests that
inherit the environment. Live CLI without this env remains unaffected.

L4-C3: ``CONTROL_PLANE_ROLE=operator`` here is **test-only**. The runtime
(``control_plane_authz.resolve_role`` / gatectl) has **no** Operator fallback —
missing role ⇒ Deny. Production must set an explicit role per process
(see L5 Runbook). Do not copy this fixture into launchd / prod env templates.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _control_plane_test_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTROL_PLANE_TEST_MODE", "1")
    # L4 suite: Authz always on; role injected only for tests (not a runtime default).
    monkeypatch.setenv("CONTROL_PLANE_AUTHZ_ENFORCE", "1")
    monkeypatch.setenv("CONTROL_PLANE_ROLE", "operator")
