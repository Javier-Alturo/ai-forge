"""Cloud LLM calls are blocked unless AIFORGE_ALLOW_CLOUD=1 is set explicitly."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cloud_policy import (  # noqa: E402
    CLOUD_ENV_VAR,
    CloudDisabledError,
    cloud_allowed,
)
from core.model_router import ModelRouter  # noqa: E402

CLOUD_CFG = {"local_model": "m", "allow_cloud_fallback": True, "cloud_model": "c", "cb_failure_threshold": 1}


@pytest.mark.parametrize("value", [None, "", "0", "true", "yes", " 2 "])
def test_cloud_off_unless_exactly_one(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(CLOUD_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(CLOUD_ENV_VAR, value)
    assert cloud_allowed() is False


def test_config_flag_alone_does_not_enable_cloud(monkeypatch):
    monkeypatch.delenv(CLOUD_ENV_VAR, raising=False)
    router = ModelRouter(CLOUD_CFG)
    assert router.allow_cloud is False
    router.report_failure()  # opens the circuit breaker
    with pytest.raises(RuntimeError, match=CLOUD_ENV_VAR):
        router.get_model()


def test_env_and_config_together_enable_cloud(monkeypatch):
    monkeypatch.setenv(CLOUD_ENV_VAR, "1")
    router = ModelRouter(CLOUD_CFG)
    assert router.allow_cloud is True


def test_env_alone_does_not_enable_router_cloud(monkeypatch):
    monkeypatch.setenv(CLOUD_ENV_VAR, "1")
    assert ModelRouter({"local_model": "m"}).allow_cloud is False


def test_cloud_model_factory_double_checks(monkeypatch):
    monkeypatch.setenv(CLOUD_ENV_VAR, "1")
    router = ModelRouter(CLOUD_CFG)
    monkeypatch.delenv(CLOUD_ENV_VAR)  # switch turned off after construction
    with pytest.raises(CloudDisabledError):
        router._get_cloud_model()


def test_llm_provider_cloud_blocked_without_switch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cloud")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    monkeypatch.delenv(CLOUD_ENV_VAR, raising=False)
    from agents import llm

    llm = importlib.reload(llm)
    try:
        with pytest.raises(CloudDisabledError):
            llm.get_llm()
    finally:
        monkeypatch.setenv("LLM_PROVIDER", "local")
        importlib.reload(llm)
