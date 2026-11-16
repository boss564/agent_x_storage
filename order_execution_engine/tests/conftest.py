"""Control-plane test defaults.

Sets CONTROL_PLANE_TEST_MODE so gatectl's L1 Drive-Boundary deny of the
production audit folder id applies to in-process and subprocess tests that
inherit the environment. Live CLI without this env remains unaffected.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _control_plane_test_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTROL_PLANE_TEST_MODE", "1")
    # L4: suite runs with Authz enforce + operator (least-surprise for
    # existing cmds). Deny/unknown-role cases override per-test.
    monkeypatch.setenv("CONTROL_PLANE_AUTHZ_ENFORCE", "1")
    monkeypatch.setenv("CONTROL_PLANE_ROLE", "operator")
