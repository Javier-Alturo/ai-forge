"""
TaskForge Tools — Gestion de tareas diarias, metas a largo plazo y habitos.

Persistencia: data/taskforge/tasks.json + data/taskforge/goals.json
Patron: mismo que Fitness Agent (JSON plano, sin dependencias externas).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path

from langchain_core.tools import tool

from agents.a2a_log import a2a_log

# ── Rutas de datos ────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_TASKFORGE_DIR = _ROOT / "data" / "taskforge"
_TASKS_FILE    = _TASKFORGE_DIR / "tasks.json"
_GOALS_FILE    = _TASKFORGE_DIR / "goals.json"
_HABITS_FILE   = _TASKFORGE_DIR / "habits.json"
_LOGS_FILE     = _TASKFORGE_DIR / "logs.json"


def _ensure_dirs() -> None:
    _TASKFORGE_DIR.mkdir(parents=True, exist_ok=True)
    for f in [_TASKS_FILE, _GOALS_FILE, _HABITS_FILE, _LOGS_FILE]:
        if not f.exists():
            f.write_text("[]", encoding="utf-8")


def _load(path: Path) -> list:
    _ensure_dirs()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(path: Path, data: list) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── TOOLS DE TAREAS ───────────────────────────────────────────────────────────

@tool
def taskforge_add_task(
    title: str,
    priority: str = "medium",
    reminder_time: str = "",
    description: str = "",
) -> str:
    """Crea una nueva tarea para hoy.

    Args:
        title: Titulo de la tarea (obligatorio).
        priority: 'high', 'medium' o 'low'. Default: 'medium'.
        reminder_time: Hora del recordatorio en formato HH:MM (24h). Opcional.
        description: Descripcion adicional. Opcional.
    """
    a2a_log("taskforge", "tasks", "add_task", title[:80])
    tasks = _load(_TASKS_FILE)
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "description": description,
        "priority": priority if priority in ("high", "medium", "low") else "medium",
        "reminder_time": reminder_time,
        "completed": False,
        "completed_at": None,
        "carried_over": False,
        "date": _today(),
        "created_at": _now(),
    }
    tasks.append(task)
    _save(_TASKS_FILE, tasks)
    reminder_str = f" | Recordatorio: {reminder_time}" if reminder_time else ""
    return f"Tarea creada [{task['id']}]: '{title}' ({priority}){reminder_str}"


@tool
def taskforge_get_today() -> str:
    """Retorna todas las tareas de hoy con su estado."""
    a2a_log("taskforge", "tasks", "get_today", _today())
    tasks = _load(_TASKS_FILE)
    today_tasks = [t for t in tasks if t.get("date") == _today()]
    if not today_tasks:
        return "No hay tareas para hoy. Puedes crear una con taskforge_add_task."

    lines = [f"Tareas de hoy ({_today()}):"]
    for t in today_tasks:
        status = "OK" if t["completed"] else "pendiente"
        prio = {"high": "ALTA", "medium": "MEDIA", "low": "BAJA"}.get(t["priority"], t["priority"])
        reminder = f" [{t['reminder_time']}]" if t.get("reminder_time") else ""
        carried = " (arrastrada)" if t.get("carried_over") else ""
        lines.append(f"  [{t['id']}] {status} | {prio}{reminder}{carried} — {t['title']}")
    return "\n".join(lines)


@tool
def taskforge_complete_task(task_id: str) -> str:
    """Marca una tarea como completada por su ID.

    Args:
        task_id: ID corto de la tarea (primeros 8 caracteres del UUID).
    """
    a2a_log("taskforge", "tasks", "complete_task", task_id)
    tasks = _load(_TASKS_FILE)
    logs  = _load(_LOGS_FILE)

    for t in tasks:
        if t["id"] == task_id:
            if t["completed"]:
                return f"La tarea [{task_id}] ya estaba marcada como completada."
            t["completed"] = True
            t["completed_at"] = _now()
            _save(_TASKS_FILE, tasks)
            logs.append({"task_id": task_id, "action": "completed", "created_at": _now()})
            _save(_LOGS_FILE, logs)
            return f"Tarea [{task_id}] completada: '{t['title']}'"

    return f"No se encontro la tarea con ID [{task_id}]. Usa taskforge_get_today para ver los IDs."


@tool
def taskforge_carry_over_tasks() -> str:
    """Arrastra las tareas incompletas de ayer a hoy.
    Ejecutar al inicio del dia o cuando el sistema detecte tareas de dias anteriores.
    """
    a2a_log("taskforge", "tasks", "carry_over", _today())
    tasks = _load(_TASKS_FILE)
    today = _today()
    carried = 0

    for t in tasks:
        if t["date"] < today and not t["completed"]:
            t["carried_over"] = True
            t["date"] = today
            carried += 1

    _save(_TASKS_FILE, tasks)
    if carried == 0:
        return "No hay tareas pendientes de dias anteriores."
    return f"{carried} tarea(s) arrastradas a hoy desde dias anteriores."


# ── TOOLS DE METAS ────────────────────────────────────────────────────────────

@tool
def taskforge_create_goal(
    title: str,
    target_date: str = "",
    color: str = "#6366f1",
) -> str:
    """Crea una nueva meta a largo plazo.

    Args:
        title: Nombre de la meta (ej: 'Alcanzar ingles B2').
        target_date: Fecha objetivo en formato YYYY-MM-DD. Opcional.
        color: Color hex para el indicador visual. Default: indigo.
    """
    a2a_log("taskforge", "goals", "create_goal", title[:80])
    goals = _load(_GOALS_FILE)
    goal = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "target_date": target_date,
        "progress": 0.0,
        "color": color,
        "created_at": _now(),
    }
    goals.append(goal)
    _save(_GOALS_FILE, goals)
    date_str = f" | Fecha objetivo: {target_date}" if target_date else ""
    return f"Meta creada [{goal['id']}]: '{title}'{date_str} | Progreso: 0%"


@tool
def taskforge_get_goals() -> str:
    """Retorna todas las metas activas con su progreso y habitos."""
    a2a_log("taskforge", "goals", "get_goals", "all")
    goals  = _load(_GOALS_FILE)
    habits = _load(_HABITS_FILE)

    if not goals:
        return "No hay metas creadas. Usa taskforge_create_goal para crear una."

    lines = ["Metas activas:"]
    for g in goals:
        goal_habits = [h for h in habits if h.get("goal_id") == g["id"]]
        habit_list = ", ".join(h["title"] for h in goal_habits) or "(sin habitos)"
        bar = "#" * int(g["progress"] / 5) + "." * (20 - int(g["progress"] / 5))
        lines.append(
            f"\n  [{g['id']}] {g['title']}\n"
            f"  Progreso: [{bar}] {g['progress']:.1f}%\n"
            f"  Fecha objetivo: {g.get('target_date', 'sin fecha')}\n"
            f"  Habitos: {habit_list}"
        )
    return "\n".join(lines)


# ── TOOLS DE HABITOS ──────────────────────────────────────────────────────────

@tool
def taskforge_add_habit(
    goal_id: str,
    title: str,
    increment: float = 0.5,
) -> str:
    """Adjunta un habito diario a una meta.

    Args:
        goal_id: ID de la meta a la que pertenece este habito.
        title: Descripcion del habito (ej: 'Grabar 1 video en ingles').
        increment: Cuanto sube el progreso de la meta al completar (default: 0.5%).
    """
    a2a_log("taskforge", "habits", "add_habit", f"{goal_id}:{title[:60]}")
    goals = _load(_GOALS_FILE)
    goal_ids = [g["id"] for g in goals]

    if goal_id not in goal_ids:
        return f"Meta [{goal_id}] no encontrada. Usa taskforge_get_goals para ver los IDs."

    habits = _load(_HABITS_FILE)
    habit = {
        "id": str(uuid.uuid4())[:8],
        "goal_id": goal_id,
        "title": title,
        "increment": increment,
        "streak": 0,
        "last_completed": None,
        "created_at": _now(),
    }
    habits.append(habit)
    _save(_HABITS_FILE, habits)
    return f"Habito creado [{habit['id']}]: '{title}' (+{increment}% por completar) -> Meta [{goal_id}]"


@tool
def taskforge_complete_habit(habit_id: str) -> str:
    """Marca un habito como completado hoy y actualiza el progreso de su meta.

    Args:
        habit_id: ID del habito a completar.
    """
    a2a_log("taskforge", "habits", "complete_habit", habit_id)
    habits = _load(_HABITS_FILE)
    goals  = _load(_GOALS_FILE)
    logs   = _load(_LOGS_FILE)

    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return f"Habito [{habit_id}] no encontrado. Usa taskforge_get_goals para ver los habitos."

    # Verificar si ya se completo hoy
    if habit.get("last_completed") == _today():
        return f"El habito '{habit['title']}' ya fue completado hoy."

    # Actualizar racha
    from datetime import timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if habit.get("last_completed") == yesterday:
        habit["streak"] = habit.get("streak", 0) + 1
    else:
        habit["streak"] = 1
    habit["last_completed"] = _today()
    _save(_HABITS_FILE, habits)

    # Actualizar progreso + XP de la meta (sistema RPG)
    goal = next((g for g in goals if g["id"] == habit["goal_id"]), None)
    old_progress = goal["progress"] if goal else 0
    xp_earned = habit.get("xp_reward", 20)
    if goal:
        goal["progress"] = min(100.0, round(goal["progress"] + habit.get("increment", 0.5), 2))
        goal["xp"] = goal.get("xp", 0) + xp_earned
        XP_PER_LEVEL = 200
        goal["level"] = goal["xp"] // XP_PER_LEVEL

        # Propagar a metas relacionadas (como metas semanales compartiendo la misma stat)
        stat_key = goal.get("stat")
        if stat_key:
            for other_g in goals:
                if other_g["id"] != goal["id"] and other_g.get("stat") == stat_key:
                    inc = habit.get("increment", 0.5)
                    # Incrementos proporcionales según el tipo de meta semanal
                    if other_g["id"] == "w_gym_01" and habit["id"] == "gym_h001":
                        inc = 20.0  # 5 entrenamientos = 100%
                    elif other_g["id"] == "w_eng_01" and habit["id"] == "e89a2afe":
                        inc = 33.33 # 3 videos = 100%
                    
                    other_g["progress"] = min(100.0, round(other_g["progress"] + inc, 2))
                    other_g["xp"] = other_g.get("xp", 0) + xp_earned
                    other_g["level"] = other_g["xp"] // XP_PER_LEVEL
        
        _save(_GOALS_FILE, goals)

    # Registrar log
    logs.append({
        "habit_id": habit_id,
        "action": "habit_completed",
        "xp_earned": xp_earned,
        "date": _today(),
        "created_at": _now(),
    })
    _save(_LOGS_FILE, logs)

    progress_str = ""
    xp_str = f" | +{xp_earned} XP"
    if goal:
        progress_str = f" | Meta '{goal['title']}': {old_progress:.1f}% → {goal['progress']:.1f}% | Nivel {goal['level']}"

    streak_bonus = " 🔥🔥" if habit["streak"] >= 7 else " 🔥" if habit["streak"] >= 3 else ""
    return (
        f"✅ Hábito completado: '{habit['title']}' | "
        f"Racha: {habit['streak']} días{streak_bonus}{xp_str}{progress_str}"
    )


@tool
def taskforge_uncomplete_habit(habit_id: str) -> str:
    """Marca un habito como no completado hoy y revierte el progreso y XP de su meta.

    Args:
        habit_id: ID del habito a desmarcar.
    """
    a2a_log("taskforge", "habits", "uncomplete_habit", habit_id)
    habits = _load(_HABITS_FILE)
    goals  = _load(_GOALS_FILE)
    logs   = _load(_LOGS_FILE)

    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return f"Habito [{habit_id}] no encontrado."

    if habit.get("last_completed") != _today():
        return f"El habito '{habit['title']}' no ha sido completado hoy."

    # Descontar racha (si subió, restar 1, o resetear)
    habit["streak"] = max(0, habit.get("streak", 1) - 1)
    habit["last_completed"] = None
    _save(_HABITS_FILE, habits)

    # Revertir progreso + XP de la meta
    goal = next((g for g in goals if g["id"] == habit["goal_id"]), None)
    old_progress = goal["progress"] if goal else 0
    xp_lost = habit.get("xp_reward", 20)
    if goal:
        goal["progress"] = max(0.0, round(goal["progress"] - habit.get("increment", 0.5), 2))
        goal["xp"] = max(0, goal.get("xp", 0) - xp_lost)
        XP_PER_LEVEL = 200
        goal["level"] = goal["xp"] // XP_PER_LEVEL

        # Revertir en metas relacionadas (como metas semanales compartiendo la misma stat)
        stat_key = goal.get("stat")
        if stat_key:
            for other_g in goals:
                if other_g["id"] != goal["id"] and other_g.get("stat") == stat_key:
                    inc = habit.get("increment", 0.5)
                    # Revertir incrementos proporcionales específicos
                    if other_g["id"] == "w_gym_01" and habit["id"] == "gym_h001":
                        inc = 20.0  # 5 entrenamientos = 100%
                    elif other_g["id"] == "w_eng_01" and habit["id"] == "e89a2afe":
                        inc = 33.33 # 3 videos = 100%
                    
                    other_g["progress"] = max(0.0, round(other_g["progress"] - inc, 2))
                    other_g["xp"] = max(0, other_g.get("xp", 0) - xp_lost)
                    other_g["level"] = other_g["xp"] // XP_PER_LEVEL
        
        _save(_GOALS_FILE, goals)

    # Eliminar log de hoy para este hábito
    new_logs = [log for log in logs if not (log.get("habit_id") == habit_id and log.get("date") == _today() and log.get("action") == "habit_completed")]
    _save(_LOGS_FILE, new_logs)

    progress_str = ""
    if goal:
        progress_str = f" | Meta '{goal['title']}': {old_progress:.1f}% → {goal['progress']:.1f}% | Nivel {goal['level']}"

    return f"🔄 Hábito desmarcado: '{habit['title']}'{progress_str}"




# ── TOOLS DE METRICAS ─────────────────────────────────────────────────────────

@tool
def taskforge_get_metrics() -> str:
    """Retorna metricas de la semana: tasa de completacion, habitos, rachas."""
    a2a_log("taskforge", "metrics", "get_metrics", "weekly")
    from datetime import timedelta

    tasks  = _load(_TASKS_FILE)
    habits = _load(_HABITS_FILE)
    logs   = _load(_LOGS_FILE)

    today     = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    week_end   = today.isoformat()

    week_tasks = [t for t in tasks if week_start <= t.get("date", "") <= week_end]
    created    = len(week_tasks)
    completed  = len([t for t in week_tasks if t["completed"]])
    rate       = (completed / created * 100) if created > 0 else 0

    habit_lines = []
    for h in habits:
        habit_lines.append(f"  {h['title']}: racha {h.get('streak', 0)} dias")

    habit_str = "\n".join(habit_lines) if habit_lines else "  (sin habitos)"

    return (
        f"Metricas de la semana ({week_start} -> {week_end}):\n"
        f"  Tareas creadas: {created}\n"
        f"  Tareas completadas: {completed}\n"
        f"  Tasa de completacion: {rate:.0f}%\n\n"
        f"Rachas de habitos:\n{habit_str}"
    )


@tool
def taskforge_history(days: int = 7) -> str:
    """Retorna el historial de tareas completadas en los ultimos N dias.

    Args:
        days: Numero de dias hacia atras. Default: 7.
    """
    a2a_log("taskforge", "tasks", "history", f"last_{days}_days")
    from datetime import timedelta

    tasks = _load(_TASKS_FILE)
    today = date.today()
    since = (today - timedelta(days=days)).isoformat()

    completed = [
        t for t in tasks
        if t.get("completed") and t.get("date", "") >= since
    ]

    if not completed:
        return f"No hay tareas completadas en los ultimos {days} dias."

    by_date: dict = {}
    for t in completed:
        d = t.get("date", "?")
        by_date.setdefault(d, []).append(t["title"])

    lines = [f"Historial ultimos {days} dias:"]
    for d in sorted(by_date.keys(), reverse=True):
        lines.append(f"\n  {d}:")
        for title in by_date[d]:
            lines.append(f"    - {title}")

    return "\n".join(lines)


@tool
def taskforge_delete_goal(goal_id: str) -> str:
    """Elimina una meta y todos sus hábitos asociados.

    Args:
        goal_id: ID de la meta a eliminar.
    """
    a2a_log("taskforge", "goals", "delete_goal", goal_id)
    goals = _load(_GOALS_FILE)
    habits = _load(_HABITS_FILE)

    goal_exists = any(g["id"] == goal_id for g in goals)
    if not goal_exists:
        return f"Meta [{goal_id}] no encontrada."

    new_goals = [g for g in goals if g["id"] != goal_id]
    new_habits = [h for h in habits if h.get("goal_id") != goal_id]

    _save(_GOALS_FILE, new_goals)
    _save(_HABITS_FILE, new_habits)
    return f"Meta [{goal_id}] y sus hábitos asociados han sido eliminados correctamente."


@tool
def taskforge_delete_habit(habit_id: str) -> str:
    """Elimina un hábito por su ID.

    Args:
        habit_id: ID del hábito a eliminar.
    """
    a2a_log("taskforge", "habits", "delete_habit", habit_id)
    habits = _load(_HABITS_FILE)

    habit_exists = any(h["id"] == habit_id for h in habits)
    if not habit_exists:
        return f"Hábito [{habit_id}] no encontrado."

    new_habits = [h for h in habits if h["id"] != habit_id]
    _save(_HABITS_FILE, new_habits)
    return f"Hábito [{habit_id}] eliminado correctamente."


# ── EXPORT ────────────────────────────────────────────────────────────────────

def get_taskforge_tools():
    return [
        taskforge_add_task,
        taskforge_get_today,
        taskforge_complete_task,
        taskforge_carry_over_tasks,
        taskforge_create_goal,
        taskforge_get_goals,
        taskforge_add_habit,
        taskforge_complete_habit,
        taskforge_get_metrics,
        taskforge_history,
        taskforge_delete_goal,
        taskforge_delete_habit,
    ]
