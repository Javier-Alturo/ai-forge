# SkillForge Agent — Versionado y Rollback de `dynamic_tools.py`

> Este documento describe el mecanismo de backup automático que protege al sistema
> cuando una herramienta autogenerada corrompe el grafo de LangGraph.

---

## El Problema

`dynamic_tools.py` es el archivo más peligroso del sistema. Se reescribe automáticamente
cada vez que el SkillForge Agent crea una nueva tool. Si la herramienta nueva:
- Tiene un bug que pasa el ASTValidator pero falla en tiempo de importación
- Rompe la firma esperada por LangGraph
- Genera un conflicto de nombres con otras tools

El sistema queda **inoperante** hasta intervención manual del desarrollador.

---

## Solución: Sistema de Backup Automático

El SkillForge realiza un **backup versionado antes de cada escritura**.

```
agents/
├── dynamic_tools.py           ← versión activa actual
└── dynamic_tools_history/     ← backups automáticos
    ├── dynamic_tools_20260429_183012.py
    ├── dynamic_tools_20260430_091547.py
    └── dynamic_tools_20260501_221034.py   ← último backup
```

### Flujo de escritura seguro

```
Usuario pide nueva tool
        │
        ▼
SkillForge genera código Python
        │
        ▼
┌─────────────────────────┐
│ 1. BACKUP automático    │ ← shutil.copy2(current → history/timestamp.py)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ 2. AST Validator        │ ← Bloqueo si sintaxis peligrosa
└────────────┬────────────┘
             │ ✅ Seguro
             ▼
┌─────────────────────────┐
│ 3. Escribir en disco    │ ← append a dynamic_tools.py
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ 4. Intentar reload      │ ← importlib.reload(dynamic_tools)
└────────────┬────────────┘
        ┌────┴────┐
        ✅ OK     ❌ Error
        │         │
        │         ▼
        │  5. ROLLBACK automático
        │     (restaurar último backup)
        │         │
        ▼         ▼
    Éxito      Notificar error al Orquestador
```

---

## Tabla de Versiones

| Campo | Valor |
|-------|-------|
| Archivo activo | `agents/dynamic_tools.py` |
| Directorio de backups | `agents/dynamic_tools_history/` |
| Formato de nombre | `dynamic_tools_YYYYMMDD_HHMMSS.py` |
| Máximo de backups | 20 (los más antiguos se purgan automáticamente) |
| Ignorado por Git | ✅ Sí (ver `.gitignore`) |

---

## Comandos de Operación Manual

```bash
# Ver historial de versiones
ls agents/dynamic_tools_history/ -lt

# Rollback manual a una versión específica
cp agents/dynamic_tools_history/dynamic_tools_20260429_183012.py agents/dynamic_tools.py

# Rollback al último backup
cp $(ls agents/dynamic_tools_history/*.py -t | head -1) agents/dynamic_tools.py

# Ver qué tools hay actualmente
python -c "import agents.dynamic_tools as dt; import inspect, langchain_core; print([n for n,o in inspect.getmembers(dt) if isinstance(o, langchain_core.tools.BaseTool)])"
```

---

## Comportamiento ante cada fallo

| Fallo | Respuesta del SkillForge | El sistema queda operativo? |
|-------|--------------------------|-----------------------------|
| SyntaxError en código generado | Rechazado por ASTValidator. **Nunca** escribe en disco | ✅ Sí |
| ImportError al hacer reload | Rollback automático al último backup | ✅ Sí |
| Conflicto de nombres de tools | Rollback automático | ✅ Sí |
| Backup dir inexistente | Se crea automáticamente (`mkdir -p`) | ✅ Sí |
| Sin backups disponibles | Error descriptivo, **no** rollback | ⚠️ Depende del estado actual |
| dynamic_tools.py corrupto manualmente | Rollback manual desde historial | ✅ Con intervención |

---

## `.gitignore` — Qué se versiona y qué no

```gitignore
# Backups de SkillForge — no versionar (pueden ser cientos)
agents/dynamic_tools_history/

# El archivo activo SÍ se versiona (es parte del estado del sistema)
# agents/dynamic_tools.py  ← NO ignorar
```
