# Code Agent — Failure Modes y Comportamiento Esperado

> Este documento describe el comportamiento del sistema ante cada tipo de fallo del Code Agent.
> Es la guía de referencia para debugging, demos con clientes y onboarding de nuevos desarrolladores.

---

## Matriz de Fallos

| Escenario | Detectado en | Respuesta del sistema | El Orquestador continúa? |
|-----------|-------------|-----------------------|--------------------------|
| Código con imports prohibidos | AST - Capa 1 | `blocked: true`, retorna `violations[]` | ✅ Sí, recibe error estructurado |
| Código con llamadas peligrosas (os.system, subprocess) | AST - Capa 1 | `blocked: true`, retorna `violations[]` | ✅ Sí |
| Acceso a dunders peligrosos (`__subclasses__`, `__globals__`) | AST - Capa 1 | `blocked: true`, retorna `violations[]` | ✅ Sí |
| SyntaxError en código generado | AST - Capa 1 | `blocked: true`, retorna `SyntaxError` | ✅ Sí |
| Loop infinito / fork bomb | Runner - Capa 3 + Resource Gov. | Killed por `timeout=30s`, retorna `TIMEOUT` | ✅ Sí, recibe timeout message |
| Consumo excesivo de RAM | Resource Governor - Capa 4 | `MemoryError`, proceso killed (Linux/macOS) | ✅ Sí |
| Error de runtime legítimo (`ZeroDivisionError`, etc.) | Runner - Capa 3 | Capturado vía try/except, retorna `stderr` | ✅ Sí |
| LLM local no genera código parseable | Code Agent | Retry x1, luego retorna `generation_failed` | ✅ Sí |
| Workspace en disco lleno | ProcessRunner | `FileError`, retorna mensaje descriptivo | ✅ Sí |
| Ollama caído durante generación | ModelRouter | Circuit breaker opens, escala a cloud o falla limpio | ✅ Sí |

---

## Comportamiento del Orquestador ante cada fallo

### Si el Sandbox bloquea el código (`blocked: true`)

```
Orquestador recibe → { blocked: true, violations: ["Llamada prohibida: os.system()"] }
Acción: Reformular el sub-prompt al Code Agent excluyendo las operaciones bloqueadas.
Límite: Máximo 2 reintentos automáticos.
Mensaje al usuario: "No pude completar la tarea con las restricciones de seguridad actuales. Las operaciones de sistema no están permitidas."
```

### Si hay timeout

```
Orquestador recibe → { success: false, stderr: "TIMEOUT: El código excedió 30s de ejecución." }
Acción: Reportar al usuario + sugerir dividir la tarea en pasos más pequeños.
NO reintentar automáticamente — el timeout puede ser intencional (loop infinito generado).
```

### Si el LLM no genera código parseable

```
Code Agent detecta → respuesta no contiene bloque ```python``` válido
Acción: Retry con prompt más específico (máximo 1 vez).
Si persiste: Retornar al Orquestador con { status: "error", data: "" }
```

### Si hay error de runtime legítimo

```
ProcessRunner captura → ZeroDivisionError, NameError, TypeError, etc.
Retorna → { success: false, returncode: 1, stderr: "RUNTIME_ERROR: ZeroDivisionError: division by zero" }
El Orquestador puede ofrecer: debugear el código automáticamente con una segunda llamada.
```

---

## Diagrama de flujo de seguridad

```
Código LLM generado
        │
        ▼
┌───────────────────────┐
│  CAPA 1: AST Validator│ ──── ¿imports baneados?
│  (core/sandbox/ast.py)│ ──── ¿llamadas peligrosas?
│                       │ ──── ¿dunders prohibidos?
└───────────┬───────────┘
            │ ✅ Pasa
            ▼
┌───────────────────────┐
│  CAPA 2: Allowlist    │ ──── ¿import en whitelist?
│  (import_allowlist.py)│
└───────────┬───────────┘
            │ ✅ Pasa
            ▼
┌───────────────────────────────────────┐
│  CAPA 3: ProcessRunner                │
│  - CWD = sandbox_workspace/           │ ──── ¿timeout?
│  - Env limpio (sin tokens)            │ ──── ¿returncode != 0?
│  - Archivo temporal → ejecución → del │
└───────────┬───────────────────────────┘
            │
            ▼
┌───────────────────────┐
│  CAPA 4: Resource Gov.│ ──── max_cpu=30s
│  (Linux/macOS)        │ ──── max_mem=512MB
│  (Windows: timeout)   │ ──── no fork
└───────────────────────┘
            │
            ▼
      { stdout, stderr, returncode, success }
              │
              ▼
      Orquestador recibe resultado estructurado
```

---

## Lo que el Sandbox NO puede detectar (limitaciones conocidas)

1. **Ofuscación por concatenación:** `"os" + ".system"` pasa el AST como string, pero el código dentro del ProcessRunner no tiene acceso real al sistema de archivos del usuario.

2. **Lógica maliciosa semánticamente válida:** Código que borra archivos dentro del workspace usando `pathlib.unlink()`. **Mitigación:** el workspace es un directorio temporal aislado creado en `data/sandbox_workspace/`.

3. **Consumo excesivo de CPU sin fork:** `while True: x += 1` pasa el AST pero el timeout de 30s del ProcessRunner lo mata.

4. **Requests a servicios internos:** Si `requests` está en allowlist, el código puede hacer HTTP a `localhost`. **Mitigación pendiente:** considerar proxy o deshabilitar requests por defecto en el config.

---

## Principio de Degradación Elegante

> **El Code Agent nunca crashea el servidor principal (`dashboard.py`).**

Todo fallo retorna un dict estructurado:
```python
{
    "success": bool,
    "blocked": bool,
    "stdout": str,
    "stderr": str,
    "returncode": int,
    "requester": str,
    "message": str  # resumen legible para el LLM y para el usuario
}
```

El Orquestador siempre puede continuar la conversación aunque el Code Agent falle.
