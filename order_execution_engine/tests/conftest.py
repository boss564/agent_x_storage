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
