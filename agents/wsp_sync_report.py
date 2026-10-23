"""
Reportes de wsp_daily_sync: resumen diario, nota de Obsidian y texto para WhatsApp.

Separado de wsp_daily_sync.py (lectura de mensajes + interpretación con LLM) para
mantener cada módulo por debajo de ~400 líneas.
"""

from __future__ import annotations

import os
from pathlib import Path

from agents.taskforge_tools import _GOALS_FILE, _HABITS_FILE, _load, _now, _today

OBSIDIAN_VAULT = os.getenv("OBSIDIAN_VAULT_PATH", "")
_DONE_ICONS = "\u2705\U0001f525\u23ed\ufe0f "


def _checklist(lines: list[str], mark: str, strip_chars: str, empty: str) -> str:
    """Convierte líneas de hábitos en una lista de tareas Markdown (una por línea)."""
    if not lines:
        return empty
    return "".join(f"- [{mark}] {line.strip().lstrip(strip_chars)}\n" for line in lines)


# ══════════════════════════════════════════════════════════════════════════════
# 4. GENERAR RESUMEN
# ══════════════════════════════════════════════════════════════════════════════

def generate_summary(completed: list[str], pending: list[str], analysis: dict) -> str:
    """Genera un resumen legible del día."""
    goals  = _load(_GOALS_FILE)
    habits = _load(_HABITS_FILE)

    today = _today()
    total_habits = len(habits)
    done_habits  = sum(1 for h in habits if h.get("last_completed") == today)
    completion_pct = (done_habits / total_habits * 100) if total_habits > 0 else 0

    # Resumen de metas
    goals_summary = []
    for g in goals:
        if not g["id"].startswith("w_"):  # Solo metas largas
            goals_summary.append(f"  📌 {g['title']}: {g['progress']:.1f}% | Nivel {g.get('level', 0)} | {g.get('xp', 0)} XP")

    weekly_summary = []
    for g in goals:
        if g["id"].startswith("w_"):  # Solo metas semanales
            weekly_summary.append(f"  📅 {g['title']}: {g['progress']:.1f}%")

    # Rachas top
    top_streaks = sorted(habits, key=lambda h: h.get("streak", 0), reverse=True)[:3]
    streak_lines = [f"  🔥 {h['title']}: {h.get('streak', 0)} días" for h in top_streaks if h.get("streak", 0) > 0]

    summary = f"""╔══════════════════════════════════════╗
║     📊 RESUMEN DIARIO — {today}     ║
╚══════════════════════════════════════╝

✅ COMPLETADO HOY ({done_habits}/{total_habits} hábitos — {completion_pct:.0f}%):
{chr(10).join(completed) if completed else '  (ninguno detectado)'}

⬜ PENDIENTE:
{chr(10).join(pending) if pending else '  ¡Todo completado! 🎉'}

🎯 PROGRESO DE METAS:
{chr(10).join(goals_summary) if goals_summary else '  (sin metas)'}

📅 METAS SEMANALES:
{chr(10).join(weekly_summary) if weekly_summary else '  (sin metas semanales)'}
"""

    if streak_lines:
        summary += f"\n🔥 RACHAS ACTIVAS:\n{chr(10).join(streak_lines)}\n"

    if analysis.get("raw_metrics", {}).get("notas_adicionales"):
        summary += f"\n📝 MÉTRICAS EXTRA:\n  {analysis['raw_metrics']['notas_adicionales']}\n"

    notes = analysis.get("interpretation_notes", "")
    if notes:
        summary += f"\n🤖 Interpretación IA: {notes}\n"

    summary += f"\n⏱️  Sincronizado: {_now()}"
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# 5. GUARDAR EN OBSIDIAN
# ══════════════════════════════════════════════════════════════════════════════

def save_to_obsidian(summary: str, completed: list[str], pending: list[str], analysis: dict) -> str:
    """Guarda el resumen del día en Obsidian."""
    if not OBSIDIAN_VAULT:
        return "⚠️  OBSIDIAN_VAULT_PATH no configurado — resumen no guardado"

    vault = Path(OBSIDIAN_VAULT)
    if not vault.exists():
        return f"⚠️  Vault no encontrado en: {OBSIDIAN_VAULT}"

    today = _today()
    # Carpeta: Diario/<año>/<mes>/
    folder = vault / "Diario" / today[:4] / today[5:7]
    folder.mkdir(parents=True, exist_ok=True)

    note_path = folder / f"{today} — Resumen Diario.md"

    habits = _load(_HABITS_FILE)
    goals  = _load(_GOALS_FILE)

    completed_md = _checklist(completed, "x", _DONE_ICONS, "- [ ] (ninguno detectado)\n")
    pending_md = _checklist(pending, " ", "⬜ ", "- [x] ¡Todo completado! 🎉\n")

    # Formato enriquecido para Obsidian con frontmatter YAML
    content = f"""---
date: {today}
tags: [diario, taskforge, habitos, resumen]
completados: {sum(1 for h in habits if h.get('last_completed') == today)}
total_habitos: {len(habits)}
---

# 📊 Resumen Diario — {today}

## ✅ Hábitos Completados
{completed_md}
## ⬜ Hábitos Pendientes
{pending_md}
## 🎯 Progreso de Metas
"""
    for g in goals:
        content += f"- **{g['title']}**: {g['progress']:.1f}% | Nivel {g.get('level', 0)} | {g.get('xp', 0)} XP\n"

    content += "\n## 🤖 Análisis IA\n"
    content += f"- **Confianza**: {analysis.get('confidence', 'N/A')}\n"
    content += f"- **Notas**: {analysis.get('interpretation_notes', 'N/A')}\n"

    if analysis.get("raw_metrics", {}).get("notas_adicionales"):
        content += f"\n## 📝 Métricas Extra\n{analysis['raw_metrics']['notas_adicionales']}\n"

    content += f"\n---\n*Generado automáticamente por wsp_daily_sync — {_now()}*\n"

    note_path.write_text(content, encoding="utf-8")
    return f"✅ Resumen guardado en Obsidian: {note_path}"


def build_wsp_summary(summary: str) -> str:
    """Convierte el resumen detallado a un formato amigable para WhatsApp."""
    # WhatsApp no tiene markdown, usar emojis y texto plano
    return summary.replace("╔", "").replace("╚", "").replace("╗", "").replace("╝", "").replace("║", "").replace("═", "").strip()
