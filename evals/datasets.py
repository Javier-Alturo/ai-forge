"""Load eval datasets: generic ones in evals/datasets/ (committed) and, optionally,
the user's real ones in evals/private/ (git-ignored). Same file names in both."""

from __future__ import annotations

import json
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
GENERIC_DIR = EVALS_DIR / "datasets"
PRIVATE_DIR = EVALS_DIR / "private"
RESULTS_DIR = EVALS_DIR / "results"
PRIVATE_RESULTS_DIR = PRIVATE_DIR / "results"


def read_jsonl(path: Path) -> list[dict]:
    items = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path.name}:{n}: invalid JSON line") from e
    return items


def load(name: str, include_private: bool = False, private_only: bool = False) -> list[dict]:
    """Items from <name>.jsonl, each tagged with "source": "generic" | "private"."""
    sources = []
    if not private_only:
        sources.append(("generic", GENERIC_DIR / f"{name}.jsonl"))
    if include_private or private_only:
        sources.append(("private", PRIVATE_DIR / f"{name}.jsonl"))
    items = []
    for source, path in sources:
        if path.exists():
            items += [{**item, "source": source} for item in read_jsonl(path)]
    return items


def results_dir(uses_private: bool) -> Path:
    """Results that include private data are written only under evals/private/."""
    return PRIVATE_RESULTS_DIR if uses_private else RESULTS_DIR
