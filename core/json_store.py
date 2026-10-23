"""Safe JSON persistence shared by TaskForge and the lead scraper.

- load_json / load_json_list: a corrupt file is renamed to <name>.corrupt-<timestamp> before
  returning [], so the next save never silently replaces the user's data.
- save_json_atomic: write to a temp file and os.replace(), so a crash mid-write
  leaves the previous version intact.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("ai_forge.json_store")


def load_json(path: Path, default: Any) -> Any:
    """Read JSON; on a corrupt file, back it up and return `default` (never silently lose data)."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_name(f"{path.name}.corrupt-{datetime.now():%Y%m%d%H%M%S}")
        path.replace(backup)
        log.error("JSON corrupto en %s; respaldado en %s", path.name, backup.name, exc_info=True)
        return default
    except OSError:
        log.error("No se pudo leer %s", path.name, exc_info=True)
        return default


def load_json_list(path: Path) -> list:
    data = load_json(path, [])
    return data if isinstance(data, list) else []


def save_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
