"""Tools del agente de fitness: logging, historial, PRs y reportes.

Persistencia (JSON) en data/fitness/.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from agents.a2a_log import a2a_log

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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
        "athlete": "user",
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

    dates = _list_session_dates()
    if sd:
        dates = [d for d in dates if d >= sd]
    if ed:
        dates = [d for d in dates if d <= ed]
    dates = list(reversed(dates))  # más recientes primero

    out: list[str] = []
    count = 0
    for d in dates:
        sess = _load_json(_session_path_for(d), default={})
        if not isinstance(sess, dict):
            continue
        if muscle_q or ex_q:
            hits = False
            for ex in (sess.get("exercises") or []):
                if not isinstance(ex, dict):
                    continue
                name = str(ex.get("name", "")).lower()
                muscles = [str(m).lower() for m in (ex.get("muscles") or []) if m]
                if ex_q and ex_q in name:
                    hits = True
                if muscle_q and any(muscle_q in m for m in muscles):
                    hits = True
            if not hits:
                continue

        out.append(f"- {sess.get('date')} | {sess.get('split')} {sess.get('focus')} | notas: {str(sess.get('notes',''))[:120]}")
        count += 1
        if count >= int(limit):
            break

    if not out:
        return "No hay sesiones que coincidan con el filtro."
    return "\n".join(out)


@tool
def fitness_check_prs() -> str:
    """Muestra PRs actuales y sugiere progresión basada en el historial."""
    _ensure_dirs()
    prs = _load_json(_PRS_PATH, default={})
    if not isinstance(prs, dict) or not prs:
        return "No hay PRs registrados aún."

    last_dates = _list_session_dates()
    last_date = last_dates[-1].isoformat() if last_dates else None

    lines: list[str] = ["PRs actuales:"]
    for ex, pr in prs.items():
        if not isinstance(pr, dict):
            continue
        load = pr.get("load")
        unit = pr.get("unit") or ""
        reps = pr.get("reps")
        rir = pr.get("rir")
        d = pr.get("date") or ""
        lines.append(f"- {ex}: {load}{unit}×{reps} @RIR{rir} ({d})")

    lines.append("")
    lines.append("Sugerencias de progresión (heurística):")
    for ex, pr in prs.items():
        if not isinstance(pr, dict):
            continue
        unit = str(pr.get("unit") or "").lower()
        try:
            reps = float(pr.get("reps"))
        except Exception:
            reps = None
        try:
            rir = float(pr.get("rir"))
        except Exception:
            rir = None
        inc = 2.5
        if "lb" in unit:
            inc = 5.0
        elif "kg" in unit or unit == "":
            inc = 2.5
        if reps is not None and reps >= 10:
            inc = 2.0 if "kg" in unit else inc
        if rir is not None and rir <= 2.0:
            lines.append(f"- {ex}: prueba +{inc:g}{pr.get('unit') or ''} la próxima vez (manteniendo RIR~1-2).")
        else:
            lines.append(f"- {ex}: repite carga y busca mejorar reps/técnica antes de subir.")

    if last_date:
        lines.append("")
        lines.append(f"Última sesión registrada: {last_date}")
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


@tool
def fitness_weekly_report(week_ending: str | None = None) -> str:
    """Reporte semanal de volumen, PRs, lesiones, progresiones."""
    _ensure_dirs()
    end = _parse_yyyy_mm_dd(week_ending or "") if week_ending else date.today()
    if not end:
        end = date.today()
    start = end - timedelta(days=6)

    # Sesiones
    dates = [d for d in _list_session_dates() if start <= d <= end]
    sessions: list[dict[str, Any]] = []
    for d in dates:
        s = _load_json(_session_path_for(d), default={})
        if isinstance(s, dict):
            sessions.append(s)

    # Volumen por músculo (sets)
    sets_by_muscle: dict[str, int] = {}
    prs_hit: list[str] = []
    for s in sessions:
        for ex in (s.get("exercises") or []):
            if not isinstance(ex, dict):
                continue
            muscles = ex.get("muscles") or []
            n_sets = len(ex.get("sets") or [])
            for m in muscles:
                key = str(m).strip().lower()
                if not key:
                    continue
                sets_by_muscle[key] = sets_by_muscle.get(key, 0) + n_sets
        for pr in (s.get("prs") or []):
            if isinstance(pr, dict):
                prs_hit.append(f"{pr.get('exercise') or pr.get('name')}: {pr.get('load')}{pr.get('unit','')}×{pr.get('reps')} @RIR{pr.get('rir')}")

    injuries = _load_json(_INJURIES_PATH, default=[])
    if not isinstance(injuries, list):
        injuries = []
    injuries_week = [
        i
        for i in injuries
        if isinstance(i, dict)
        and (d := _parse_yyyy_mm_dd(str(i.get("date", "")))) is not None
        and start <= d <= end
    ]

    lines: list[str] = [
        f"Reporte semanal ({start.isoformat()} → {end.isoformat()}):",
        f"- Sesiones: {len(sessions)}",
    ]
    if sessions:
        lines.append("- Detalle sesiones:")
        for s in sessions:
            lines.append(f"  - {s.get('date')} | {s.get('split')} {s.get('focus')}")

    lines.append("")
    lines.append("Volumen (sets por músculo, según tags en ejercicios):")
    if not sets_by_muscle:
        lines.append("- (Sin datos de músculos/sets; añade 'muscles' en exercises para reportes mejores.)")
    else:
        for m, n in sorted(sets_by_muscle.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {m}: {n} sets")

    lines.append("")
    lines.append("PRs de la semana:")
    lines += [f"- {x}" for x in prs_hit[:60]] if prs_hit else ["- (Ninguno registrado)"]

    lines.append("")
    lines.append("Lesiones/molestias de la semana:")
    if not injuries_week:
        lines.append("- (Sin registros)")
    else:
        for i in injuries_week[-30:]:
            lines.append(
                f"- {i.get('date')} | {i.get('zone')} {i.get('intensity_0_10')}/10 | causa: {i.get('caused_by_exercise') or '-'}"
            )

    lines.append("")
    lines.append("Progresión sugerida:")
    lines.append("- Revisa `fitness_check_prs` y prioriza incrementos pequeños si RIR<=2.")
    lines.append("- Si aparece molestia, reduce rango/volumen y cambia variantes 1-2 semanas.")
    return "\n".join(lines).strip()


def get_fitness_tools():
    return [
        fitness_log_session,
        fitness_get_history,
        fitness_check_prs,
        fitness_next_session,
        fitness_weekly_report,
        fitness_injury_log,
    ]

