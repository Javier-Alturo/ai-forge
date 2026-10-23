"""TaskForge habits: XP/progress apply and revert, streaks, clamping (fictional data)."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import taskforge_habits as habits_mod  # noqa: E402
from agents import taskforge_store as store  # noqa: E402

NAMES = ("_TASKS_FILE", "_GOALS_FILE", "_HABITS_FILE", "_LOGS_FILE")


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_TASKFORGE_DIR", tmp_path)
    for name in NAMES:
        path = tmp_path / f"{name.strip('_').lower().replace('_file', '')}.json"
        monkeypatch.setattr(store, name, path)
        if hasattr(habits_mod, name):
            monkeypatch.setattr(habits_mod, name, path)
    return tmp_path


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# ── Habits ───────────────────────────────────────────────────────────────────

GOAL = {"id": "g1", "title": "Aprender Docker", "progress": 10.0, "xp": 190, "level": 0, "stat": "int"}
WEEKLY = {"id": "w1", "title": "Semana", "progress": 0.0, "xp": 0, "level": 0, "stat": "int"}
HABIT = {"id": "h1", "goal_id": "g1", "title": "Leer docs", "increment": 2.0, "streak": 0, "last_completed": None}


def _seed(goals=(GOAL, WEEKLY), habit=HABIT):
    _write(store._GOALS_FILE, [dict(g) for g in goals])
    _write(store._HABITS_FILE, [dict(habit)])
    _write(store._LOGS_FILE, [])


def test_complete_then_uncomplete_restores_state(data_dir):
    _seed()
    out = habits_mod.taskforge_complete_habit.invoke({"habit_id": "h1"})
    assert "Hábito completado" in out
    goals = {g["id"]: g for g in store._load(store._GOALS_FILE)}
    assert goals["g1"]["progress"] == 12.0 and goals["g1"]["xp"] == 210 and goals["g1"]["level"] == 1
    assert goals["w1"]["progress"] == 2.0  # propagated to related goal (same stat)
    assert len(store._load(store._LOGS_FILE)) == 1

    habits_mod.taskforge_uncomplete_habit.invoke({"habit_id": "h1"})
    goals = {g["id"]: g for g in store._load(store._GOALS_FILE)}
    assert goals["g1"]["progress"] == 10.0 and goals["g1"]["xp"] == 190 and goals["g1"]["level"] == 0
    assert goals["w1"]["progress"] == 0.0
    assert store._load(store._LOGS_FILE) == []


def test_complete_twice_same_day_is_refused(data_dir):
    _seed()
    habits_mod.taskforge_complete_habit.invoke({"habit_id": "h1"})
    assert "ya fue completado" in habits_mod.taskforge_complete_habit.invoke({"habit_id": "h1"})


def test_streak_continues_from_yesterday(data_dir):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _seed(habit={**HABIT, "streak": 4, "last_completed": yesterday})
    habits_mod.taskforge_complete_habit.invoke({"habit_id": "h1"})
    assert store._load(store._HABITS_FILE)[0]["streak"] == 5


def test_progress_is_clamped(data_dir):
    _seed(goals=({**GOAL, "progress": 99.5},), habit={**HABIT, "increment": 5.0})
    habits_mod.taskforge_complete_habit.invoke({"habit_id": "h1"})
    assert store._load(store._GOALS_FILE)[0]["progress"] == 100.0


def test_unknown_habit(data_dir):
    _seed()
    assert "no encontrado" in habits_mod.taskforge_complete_habit.invoke({"habit_id": "zzz"})


def test_taskforge_tools_reexports():
    from agents import taskforge_tools

    assert taskforge_tools._load is store._load
    assert taskforge_tools.taskforge_complete_habit is habits_mod.taskforge_complete_habit
    assert len(taskforge_tools.get_taskforge_tools()) == 12
