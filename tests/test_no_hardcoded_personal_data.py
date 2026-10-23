"""Source code must not hardcode phone numbers or absolute user paths; they belong in .env."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DIRS = ("knowledge/", "pruebas/", "data/", "tests/")
CODE_SUFFIXES = {".py", ".bat", ".ps1", ".sh", ".json", ".yml", ".yaml", ".toml"}

PATTERNS = {
    "phone number": re.compile(r"(?<![\d.])(?:\+?57)?3\d{9}(?!\d)"),
    "absolute user path": re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!<)[^\\/\s\"']+", re.IGNORECASE),
}


def _tracked_code_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    files = [ROOT / f for f in out.splitlines() if not f.startswith(EXCLUDED_DIRS)]
    return [f for f in files if f.suffix in CODE_SUFFIXES and f.is_file()]


def test_no_hardcoded_phones_or_user_paths():
    findings = []
    for path in _tracked_code_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {label}")
    assert not findings, "Move these to .env:\n" + "\n".join(findings)
