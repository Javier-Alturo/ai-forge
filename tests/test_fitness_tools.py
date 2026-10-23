"""Fitness tools: history filters, PR suggestions, weekly report, no data loss (fictional data)."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import fitness_report  # noqa: E402
from agents import fitness_tools as ft  # noqa: E402


@pytest.fixture
def fdir(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "_FITNESS_DIR", tmp_path)
    monkeypatch.setattr(ft, "_SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(ft, "_PRS_PATH", tmp_path / "prs.json")
    monkeypatch.setattr(ft, "_PROFILE_PATH", tmp_path / "athlete_profile.json")
    monkeypatch.setattr(ft, "_INJURIES_PATH", tmp_path / "injuries.json")
    return tmp_path


def _log(day: date, split="Push", muscles=("pecho",), name="Press banca", prs=None):
    ex = [{"name": name, "muscles": list(muscles), "sets": [{"reps": 8, "load": 60}] * 3}]
    return ft.fitness_log_session.invoke({
        "session_date": day.isoformat(), "split": split, "focus": "Fuerza", "exercises": ex, "prs": prs,
    })


def test_athlete_name_comes_from_profile(fdir):
    ft._save_json(ft._PROFILE_PATH, {"name": "Atleta Demo"})
    _log(date.today())
    sess = json.loads((fdir / "sessions" / f"{date.today().isoformat()}.json").read_text(encoding="utf-8"))
    assert sess["athlete"] == "Atleta Demo"


def test_history_filters_by_muscle_and_exercise(fdir):
    _log(date.today() - timedelta(days=1), muscles=("espalda",), name="Remo")
    _log(date.today(), muscles=("pecho",), name="Press banca")
    assert "Push" in ft.fitness_get_history.invoke({"muscle": "espalda"})
    out = ft.fitness_get_history.invoke({"exercise_query": "press"})
    assert date.today().isoformat() in out and (date.today() - timedelta(days=1)).isoformat() not in out
    assert "No hay sesiones" in ft.fitness_get_history.invoke({"muscle": "pierna"})


@pytest.mark.parametrize(("pr", "expected"), [
    ({"unit": "kg", "reps": 5, "rir": 1}, "+2.5kg"),
    ({"unit": "lb", "reps": 5, "rir": 2}, "+5lb"),
    ({"unit": "kg", "reps": 12, "rir": 1}, "+2kg"),
    ({"unit": "kg", "reps": 5, "rir": 4}, "repite carga"),
    ({"unit": "kg", "reps": "x", "rir": None}, "repite carga"),
])
def test_pr_suggestion(pr, expected):
    assert expected in ft._pr_suggestion("Sentadilla", pr)


def test_corrupt_prs_file_is_backed_up(fdir):
    ft._PRS_PATH.write_text('{"Sentadilla": {', encoding="utf-8")
    _log(date.today(), prs=[{"exercise": "Press banca", "load": 70, "unit": "kg", "reps": 3, "rir": 1}])
    assert list(fdir.glob("prs.json.corrupt-*"))
    assert "Press banca" in ft.fitness_check_prs.invoke({})


def test_weekly_report(fdir):
    _log(date.today(), muscles=("pecho", "triceps"))
    ft.fitness_injury_log.invoke({"zone": "hombro", "intensity_0_10": 3})
    out = fitness_report.fitness_weekly_report.invoke({})
    assert "Sesiones: 1" in out and "pecho: 3 sets" in out and "hombro 3/10" in out


def test_tool_registry():
    assert {t.name for t in ft.get_fitness_tools()} >= {"fitness_weekly_report", "fitness_check_prs"}
