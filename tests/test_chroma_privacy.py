"""ChromaDB must not send anonymous usage telemetry off the machine."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

chromadb = pytest.importorskip("chromadb")

from agents import chroma_client  # noqa: E402


def test_telemetry_env_default_is_off():
    assert os.environ.get("ANONYMIZED_TELEMETRY", "").lower() == "false"


def test_singleton_client_has_telemetry_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(chroma_client, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(chroma_client, "_client", None)
    client = chroma_client.get_chroma_client()
    assert client.get_settings().anonymized_telemetry is False
