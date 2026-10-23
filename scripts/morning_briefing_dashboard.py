"""Morning Briefing Dashboard — Servidor web local (localhost:8765) que renderiza el briefing diario de forma interactiva y visual."""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from agents.logger import get_logger
from agents.obsidian_tools import get_vault_path
from scripts.morning_briefing import run_briefing_flow

app = FastAPI(title="AI-Forge Morning Briefing Dashboard")
log = get_logger("briefing_dashboard")

# ══════════════════════════════════════════════════════════════════════════════
# DATA PARSERS & HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_briefing_content() -> str:
    """Lee el briefing de hoy en Obsidian."""
    today = date.today().isoformat()
    try:
        vault = get_vault_path()
        path = vault / "Daily Notes" / f"{today}-briefing.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
    except (ValueError, OSError):  # vault no configurado o error de lectura
        log.warning("No se pudo leer el briefing de hoy", exc_info=True)
    return ""

def read_daily_tasks() -> List[Dict[str, Any]]:
    """Lee las tareas (pendientes y completadas) de la Daily Note de hoy en Obsidian."""
    today = date.today().isoformat()
    tasks = []
    try:
        vault = get_vault_path()
        path = vault / "Daily Notes" / f"{today}.md"
        if not path.exists():
            return []
        
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line_str = line.strip()
            if line_str.startswith("- [ ]") or line_str.startswith("- [x]"):
                completed = line_str.startswith("- [x]")
                text = line_str[5:].strip()
                if text:
                    tasks.append({
                        "text": text,
                        "completed": completed,
                        "raw_line": line
                    })
    except (ValueError, OSError):
        log.warning("No se pudo leer la Daily Note de hoy", exc_info=True)
    return tasks

def write_daily_tasks(tasks: List[Dict[str, Any]]) -> bool:
    """Escribe de vuelta el bloque de tareas en la Daily Note de hoy."""
    today = date.today().isoformat()
    try:
        vault = get_vault_path()
        path = vault / "Daily Notes" / f"{today}.md"
        if not path.exists():
            return False
            
        lines = path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        task_idx = 0
        
        for line in lines:
            if line.strip().startswith("- [ ]") or line.strip().startswith("- [x]"):
                if task_idx < len(tasks):
                    t = tasks[task_idx]
                    prefix = "- [x]" if t["completed"] else "- [ ]"
                    # Preservar indentación original
                    indent = line[:line.find("-")]
                    new_lines.append(f"{indent}{prefix} {t['text']}")
                    task_idx += 1
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
                
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except (ValueError, OSError):
        log.error("No se pudo escribir la Daily Note de hoy", exc_info=True)
        return False

# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

class TaskToggleIn(BaseModel):
    task_text: str
    completed: bool

@app.get("/api/briefing")
async def get_briefing():
    """Retorna el contenido crudo del briefing de hoy en markdown y las tareas estructuradas."""
    briefing = get_briefing_content()
    tasks = read_daily_tasks()
    return {
        "date": date.today().isoformat(),
        "has_briefing": bool(briefing),
        "markdown": briefing,
        "tasks": tasks
    }

@app.post("/api/generate")
async def generate_briefing():
    """Genera (o regenera) el briefing diario en segundo plano."""
    try:
        # Ejecuta el script de orquestación principal
        briefing = await asyncio.to_thread(run_briefing_flow)
        tasks = read_daily_tasks()
        return {"status": "ok", "markdown": briefing, "tasks": tasks}
    except Exception as e:  # frontera HTTP: cualquier fallo del pipeline -> 500 con traza en logs
        log.exception("Generación del briefing falló")
        raise HTTPException(status_code=500, detail=str(e)) from e

@app.post("/api/tasks/toggle")
async def toggle_task(body: TaskToggleIn):
    """Marca o desmarca una tarea en el archivo .md de Obsidian de hoy."""
    tasks = read_daily_tasks()
    found = False
    for t in tasks:
        if t["text"].strip() == body.task_text.strip():
            t["completed"] = body.completed
            found = True
            break
            
    if not found:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
    success = write_daily_tasks(tasks)
    if not success:
        raise HTTPException(status_code=500, detail="Error al actualizar el archivo Markdown")
        
    return {"status": "ok", "tasks": tasks}

# Panel HTML en archivo aparte (antes ~320 líneas de string dentro de este módulo)
_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "morning_briefing.html"


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return _TEMPLATE_PATH.read_text(encoding="utf-8")

def main():
    print("🚀 Levantando Dashboard del Morning Briefing en http://localhost:8765...")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")

if __name__ == "__main__":
    main()
