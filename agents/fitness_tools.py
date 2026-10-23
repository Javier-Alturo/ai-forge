"""Tools del agente de fitness: logging, historial, PRs y reportes.

Persistencia (JSON) en data/fitness/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from core.json_store import load_json, save_json_atomic

_ROOT = Path(__file__).resolve().parent.parent
_FITNESS_DIR = _ROOT / "data" / "fitness"
_SESSIONS_DIR = _FITNESS_DIR / "sessions"
_PRS_PATH = _FITNESS_DIR / "prs.json"
_PROFILE_PATH = _FITNESS_DIR / "athlete_profile.json"
_INJURIES_PATH = _FITNESS_DIR / "injuries.json"


def _ensure_dirs() -> None:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _FITNESS_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    # Un JSON corrupto se respalda (antes devolvía default y el siguiente guardado lo sobrescribía)
    return load_json(path, default)


def _save_json(path: Path, data: Any) -> None:
    save_json_atomic(path, data)


def _parse_yyyy_mm_dd(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _session_path_for(d: date) -> Path:
    return _SESSIONS_DIR / f"{d.isoformat()}.json"


def _list_session_dates() -> list[date]:
    if not _SESSIONS_DIR.exists():
        return []
    out: list[date] = []
    for p in _SESSIONS_DIR.glob("*.json"):
        d = _parse_yyyy_mm_dd(p.stem)
        if d:
            out.append(d)
    return sorted(out)


@dataclass(frozen=True)
class _NextSession:
    split: str  # Push/Pull/Legs
    focus: str  # Fuerza/Hipertrofia


_SPLITS = ["Push", "Pull", "Legs"]
_FOCI = ["Fuerza", "Hipertrofia"]


def _toggle_focus(focus: str) -> str:
    f = (focus or "").strip().capitalize()
    if f.lower().startswith("fuer"):
        return "Hipertrofia"
    if f.lower().startswith("hip"):
        return "Fuerza"
    return "Hipertrofia"


def _next_split(split: str) -> str:
    s = (split or "").strip().capitalize()
    if s not in _SPLITS:
        return "Push"
    idx = _SPLITS.index(s)
    return _SPLITS[(idx + 1) % len(_SPLITS)]


def _get_profile() -> dict[str, Any]:
    _ensure_dirs()
    prof = _load_json(_PROFILE_PATH, default={})
    return prof if isinstance(prof, dict) else {}


def _get_last_known_session() -> dict[str, Any]:
    dates = _list_session_dates()
    if dates:
        last_path = _session_path_for(dates[-1])
        sess = _load_json(last_path, default={})
        if isinstance(sess, dict):
            return sess
    prof = _get_profile()
    last = prof.get("last_session") if isinstance(prof.get("last_session"), dict) else {}
    return last if isinstance(last, dict) else {}


def _compute_next_session() -> _NextSession:
    last = _get_last_known_session()
    last_split = str(last.get("split", "Pull"))
    last_focus = str(last.get("focus", "Fuerza"))
    return _NextSession(split=_next_split(last_split), focus=_toggle_focus(last_focus))


@tool
def fitness_log_session(
    session_date: str,
    split: str,
    focus: str,
    exercises: list[dict],
    notes: str = "",
    perceived_effort_0_10: int | None = None,
    prs: list[dict] | None = None,
) -> str:
    """
    Registra una sesión en data/fitness/sessions/YYYY-MM-DD.json.

    - session_date: "YYYY-MM-DD"
    - split: Push/Pull/Legs
    - focus: Fuerza/Hipertrofia
    - exercises: lista de ejercicios, cada uno con:
      {name, muscles?:[], sets:[{reps, load, unit?, rir?, notes?}], notes?}
    - prs: opcional, lista de PRs logrados en esta sesión.
    """
    _ensure_dirs()
    d = _parse_yyyy_mm_dd(session_date)
    if not d:
        return "Fecha inválida. Usa formato YYYY-MM-DD."

    sess = {
        "athlete": _get_profile().get("name", ""),
        "date": d.isoformat(),
        "split": split,
        "focus": focus,
        "notes": notes or "",
        "perceived_effort_0_10": perceived_effort_0_10,
        "exercises": exercises or [],
        "prs": prs or [],
        "created_at": _utc_now_iso(),
    }
    path = _session_path_for(d)
    _save_json(path, sess)
    a2a_log("fitness", "filesystem", "log_session", f"{path.name} split={split} focus={focus}")

    prof = _get_profile()
    prof["last_session"] = {"date": d.isoformat(), "split": split, "focus": focus}
    _save_json(_PROFILE_PATH, prof)

    if prs:
        _update_prs_from_entries(prs, session_date=d.isoformat())
    return f"Sesión guardada en {path.as_posix()}."


def _update_prs_from_entries(entries: list[dict], session_date: str) -> None:
    current = _load_json(_PRS_PATH, default={})
    if not isinstance(current, dict):
        current = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        ex = str(e.get("exercise", "") or e.get("name", "")).strip()
        if not ex:
            continue
        pr = {
            "exercise": ex,
            "load": e.get("load"),
            "unit": e.get("unit"),
            "reps": e.get("reps"),
            "rir": e.get("rir"),
            "date": e.get("date") or session_date,
            "source": "session_pr",
        }
        current[ex] = pr
    _save_json(_PRS_PATH, current)


def _session_matches(sess: dict, muscle_q: str, ex_q: str) -> bool:
    """True si la sesión contiene un ejercicio cuyo nombre o músculos coinciden con el filtro."""
    if not (muscle_q or ex_q):
        return True
    for ex in sess.get("exercises") or []:
        if not isinstance(ex, dict):
            continue
        if ex_q and ex_q in str(ex.get("name", "")).lower():
            return True
        muscles = [str(m).lower() for m in (ex.get("muscles") or []) if m]
        if muscle_q and any(muscle_q in m for m in muscles):
            return True
    return False


def _dates_in_range(start: date | None, end: date | None) -> list[date]:
    """Fechas con sesión dentro del rango, más recientes primero."""
    dates = [d for d in _list_session_dates() if (not start or d >= start) and (not end or d <= end)]
    return list(reversed(dates))


@tool
def fitness_get_history(
    start_date: str | None = None,
    end_date: str | None = None,
    muscle: str | None = None,
    exercise_query: str | None = None,
    limit: int = 30,
) -> str:
    """Recupera historial de sesiones por rango de fechas o músculo."""
    _ensure_dirs()
    sd = _parse_yyyy_mm_dd(start_date or "") if start_date else None
    ed = _parse_yyyy_mm_dd(end_date or "") if end_date else None
    muscle_q = (muscle or "").strip().lower()
    ex_q = (exercise_query or "").strip().lower()

    out: list[str] = []
    for d in _dates_in_range(sd, ed):
        sess = _load_json(_session_path_for(d), default={})
        if not isinstance(sess, dict) or not _session_matches(sess, muscle_q, ex_q):
            continue
        out.append(f"- {sess.get('date')} | {sess.get('split')} {sess.get('focus')} | notas: {str(sess.get('notes',''))[:120]}")
        if len(out) >= int(limit):
            break
    return "\n".join(out) if out else "No hay sesiones que coincidan con el filtro."


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pr_suggestion(ex: str, pr: dict) -> str:
    """Heurística: subir carga si el último PR fue con RIR<=2; si no, consolidar reps/técnica."""
    unit = str(pr.get("unit") or "").lower()
    reps = _to_float(pr.get("reps"))
    rir = _to_float(pr.get("rir"))
    inc = 5.0 if "lb" in unit else 2.5
    if reps is not None and reps >= 10 and "kg" in unit:
        inc = 2.0
    if rir is not None and rir <= 2.0:
        return f"- {ex}: prueba +{inc:g}{pr.get('unit') or ''} la próxima vez (manteniendo RIR~1-2)."
    return f"- {ex}: repite carga y busca mejorar reps/técnica antes de subir."


@tool
def fitness_check_prs() -> str:
    """Muestra PRs actuales y sugiere progresión basada en el historial."""
    _ensure_dirs()
    prs = _load_json(_PRS_PATH, default={})
    if not isinstance(prs, dict) or not prs:
        return "No hay PRs registrados aún."
    valid = {ex: pr for ex, pr in prs.items() if isinstance(pr, dict)}

    lines = ["PRs actuales:"]
    lines += [
        f"- {ex}: {pr.get('load')}{pr.get('unit') or ''}×{pr.get('reps')} @RIR{pr.get('rir')} ({pr.get('date') or ''})"
        for ex, pr in valid.items()
    ]
    lines += ["", "Sugerencias de progresión (heurística):"]
    lines += [_pr_suggestion(ex, pr) for ex, pr in valid.items()]

    last_dates = _list_session_dates()
    if last_dates:
        lines += ["", f"Última sesión registrada: {last_dates[-1].isoformat()}"]
    return "\n".join(lines).strip()


@tool
def fitness_next_session() -> str:
    """Basado en el historial decide qué día toca (Push/Pull/Legs, Fuerza/Hipertrofia)."""
    _ensure_dirs()
    nxt = _compute_next_session()
    prof = _get_profile()
    protected = prof.get("protected_zones") or {}
    return (
        f"Próxima sesión sugerida: {nxt.split} {nxt.focus}.\n"
        f"Zonas protegidas: {json.dumps(protected, ensure_ascii=False)}"
    )


@tool
def fitness_injury_log(
    zone: str,
    intensity_0_10: int,
    caused_by_exercise: str | None = None,
    notes: str | None = None,
    injury_date: str | None = None,
) -> str:
    """Registra molestias articulares con zona, intensidad 0-10, ejercicio causante."""
    _ensure_dirs()
    d = _parse_yyyy_mm_dd(injury_date or "") if injury_date else None
    entry = {
        "date": (d.isoformat() if d else date.today().isoformat()),
        "zone": (zone or "").strip(),
        "intensity_0_10": int(intensity_0_10),
        "caused_by_exercise": (caused_by_exercise or "").strip() or None,
        "notes": (notes or "").strip() or None,
        "created_at": _utc_now_iso(),
    }
    data = _load_json(_INJURIES_PATH, default=[])
    if not isinstance(data, list):
        data = []
    data.append(entry)
    _save_json(_INJURIES_PATH, data)
    a2a_log("fitness", "filesystem", "injury_log", f"{entry['zone']} {entry['intensity_0_10']}/10")
    return "Molestia registrada."


def get_fitness_tools():
    from agents.fitness_report import fitness_weekly_report  # import diferido: fitness_report importa este módulo

    return [
        fitness_log_session,
        fitness_get_history,
        fitness_check_prs,
        fitness_next_session,
        fitness_weekly_report,
        fitness_injury_log,
    ]

