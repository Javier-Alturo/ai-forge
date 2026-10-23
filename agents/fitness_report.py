"""Fitness weekly report: volume per muscle, PRs and injuries for a 7-day window.

Split from fitness_tools.py to keep each module small; reads the same JSON files.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from langchain_core.tools import tool

from agents import fitness_tools as ft


def _sessions_between(start: date, end: date) -> list[dict[str, Any]]:
    sessions = []
    for d in ft._list_session_dates():
        if start <= d <= end:
            s = ft._load_json(ft._session_path_for(d), default={})
            if isinstance(s, dict):
                sessions.append(s)
    return sessions


def _volume_by_muscle(sessions: list[dict[str, Any]]) -> dict[str, int]:
    sets_by_muscle: dict[str, int] = {}
    for s in sessions:
        for ex in s.get("exercises") or []:
            if not isinstance(ex, dict):
                continue
            n_sets = len(ex.get("sets") or [])
            for m in ex.get("muscles") or []:
                key = str(m).strip().lower()
                if key:
                    sets_by_muscle[key] = sets_by_muscle.get(key, 0) + n_sets
    return sets_by_muscle


def _prs_hit(sessions: list[dict[str, Any]]) -> list[str]:
    return [
        f"{pr.get('exercise') or pr.get('name')}: {pr.get('load')}{pr.get('unit', '')}×{pr.get('reps')} @RIR{pr.get('rir')}"
        for s in sessions
        for pr in (s.get("prs") or [])
        if isinstance(pr, dict)
    ]


def _injuries_between(start: date, end: date) -> list[dict[str, Any]]:
    injuries = ft._load_json(ft._INJURIES_PATH, default=[])
    if not isinstance(injuries, list):
        return []
    out = []
    for i in injuries:
        d = ft._parse_yyyy_mm_dd(str(i.get("date", ""))) if isinstance(i, dict) else None
        if d is not None and start <= d <= end:
            out.append(i)
    return out


def _section(title: str, items: list[str], empty: str) -> list[str]:
    return ["", title] + (items or [empty])


@tool
def fitness_weekly_report(week_ending: str | None = None) -> str:
    """Reporte semanal de volumen, PRs, lesiones, progresiones."""
    ft._ensure_dirs()
    end = (ft._parse_yyyy_mm_dd(week_ending or "") if week_ending else None) or date.today()
    start = end - timedelta(days=6)
    sessions = _sessions_between(start, end)
    volume = _volume_by_muscle(sessions)
    injuries = _injuries_between(start, end)

    lines = [f"Reporte semanal ({start.isoformat()} → {end.isoformat()}):", f"- Sesiones: {len(sessions)}"]
    if sessions:
        lines.append("- Detalle sesiones:")
        lines += [f"  - {s.get('date')} | {s.get('split')} {s.get('focus')}" for s in sessions]
    lines += _section(
        "Volumen (sets por músculo, según tags en ejercicios):",
        [f"- {m}: {n} sets" for m, n in sorted(volume.items(), key=lambda kv: (-kv[1], kv[0]))],
        "- (Sin datos de músculos/sets; añade 'muscles' en exercises para reportes mejores.)",
    )
    lines += _section("PRs de la semana:", [f"- {x}" for x in _prs_hit(sessions)[:60]], "- (Ninguno registrado)")
    lines += _section(
        "Lesiones/molestias de la semana:",
        [
            f"- {i.get('date')} | {i.get('zone')} {i.get('intensity_0_10')}/10 | causa: {i.get('caused_by_exercise') or '-'}"
            for i in injuries[-30:]
        ],
        "- (Sin registros)",
    )
    lines += [
        "",
        "Progresión sugerida:",
        "- Revisa `fitness_check_prs` y prioriza incrementos pequeños si RIR<=2.",
        "- Si aparece molestia, reduce rango/volumen y cambia variantes 1-2 semanas.",
    ]
    return "\n".join(lines).strip()
