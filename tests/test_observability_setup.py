"""LangFuse local setup: strong random secrets, never overwrite, compose has no weak defaults."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "observability"))

import setup_env  # noqa: E402

COMPOSE = (ROOT / "observability" / "docker-compose.yml").read_text(encoding="utf-8")


def test_generated_secrets_are_random_and_long():
    a, b = setup_env.generate(), setup_env.generate()
    assert a["POSTGRES_PASSWORD"] != b["POSTGRES_PASSWORD"]
    assert re.fullmatch(r"[0-9a-f]{64}", a["ENCRYPTION_KEY"])
    assert a["LANGFUSE_PUBLIC_KEY"].startswith("pk-lf-") and a["LANGFUSE_SECRET_KEY"].startswith("sk-lf-")


def test_compose_env_is_never_overwritten(tmp_path):
    path = tmp_path / ".env"
    values, created = setup_env.write_compose_env(path)
    assert created and path.exists()
    again, created_again = setup_env.write_compose_env(path)
    assert not created_again and again == values


def test_app_env_only_appends_missing_keys(tmp_path):
    app_env = tmp_path / ".env"
    app_env.write_text("OLLAMA_MODEL=x\nLANGFUSE_HOST=http://localhost:3000\n", encoding="utf-8")
    lines = setup_env.app_env_lines(setup_env.generate())
    added = setup_env.add_to_app_env(lines, app_env)
    assert {ln.split("=")[0] for ln in added} == {"LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"}
    assert setup_env.add_to_app_env(lines, app_env) == []
    assert "OLLAMA_MODEL=x" in app_env.read_text(encoding="utf-8")


def test_compose_publishes_only_on_localhost():
    published = re.findall(r'^\s*-\s*"?([\d.:]+:\d+)"?', COMPOSE, flags=re.M)
    assert published, "expected some published ports"
    assert all(p.startswith("127.0.0.1:") for p in published)


def test_compose_has_no_default_passwords():
    assert "postgres:postgres@" not in COMPOSE
    assert "miniosecret" not in COMPOSE and "myredissecret" not in COMPOSE
    assert 'TELEMETRY_ENABLED: "false"' in COMPOSE
    assert 'AUTH_DISABLE_SIGNUP: "true"' in COMPOSE
