"""
Cloud policy — single explicit switch for sending prompts to a cloud LLM.

Every code path that can call a cloud model (ModelRouter fallback, LLM_PROVIDER=cloud)
must check `cloud_allowed()`. It is False unless the process environment sets
AIFORGE_ALLOW_CLOUD=1, so a config file edit alone can never send data off the machine.
"""

from __future__ import annotations

import os

CLOUD_ENV_VAR = "AIFORGE_ALLOW_CLOUD"


class CloudDisabledError(RuntimeError):
    """Raised when a cloud model is requested but the cloud switch is off."""


def cloud_allowed() -> bool:
    return os.environ.get(CLOUD_ENV_VAR, "").strip() == "1"


def require_cloud_allowed(purpose: str) -> None:
    if not cloud_allowed():
        raise CloudDisabledError(
            f"Cloud LLM blocked ({purpose}): set {CLOUD_ENV_VAR}=1 to allow prompts to leave this machine."
        )
