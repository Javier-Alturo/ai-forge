# AI-Forge — Arquitectura del Sistema y Mapa de Servicios

## Mapa de Puertos y Servicios

| Servicio | Puerto | Protocolo | Accesible desde | Configurable en |
|----------|--------|-----------|-----------------|-----------------|
| FastAPI Dashboard | 8000 | HTTP / WebSocket | localhost (navegador) | `dashboard.py` |
| Ollama (LLM local) | 11434 | HTTP REST | localhost only | `.env` → `OLLAMA_BASE_URL` |
| ChromaDB | En proceso | Embedding API | Interno (Python) | `agents/chroma_memory.py` |
| MCP Server (SkillForge) | stdio | STDIO | Interno (subprocess) | `mcp_servers.json` |
| GitHub API | 443 | HTTPS | Internet | `.env` → `GITHUB_TOKEN` |
| Google OAuth (Gmail/Calendar) | 443 | HTTPS | Internet | `credentials.json` |

> **Nota de seguridad:** Ningún servicio expone puertos externos. Todo el sistema está diseñado para correr 100% local salvo las llamadas explícitas a APIs externas (GitHub, Google).

---

## Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────┐
│                     USUARIO (Navegador)                          │
│                    http://localhost:8000                          │
└─────────────────────────────┬───────────────────────────────────┘
                              │ WebSocket (ws://)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              FastAPI Dashboard (dashboard.py)                     │
│              Puerto: 8000 | Protocolo: HTTP + WS                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Python function call
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Orquestador (LangGraph ReAct)                        │
│              Motor: qwen2.5:14b vía Ollama:11434                 │
│              Memoria: MemorySaver (en proceso)                    │
│              ModelRouter: Circuit Breaker (local → cloud)        │
└──┬──────────┬─────────┬──────────┬──────────┬───────────────────┘
   │          │         │          │          │
   ▼          ▼         ▼          ▼          ▼
[Memory]  [Code/    [Marketing] [MCP      [SkillForge]
[RAG]     [SkillFg]  [Fitness]  [Agent]   [dynamic_tools.py]
   │          │                    │
   ▼          ▼                    ▼
[ChromaDB] [SandboxMgr]        [FastMCP Server]
[LlamaIdx]  4 capas              stdio://
                                 → GitHub API :443
```

---

## Estructura de Archivos Clave

```
ai-forge/
├── core/
│   ├── model_router.py          ← Circuit Breaker Local→Cloud
│   └── sandbox/
│       ├── ast_validator.py     ← CAPA 1: Análisis estático
│       ├── import_allowlist.py  ← CAPA 2: Whitelist de módulos
│       ├── process_runner.py    ← CAPA 3: Proceso aislado
│       ├── resource_governor.py ← CAPA 4: CPU/RAM limits
│       └── sandbox_manager.py  ← Punto de entrada único
├── agents/
│   ├── orchestrator.py          ← Hub central + MemoryGate
│   ├── memory/
│   │   ├── memory_gate.py       ← Clasificador LLM de memoria
│   │   └── memory_schemas.py    ← Tipos: FACT/PREFERENCE/EVENT/...
│   ├── skillforge_tools.py      ← Auto-programación + Backup/Rollback
│   ├── dynamic_tools.py         ← Tools autogeneradas (activas)
│   ├── dynamic_tools_history/   ← Backups automáticos (no en git)
│   └── mcp_agent.py             ← Sub-agente CI/CD
├── scripts/
│   └── mcp_aiforge_server.py    ← Servidor FastMCP (stdio)
├── docs/
│   ├── architecture.md          ← Este archivo
│   └── failure_modes/
│       ├── code_agent.md        ← Matriz de fallos del Code Agent
│       └── skillforge_agent.md  ← Sistema de backup/rollback
├── tests/
│   ├── sandbox/
│   │   └── test_ast_validator.py ← 40+ tests de seguridad
│   └── test_sandbox.py           ← Tests de integración original
└── agents_config.json            ← Config centralizada (timeouts, model_router, sandbox)
```

---

## Variables de Entorno Requeridas

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `OLLAMA_MODEL` | ✅ | Modelo local (ej: `qwen2.5:14b`) |
| `OLLAMA_BASE_URL` | ✅ | URL de Ollama (default: `http://localhost:11434`) |
| `GITHUB_TOKEN` | ✅ Para CI/CD | Personal Access Token para MCP Agent y GitHub Actions |
| `OBSIDIAN_VAULT_PATH` | ✅ Para Brain Agent | Ruta absoluta al vault de Obsidian |
| `MCP_SERVERS_CONFIG` | Opcional | Ruta a `mcp_servers.json` |
| `ANTHROPIC_API_KEY` | Solo si cloud fallback | Requerida si `allow_cloud_fallback: true` |
| `GOOGLE_OAUTH_CREDENTIALS` | Solo Gmail/Calendar | Ruta a credentials.json de Google |
