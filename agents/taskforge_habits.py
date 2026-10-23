"""TaskForge — habit tools (add, complete, uncomplete, delete) and the goal XP/progress logic."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.taskforge_store import _GOALS_FILE, _HABITS_FILE, _LOGS_FILE, _load, _now, _save, _today

XP_PER_LEVEL = 200

# Incrementos especiales (meta semanal, hábito) -> % por completado. Ej: 5 entrenamientos = 100%.
_WEEKLY_INCREMENTS = {("w_gym_01", "gym_h001"): 20.0, ("w_eng_01", "e89a2afe"): 33.33}


def _apply_to_goal(goal: dict, progress_delta: float, xp_delta: int) -> None:
    """Suma (o resta) progreso y XP a una meta, acotando progreso a [0, 100] y XP a >= 0."""
    goal["progress"] = min(100.0, max(0.0, round(goal["progress"] + progress_delta, 2)))
    goal["xp"] = max(0, goal.get("xp", 0) + xp_delta)
    goal["level"] = goal["xp"] // XP_PER_LEVEL


def _apply_habit(habit: dict, goals: list, sign: int) -> dict | None:
    """Aplica (sign=+1) o revierte (sign=-1) el efecto de un hábito en su meta y en las
    metas relacionadas (misma stat, p.ej. metas semanales). Devuelve la meta principal."""
    goal = next((g for g in goals if g["id"] == habit["goal_id"]), None)
    if goal is None:
        return None
    xp = sign * habit.get("xp_reward", 20)
    _apply_to_goal(goal, sign * habit.get("increment", 0.5), xp)
    stat_key = goal.get("stat")
    for other in goals:
        if stat_key and other["id"] != goal["id"] and other.get("stat") == stat_key:
            inc = _WEEKLY_INCREMENTS.get((other["id"], habit["id"]), habit.get("increment", 0.5))
            _apply_to_goal(other, sign * inc, xp)
    return goal


def _update_streak(habit: dict) -> None:
    """Suma 1 a la racha si el último completado fue ayer; si no, la reinicia a 1."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    habit["streak"] = habit.get("streak", 0) + 1 if habit.get("last_completed") == yesterday else 1
    habit["last_completed"] = _today()


def _progress_str(goal: dict | None, old_progress: float) -> str:
    if not goal:
        return ""
    return f" | Meta '{goal['title']}': {old_progress:.1f}% → {goal['progress']:.1f}% | Nivel {goal['level']}"


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
    if goal_id not in {g["id"] for g in _load(_GOALS_FILE)}:
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
    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return f"Habito [{habit_id}] no encontrado. Usa taskforge_get_goals para ver los habitos."
    if habit.get("last_completed") == _today():
        return f"El habito '{habit['title']}' ya fue completado hoy."

    _update_streak(habit)
    _save(_HABITS_FILE, habits)

    goals = _load(_GOALS_FILE)
    old_progress = next((g["progress"] for g in goals if g["id"] == habit["goal_id"]), 0)
    goal = _apply_habit(habit, goals, sign=+1)
    if goal:
        _save(_GOALS_FILE, goals)

    xp_earned = habit.get("xp_reward", 20)
    logs = _load(_LOGS_FILE)
    logs.append({
        "habit_id": habit_id,
        "action": "habit_completed",
        "xp_earned": xp_earned,
        "date": _today(),
        "created_at": _now(),
    })
    _save(_LOGS_FILE, logs)

    streak_bonus = " 🔥🔥" if habit["streak"] >= 7 else " 🔥" if habit["streak"] >= 3 else ""
    return (
        f"✅ Hábito completado: '{habit['title']}' | "
        f"Racha: {habit['streak']} días{streak_bonus} | +{xp_earned} XP{_progress_str(goal, old_progress)}"
    )


@tool
def taskforge_uncomplete_habit(habit_id: str) -> str:
    """Marca un habito como no completado hoy y revierte el progreso y XP de su meta.

    Args:
        habit_id: ID del habito a desmarcar.
    """
    a2a_log("taskforge", "habits", "uncomplete_habit", habit_id)
    habits = _load(_HABITS_FILE)
    habit = next((h for h in habits if h["id"] == habit_id), None)
    if not habit:
        return f"Habito [{habit_id}] no encontrado."
    if habit.get("last_completed") != _today():
        return f"El habito '{habit['title']}' no ha sido completado hoy."

    habit["streak"] = max(0, habit.get("streak", 1) - 1)
    habit["last_completed"] = None
    _save(_HABITS_FILE, habits)

    goals = _load(_GOALS_FILE)
    old_progress = next((g["progress"] for g in goals if g["id"] == habit["goal_id"]), 0)
    goal = _apply_habit(habit, goals, sign=-1)
    if goal:
        _save(_GOALS_FILE, goals)

    logs = _load(_LOGS_FILE)
    kept = [
        entry for entry in logs
        if not (entry.get("habit_id") == habit_id and entry.get("date") == _today()
                and entry.get("action") == "habit_completed")
    ]
    _save(_LOGS_FILE, kept)
    return f"🔄 Hábito desmarcado: '{habit['title']}'{_progress_str(goal, old_progress)}"


@tool
def taskforge_delete_habit(habit_id: str) -> str:
    """Elimina un hábito por su ID.

    Args:
        habit_id: ID del hábito a eliminar.
    """
    a2a_log("taskforge", "habits", "delete_habit", habit_id)
    habits = _load(_HABITS_FILE)
    if not any(h["id"] == habit_id for h in habits):
        return f"Hábito [{habit_id}] no encontrado."
    _save(_HABITS_FILE, [h for h in habits if h["id"] != habit_id])
    return f"Hábito [{habit_id}] eliminado correctamente."
