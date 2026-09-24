"""
Dashboard web AI-Forge: FastAPI + WebSockets + chat orquestador.

Ejecutar desde la raíz del repo:
  python dashboard/app.py
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent

log_ws_clients: list[WebSocket] = []


async def _broadcast_logs_worker() -> None:
    from agents.log_broadcast import get_log_queue

    q = get_log_queue()
    while True:
        line = await asyncio.to_thread(q.get)
        dead: list[WebSocket] = []
        for ws in list(log_ws_clients):
            try:
                await ws.send_text(line)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            if ws in log_ws_clients:
                log_ws_clients.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_broadcast_logs_worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="AI-Forge Dashboard", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1)


def _gpu_summary() -> str:
    """Línea corta de uso GPU vía nvidia-smi (sin dependencias extra)."""
    if not shutil.which("nvidia-smi"):
        return "GPU: no detectada (sin nvidia-smi o no NVIDIA)"
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return "GPU: nvidia-smi no disponible"
        first = proc.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in first.split(",")]
        if len(parts) < 5:
            return f"GPU: {first[:120]}"
        name, util, mem_u, mem_t, temp = parts[0], parts[1], parts[2], parts[3], parts[4]
        return f"{name} · {util}% · VRAM {mem_u}/{mem_t} MiB · {temp}°C"
    except (subprocess.TimeoutExpired, OSError, TimeoutError):
        return "GPU: error al consultar"
    except Exception:  # noqa: BLE001
        return "GPU: —"


@app.get("/api/status")
async def api_status():
    """Modelo LLM activo y resumen GPU para el header del dashboard."""
    from agents.llm import ANTHROPIC_MODEL, LLM_PROVIDER, OLLAMA_BASE, OLLAMA_MODEL

    if LLM_PROVIDER == "cloud":
        model_label = f"Anthropic · {ANTHROPIC_MODEL}"
    else:
        model_label = f"Ollama · {OLLAMA_MODEL}"

    gpu = await asyncio.to_thread(_gpu_summary)
    return {
        "llm_provider": LLM_PROVIDER,
        "model_label": model_label,
        "ollama_base": OLLAMA_BASE if LLM_PROVIDER != "cloud" else None,
        "gpu": gpu,
    }


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    html_path = HERE / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/api/agents")
async def api_agents():
    """Estado de agentes para el panel izquierdo (todos activos mientras corre el servidor)."""
    agents = [
        {"id": "orchestrator", "name": "Orquestador", "active": True},
        {"id": "web_search", "name": "Web search", "active": True},
        {"id": "memory", "name": "Memoria (Chroma)", "active": True},
        {"id": "code", "name": "Código", "active": True},
        {"id": "neural_network", "name": "Red neuronal", "active": True},
        {"id": "fitness", "name": "Fitness", "active": True},
        {"id": "taskforge", "name": "TaskForge", "active": True},
        {"id": "reminder", "name": "Reminder Daemon", "active": True},
        {"id": "marketing", "name": "Marketing", "active": True},
        {"id": "file", "name": "Archivos", "active": True},
        {"id": "email", "name": "Gmail", "active": True},
        {"id": "calendar", "name": "Calendar", "active": True},
        {"id": "voice", "name": "Voz", "active": True},
        {"id": "image", "name": "Imagen SD", "active": True},
        {"id": "computer_use", "name": "Computer use", "active": True},
        {"id": "github", "name": "GitHub", "active": True},
        {"id": "rag", "name": "RAG docs", "active": True},
        {"id": "obsidian", "name": "Obsidian", "active": True},
        {"id": "rag_obsidian", "name": "RAG Obsidian", "active": True},
        {"id": "mcp", "name": "MCP (si config)", "active": True},
    ]
    return {"agents": agents}


@app.post("/chat")
async def chat(body: ChatIn):
    """Endpoint de compatibilidad (no-streaming). No bloquea el servidor."""
    from agents.orchestrator import run_turn
    msg = await asyncio.to_thread(run_turn, body.message, "dashboard-rest")
    return {"response": msg.content or ""}


@app.websocket("/ws/chat/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str):
    """WebSocket de chat con streaming en tiempo real. Cada sesión tiene su propio thread_id."""
    await websocket.accept()
    try:
        while True:
            text = await websocket.receive_text()
            if not text.strip():
                continue
            from agents.orchestrator import arun_turn_stream
            try:
                async for chunk in arun_turn_stream(text, thread_id=session_id):
                    if chunk:
                        await websocket.send_text(chunk)
                await websocket.send_text("\x00END\x00")  # sentinel de fin de respuesta
            except Exception as exc:  # noqa: BLE001
                await websocket.send_text(f"\nError: {exc}")
                await websocket.send_text("\x00END\x00")
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    log_ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in log_ws_clients:
            log_ws_clients.remove(websocket)


@app.get("/api/taskforge/data")
async def api_taskforge_data():
    from agents.taskforge_tools import _TASKS_FILE, _GOALS_FILE, _HABITS_FILE, _LOGS_FILE, _load
    from datetime import date

    goals = _load(_GOALS_FILE)
    habits = _load(_HABITS_FILE)
    tasks = _load(_TASKS_FILE)
    logs = _load(_LOGS_FILE)
    today = date.today().isoformat()

    # ── RPG stats per goal ──────────────────────────────────────────────────────
    XP_PER_LEVEL = 200
    stat_labels = {"INT": "Intelecto", "CHA": "Carisma", "STR": "Fuerza", "VIT": "Vitalidad", "WIS": "Sabiduría"}
    stat_colors = {"INT": "#6366f1", "CHA": "#ec4899", "STR": "#f97316", "VIT": "#10b981", "WIS": "#f59e0b"}

    rpg_stats = []
    for g in goals:
        stat_key = g.get("stat", "WIS")
        xp = g.get("xp", 0)
        level = max(0, xp // XP_PER_LEVEL)
        xp_in_level = xp % XP_PER_LEVEL
        xp_pct = round((xp_in_level / XP_PER_LEVEL) * 100, 1)
        goal_habits = [h for h in habits if h.get("goal_id") == g["id"]]
        done_today = sum(1 for h in goal_habits if h.get("last_completed") == today)
        rpg_stats.append({
            "goal_id": g["id"],
            "title": g["title"],
            "stat": stat_key,
            "stat_label": stat_labels.get(stat_key, stat_key),
            "color": stat_colors.get(stat_key, g.get("color", "#6366f1")),
            "xp": xp,
            "level": level,
            "xp_in_level": xp_in_level,
            "xp_pct": xp_pct,
            "xp_per_level": XP_PER_LEVEL,
            "habits_total": len(goal_habits),
            "habits_done_today": done_today,
        })

    char_xp = sum(g.get("xp", 0) for g in goals)
    char_level = max(1, char_xp // 100)
    char_xp_pct = round(((char_xp % 500) / 500) * 100, 1)

    habits_enriched = []
    for h in habits:
        h_copy = dict(h)
        h_copy["done_today"] = h.get("last_completed") == today
        habits_enriched.append(h_copy)

    return {
        "tasks": tasks,
        "goals": goals,
        "habits": habits_enriched,
        "logs": logs,
        "rpg": {
            "stats": rpg_stats,
            "char_xp": char_xp,
            "char_level": char_level,
            "char_xp_pct": char_xp_pct,
        }
    }


class GoalIn(BaseModel):
    title: str = Field(..., min_length=1)
    target_date: str = ""
    color: str = "#6366f1"


class HabitIn(BaseModel):
    goal_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    increment: float = 0.5


@app.post("/api/taskforge/goals")
async def api_create_goal(body: GoalIn):
    """Crea una nueva meta desde el dashboard sin usar el chat."""
    from agents.taskforge_tools import taskforge_create_goal
    result = await asyncio.to_thread(
        taskforge_create_goal.invoke,
        {"title": body.title, "target_date": body.target_date, "color": body.color}
    )
    return {"message": result}


@app.post("/api/taskforge/habits")
async def api_create_habit(body: HabitIn):
    """Añade un hábito a una meta desde el dashboard sin usar el chat."""
    from agents.taskforge_tools import taskforge_add_habit
    result = await asyncio.to_thread(
        taskforge_add_habit.invoke,
        {"goal_id": body.goal_id, "title": body.title, "increment": body.increment}
    )
    return {"message": result}


class HabitCompleteIn(BaseModel):
    habit_id: str = Field(..., min_length=1)


@app.post("/api/taskforge/habits/complete")
async def api_complete_habit_route(body: HabitCompleteIn):
    """Marca un hábito como completado hoy desde el dashboard sin usar el chat."""
    from agents.taskforge_tools import taskforge_complete_habit
    result = await asyncio.to_thread(
        taskforge_complete_habit.invoke,
        {"habit_id": body.habit_id}
    )
    return {"message": result}


@app.post("/api/taskforge/habits/uncomplete")
async def api_uncomplete_habit_route(body: HabitCompleteIn):
    """Desmarca un hábito completado hoy desde el dashboard sin usar el chat."""
    from agents.taskforge_tools import taskforge_uncomplete_habit
    result = await asyncio.to_thread(
        taskforge_uncomplete_habit.invoke,
        {"habit_id": body.habit_id}
    )
    return {"message": result}



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
