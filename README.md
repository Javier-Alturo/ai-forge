# AI-Forge: Local Multi-Agent System 🤖🧠

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Tests](https://img.shields.io/badge/tests-92%20passed-brightgreen)
![Agents](https://img.shields.io/badge/agents-15%2B-purple)

**AI-Forge** es un sistema orquestador de Inteligencia Artificial ("Agent-to-Agent" o A2A) de ejecución local diseñado con **LangGraph**. Funciona como un "cerebro digital autónomo" que delega tareas a más de 15 sub-agentes ultra-especializados, logrando que el sistema completo actúe de forma orquestada, mantenga memoria a largo plazo, interactúe con el entorno del usuario y hasta sea capaz de auto-programarse nuevas habilidades.

---

## ✨ Características Principales

- **Orquestación Descentralizada (A2A):** Un Orquestador principal evalúa la petición del usuario y enruta el contexto hacia agentes especialistas (Marketing, RAG, File, Github, Memory, MCP, etc.) reduciendo la sobrecarga cognitiva del LLM.
- **Auto-Programación (SkillForge Agent):** AI-Forge no es estático. Si le pides hacer algo que no sabe, el **SkillForge Agent** genera código en Python, lo valida con ASTValidator, crea un backup automático y guarda la herramienta dinámicamente con rollback automático si falla.
- **Second Brain Autónomo (Obsidian Agent):** AI-Forge puede leer tu base de conocimientos (Vault de Obsidian), analizar las notas recientes, cruzarlas con tu progreso de entrenamiento y generar reportes semanales.
- **Model Context Protocol (MCP Agent):** Integración completa con servidores FastMCP en hilos persistentes. Gestiona commits y Pull Requests directamente desde el chat, sorteando los bloqueos del Credential Manager de Windows.
- **Memoria Semántica con MemoryGate:** ChromaDB y LlamaIndex empoderan al sistema para que nunca olvide instrucciones pasadas. El MemoryGate clasifica automáticamente cada turno de conversación antes de persistirlo, evitando ruido en la base de datos.
- **Sandbox de Seguridad de 4 Capas:** Todo el código generado por el LLM pasa por AST Validator → Import Allowlist → Process Runner aislado → Resource Governor antes de ejecutarse. 67 tests automatizados verifican su integridad.
- **Entorno Local (Privacidad al 100%):** Diseñado para correr primariamente en modelos locales (como `qwen2.5:14b`) mediante Ollama. Con ModelRouter y Circuit Breaker para fallback opcional a la nube.
- **Sincronización de WhatsApp (WSP Daily Sync):** Integración automatizada usando Playwright y Ollama local. Lee de forma autónoma el último mensaje de WhatsApp Web (ej. *"hice ejercicio y leí 20 páginas"*), interpreta semánticamente los hábitos diarios completados usando IA local, actualiza la base de datos de hábitos RPG en TaskForge, persiste un log diario en Obsidian y envía un reporte detallado con XP ganada directamente de vuelta al chat.

---

## 🧭 ¿Cómo Decide el Orquestador?

El Orquestador no usa reglas fijas. Evalúa la intención del usuario con el LLM y selecciona dinámicamente qué agente (o cadena de agentes) ejecutar.

### Flujo de una petición completa

```
Usuario escribe prompt
        ↓
   Orquestador (LangGraph ReAct — qwen2.5:14b vía Ollama)
        ↓ evalúa intent con historial completo de sesión
        ├── ¿Tarea de código/ejecución?       → Code Agent → SandboxManager (4 capas)
        ├── ¿Memoria/contexto pasado?         → Memory Agent → ChromaDB
        ├── ¿Búsqueda en documentos/notas?   → RAG Agent → LlamaIndex + Obsidian
        ├── ¿Escritura en Obsidian?           → Obsidian Agent → Vault local
        ├── ¿Operación de GitHub/CI/CD?       → MCP Agent → FastMCP Server (stdio)
        ├── ¿Nueva habilidad solicitada?      → SkillForge Agent → dynamic_tools.py
        ├── ¿Automatización de UI/pantalla?   → Computer Use Agent → llava + PyAutoGUI
        ├── ¿Búsqueda web en tiempo real?     → Web Search Agent → DuckDuckGo
        ├── ¿Leads/clientes/Upwork?          → Marketing Agent → Playwright Scraper
        ├── ¿Email/Calendario Google?        → Email/Calendar Agent → OAuth2
        ├── ¿Redes neuronales PyTorch?       → Neural Network Agent
        ├── ¿Fitness/entrenamiento?          → Fitness Agent → JSON persistente
        └── ¿Tarea compuesta?                → Cadena de agentes en secuencia
        ↓
   MemoryGate evalúa el turno en background (daemon thread)
        ↓ clasifica con LLM: FACT / PREFERENCE / DECISION / EVENT / EPHEMERAL
        ↓ si vale la pena → persiste en ChromaDB (deduplicación semántica)
        ↓
   Resultado consolidado → WebSocket → Dashboard UI
```

### Principios de enrutamiento

- **Contexto limpio por agente:** Ningún sub-agente ve la conversación completa. Solo recibe un sub-prompt específico con su misión exacta.
- **Fallback estructurado:** Si un agente falla, el Orquestador recibe un dict de error estructurado y puede reintentar, reformular, o reportar al usuario limpiamente sin colgarse.
- **Sin ciclos:** El grafo LangGraph es acíclico. Los agentes no se llaman entre sí directamente — todo pasa por el Orquestador.
- **ModelRouter con Circuit Breaker:** Si Ollama falla 3 veces consecutivas, el router puede escalar automáticamente a cloud (deshabilitado por defecto para privacidad).

---

## 🦾 El Ecosistema de Agentes

El Orquestador tiene a su disposición un ejército de especialistas, todos heredando de `AgentBase`:

1. **Memory Agent** — Escribe y lee recuerdos semánticos en ChromaDB con deduplicación.
2. **File Agent** — Navegación de disco, lectura y escritura de archivos en el sistema local.
3. **Github Agent** — Creación de repos, lectura de código remoto, issues y PRs vía PyGitHub.
4. **Obsidian Agent** — Lectura, escritura, búsqueda y notas recientes en tu vault Markdown.
5. **Marketing Agent** — OSINT, scraping de leads en Upwork/Reddit con Playwright y sistema de scoring.
6. **Fitness Agent** — Registro JSON persistente de PRs del gimnasio, historial de lesiones y volumen semanal.
7. **Computer Use Agent** — Visión con `llava`, clics, teclado simulado y automatización de UI vía PyAutoGUI.
8. **Code Agent** — Generación y ejecución de Python en sandbox de 4 capas de seguridad.
9. **RAG Agent** — Búsqueda vectorial sobre PDFs y archivos locales + vault completo de Obsidian.
10. **Neural Network Agent** — Diseña, codifica y entrena modelos PyTorch con métricas persistentes.
11. **MCP Agent** — CI/CD autónomo: commits, push y PRs vía FastMCP con anti-bloqueos para Windows.
12. **SkillForge Agent** — Escribe y persiste nuevas herramientas con backup/rollback automático.
13. **Image Agent** — Generación de imágenes con Stable Diffusion v1.5 (diffusers local).
14. **Voice Agent** — Transcripción de voz en tiempo real con Whisper local.
15. **Calendar / Email Agents** — Gmail y Google Calendar con OAuth2 completo.
16. **Brain Agent** — Analiza notas recientes de Obsidian y genera insights/newsletters semanales.
17. **Web Search Agent** — DuckDuckGo en tiempo real con opción de guardar hallazgos en memoria.

---

## ⚙️ Configuración Completa del Entorno

Copia el archivo de ejemplo y configura según tu entorno:

```bash
cp .env.example .env   # Linux/macOS
copy .env.example .env # Windows
```

### Variables principales

| Variable | Requerida | Descripción | Ejemplo |
|----------|-----------|-------------|---------|
| `OLLAMA_MODEL` | ✅ Sí | Modelo principal de inferencia | `qwen2.5:14b` |
| `OLLAMA_BASE_URL` | ✅ Sí | URL del servidor Ollama local | `http://localhost:11434` |
| `LLM_PROVIDER` | ✅ Sí | Motor LLM: `local` o `cloud` | `local` |
| `OBSIDIAN_VAULT_PATH` | ✅ Para Obsidian/Brain | Ruta absoluta a tu vault | `C:/Users/user/MyVault` |
| `GITHUB_TOKEN` | ✅ Para MCP/GitHub | Personal Access Token | `ghp_xxxxxxxxxxxx` |

### Variables de cloud fallback (opcionales)

| Variable | Requerida | Descripción | Default |
|----------|-----------|-------------|---------|
| `ANTHROPIC_API_KEY` | No | Fallback a Claude si Ollama no disponible | `None` |
| `ANTHROPIC_MODEL` | No | Modelo de Anthropic para fallback | `claude-sonnet-4-20250514` |

### Variables por agente

| Variable | Agente | Requerida | Descripción |
|----------|--------|-----------|-------------|
| `GOOGLE_OAUTH_CREDENTIALS` | Calendar / Email | Solo OAuth | Ruta al JSON de Google Cloud Console |
| `GOOGLE_OAUTH_TOKEN` | Calendar / Email | Auto-generado | Sesión OAuth (se crea en primer uso) |
| `MEMORY_EMBED_MODEL` | Memory / RAG | No | Modelo de embeddings | 
| `RAG_TOP_K` | RAG | No | Resultados máximos RAG | 
| `OLLAMA_VISION_MODEL` | Computer Use | No | Modelo de visión (`llava`) |
| `SD_MODEL_ID` | Image | No | Modelo de Stable Diffusion |
| `IMAGE_OUTPUT_DIR` | Image | No | Carpeta de salida de imágenes |
| `WHISPER_MODEL` | Voice | No | Tamaño del modelo Whisper (`base`) |
| `MCP_SERVERS_CONFIG` | MCP | No | Ruta al JSON de servidores MCP |

---

## 🔧 Diccionario de Tools por Agente

Cada agente expone tools al Orquestador mediante el decorador `@tool` de LangChain. Esta tabla documenta qué puede hacer cada agente y los parámetros exactos verificados contra el código fuente.

### 🧠 Memory Agent (`memory_tools.py`)
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `memory_list_all` | Lista todos los recuerdos indexados en ChromaDB | — |
| `memory_add_reminder` | Crea un recordatorio persistente | `text: str` |
| `memory_add_progress` | Añade nota de progreso o log | `text: str` |
| `memory_delete_reminder` | Elimina recordatorio por ID corto | `item_id: str` |
| `memory_delete_progress` | Elimina entrada de progreso por ID | `item_id: str` |
| `memory_semantic_search` | Búsqueda semántica por embeddings | `query: str, n_results: int = 8` |
| `memory_add_embedding` | Guarda texto con embedding y etiqueta libre | `text: str, kind: str = "note"` |
| `memory_get_context` | Recupera N recuerdos más relevantes (RAG interno) | `query: str, n: int = 6` |

### 📁 File Agent (`file_tools.py`)
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `file_read_file` | Lee un archivo de texto con límite de tamaño | `path: str, max_bytes: int = 500000` |
| `file_write_file` | Escribe o anexa contenido a un archivo | `path: str, content: str, append: bool = False` |
| `file_list_directory` | Lista entradas de un directorio (no recursivo) | `path: str, max_entries: int = 200` |
| `file_move_or_copy` | Mueve o copia archivos/directorios | `source_path: str, destination_path: str, operation: str` |
| `file_search` | Búsqueda recursiva por nombre o contenido | `root_path: str, name_glob: str, content_substring: str` |

### 💻 Code Agent (`code_tools.py`)
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `code_generate_and_execute` | Genera código Python y lo ejecuta en sandbox de 4 capas | `description: str` |
| `code_handoff_to_memory_agent` | Delega en el agente de memoria para guardar resultados | `instruction: str` |

### 🛠️ SkillForge Agent (`skillforge_tools.py`)
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `skillforge_save_tool` | Valida, respalda y guarda nueva tool en `dynamic_tools.py` | `python_code: str` |
| `skillforge_list_history` | Lista el historial de versiones de `dynamic_tools.py` | — |
| `skillforge_rollback` | Revierte al último backup con confirmación explícita | `confirm: str` |

### 🤖 MCP Agent (tools dinámicas vía FastMCP)
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `aiforge_commit_push` | Commit + push al repositorio remoto (anti-bloqueos Windows) | `message: str, branch: str` |
| `aiforge_create_pr` | Crea Pull Request en GitHub vía API | `title: str, body: str, head: str, base: str` |
| `aiforge_get_status` | Estado actual del repositorio Git | — |
| `aiforge_get_diff` | Diff de cambios actuales | — |
| `aiforge_list_branches` | Lista ramas del repositorio | — |
| `aiforge_merge_pr` | Mergea un PR existente | `pr_number: int` |

### 📚 RAG Agent (`rag_tools.py`)
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `rag_index_documents` | Indexa PDFs/TXT/MD en `data/documents/` | — |
| `rag_query` | Consulta RAG sobre documentos indexados | `question: str` |
| `rag_add_document` | Crea y indexa un archivo nuevo | `filename: str, content: str` |
| `rag_list_indexed` | Lista fragmentos indexados en Chroma | `max_rows: int = 50` |
| `rag_index_obsidian_vault` | Indexa todo el vault de Obsidian en Chroma | — |
| `rag_query_obsidian` | Consulta la base de conocimiento de Obsidian | `question: str` |

### 📓 Obsidian Agent (`obsidian_tools.py`)
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `obsidian_read_note` | Lee una nota por título (`.md` opcional) | `title: str` |
| `obsidian_write_note` | Crea o sobrescribe una nota | `title: str, content: str` |
| `obsidian_append_note` | Añade texto al final de una nota existente | `title: str, content: str` |
| `obsidian_search_notes` | Busca texto en todas las notas del vault | `query: str` |
| `obsidian_get_recent_notes` | Notas modificadas en los últimos N días | `days: int = 7` |

### 🌐 Web Search Agent (`web_search_tools.py`)
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `web_search_duckduckgo` | Búsqueda en internet en tiempo real | `query: str` |
| `web_search_save_findings_to_memory` | Delega hallazgos al Memory Agent | `instruction: str` |

---

## 🌅 Morning Briefing Inteligente & Telegram Bot

AI-Forge incluye un sistema autónomo que actúa como tu "segundo cerebro", generando un reporte matutino cada vez que inicias sesión y un asistente conversacional 24/7 vía Telegram.

### 🔄 Morning Briefing (Arranque Automático)
Espera que Ollama + ChromaDB estén libres (máx. 60s)
      │
      ▼
[Paso 0] goal_tracker.py
      │  ← Lee mensajes de Telegram de las últimas 24h
      │  ← Analiza avances en metas con Qwen local
      │  ← Actualiza progress_log y status en data/taskforge/tasks.json
      │  ← Envía reporte de metas actualizadas a Telegram (si hubo cambios)
      │
      ▼
MorningBriefingAgent (LangGraph ReAct)
      │
      ├── 📝 Lee tu Daily Note en Obsidian
      ├── 🎯 Lee tus metas activas actualizadas de TaskForge
      ├── ⏳ Escanea tareas pendientes de los últimos 3 días
      ├── 🌦️ Consulta el clima en Bogotá (OpenWeatherMap)
      ├── 📰 Descarga titulares de HuggingFace, TechCrunch, Papers with Code
      ├── 📅 Revisa eventos de Google Calendar (si está configurado)
      ├── 📧 Filtra correos críticos de Gmail (si está configurado)
      └── 🛡️ Verifica que Ollama, ChromaDB y MCP estén corriendo
      │
      ▼
Genera el Briefing en Markdown
      │
      ├──→ 💾 Guarda en Obsidian: Daily Notes/YYYY-MM-DD-briefing.md
      ├──→ 🌐 Disponible en: http://localhost:8765
      └──→ 📱 Envía resumen compacto a Telegram

### **¿El bot de Telegram lee todos mis mensajes? ¿Cómo funciona?**
> Sí y no. El script `telegram_bot_listener.py` corre en tu PC y se conecta a la API de Telegram. Recibe todos los mensajes que le envías directamente al bot. 
> 
> Está programado para dos cosas:
> 1. **Comandos explícitos:** Si escribes exactamente `/daily` o `/briefing`, genera el briefing de inmediato.
> 2. **Conversación:** Si escribes cualquier otra cosa, reenvía el mensaje al orquestador de LangGraph local para que Qwen te responda de forma conversacional y use sus herramientas en tu PC.
> 
> Adicionalmente, el sistema de **Morning Briefing** revisa todo el historial de chats de las últimas 24 horas antes de ejecutarse por la mañana (usando el módulo `goal_tracker.py`). Analiza con Qwen local si le contaste sobre algún avance en tus metas del día anterior (por ejemplo: *"estudié inglés 2 horas"* o *"mandé 3 propuestas en Upwork"*) y actualiza automáticamente tu base de datos de tareas y XP en `tasks.json`.

---

## 📱 Sincronización Diaria de WhatsApp (WSP Daily Sync)

Permite registrar tus hábitos y tareas diarias enviando un simple mensaje por WhatsApp (ej: *"hice ejercicio y leí 20 páginas"*). La IA procesa y mapea la entrada a tus hábitos estructurados de TaskForge en local.

### 🔄 Flujo de Ejecución

1. **Lectura (Playwright):** Inicia una sesión de navegador persistente (reusando tu sesión de Chrome activa), abre el chat de WhatsApp con tu número registrado y extrae el último mensaje recibido.
2. **Análisis (Ollama Local):** Tu modelo local (ej: `qwen2.5:14b`) interpreta semánticamente el mensaje natural para mapearlo contra los hábitos del sistema.
3. **Actualización (TaskForge RPG):** Registra los hábitos completados, acumula XP y sube niveles si corresponde en la base de datos del juego.
4. **Registro (Obsidian Vault):** Guarda una nota estructurada con el balance y progreso en tu diario/vault.
5. **Reporte (WhatsApp):** Envía un reporte formal interactivo con los hábitos completados y el estado actual de tu personaje RPG de vuelta al chat de WhatsApp.

### 💻 Comandos de Uso y Pruebas

- **Simular análisis (Dry-run / CLI):**
  Prueba la interpretación semántica y registro directo en base de datos sin necesidad de abrir WhatsApp:
  ```bash
  python agents/wsp_daily_sync.py --messages "Hice ejercicio y leí 20 páginas"
  ```

- **Ejecución Completa (WhatsApp + Playwright):**
  Abre la ventana del navegador (reutilizando la sesión de WhatsApp Web iniciada previamente) para leer tu último mensaje y enviar el reporte de vuelta:
  ```bash
  python pruebas/sync_y_enviar_playwright.py
  ```

- **Programar ejecución automática (Cron / Windows Task Scheduler):**
  Instala un script programador en segundo plano para sincronizar todos los días automáticamente:
  ```bash
  python scripts/setup_wsp_cron.py --install
  ```

---

## 🛠️ Stack Tecnológico

| Categoría | Tecnología |
|-----------|-----------|
| Core ReAct | Python 3.10+, LangGraph, LangChain |
| Motor LLM Local | Ollama (`qwen2.5:14b`, `llava`) |
| Motor LLM Cloud | Anthropic Claude (fallback opcional) |
| Vector Database | ChromaDB (persistente, singleton) |
| RAG Engine | LlamaIndex + HuggingFace Embeddings |
| Protocolo Extendido | FastMCP (Model Context Protocol) |
| Dashboard UI | FastAPI + WebSockets |
| Automatización UI | PyAutoGUI + Playwright |
| Seguridad de Código | SandboxManager (AST + Allowlist + ProcessRunner + ResourceGovernor) |
| CI/CD | GitHub Actions + GitHub API |
| Persistencia Extra | JSON (Fitness, Leads), ChromaDB (Memory, RAG) |

---

## 🚀 Instalación y Despliegue

### Requisitos Previos
- Python 3.10+
- [Ollama](https://ollama.com/) instalado y corriendo.

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/Javier-Alturo/ai-forge.git
cd ai-forge

# 2. Entorno virtual
python -m venv .venv
# En Windows:
.venv\Scripts\activate
# En Linux/macOS:
source .venv/bin/activate

# 3. Dependencias
pip install -r requirements.txt

# 4. Descargar los motores de inferencia local
ollama pull qwen2.5:14b
ollama pull llava

# 5. Configurar entorno
cp .env.example .env
# Edita .env con tus rutas y tokens
```

---

## 💻 Uso

Para levantar el Dashboard visual interactivo:

```bash
python dashboard.py
```

Abre tu navegador en `http://localhost:8000`.

*Ejemplos de Prompts:*
- *"Orquestador, usa al agente de Marketing para analizar perfiles de Upwork y genera una propuesta."*
- *"SkillForge, prográmate una herramienta para darme el clima y guárdala."*
- *"Orquestador, usa el MCP Agent para hacer un commit de mis cambios de hoy y sube un Pull Request a main."*
- *"Haz un resumen semanal de mi entrenamiento y notas de Obsidian."*
- *"Busca en mi vault de Obsidian todo lo que escribí sobre arquitectura de agentes."*

---

## 📂 Arquitectura Interna

```text
ai-forge/
├── agents/                       # Nodos del LangGraph
│   ├── agent_base.py             # Clase abstracta principal (AgentBase)
│   ├── orchestrator.py           # Enrutador inteligente + MemoryGate + ModelRouter
│   ├── mcp_agent.py              # Sub-Agente Model Context Protocol
│   ├── skillforge_agent.py       # Módulo de Auto-programación
│   ├── dynamic_tools.py          # Tools autogeneradas por SkillForge (activas)
│   ├── wsp_daily_sync.py         # Motor de sincronización de hábitos vía WhatsApp
│   ├── morning_briefing_agent.py # Generación automática de resumen diario (Obsidian, Calendar, Clima, RSS)
│   ├── morning_briefing_tools.py # Herramientas de extracción para el Morning Briefing
│   └── memory/
│       ├── memory_gate.py        # Clasificador LLM de relevancia de memoria
│       └── memory_schemas.py     # Tipos: FACT/PREFERENCE/DECISION/EVENT/EPHEMERAL
├── core/
│   ├── model_router.py           # Circuit Breaker Local→Cloud
│   └── sandbox/
│       ├── sandbox_manager.py    # Punto de entrada único para código LLM
│       ├── ast_validator.py      # CAPA 1: Análisis AST
│       ├── import_allowlist.py   # CAPA 2: Whitelist de módulos
│       ├── process_runner.py     # CAPA 3: Proceso aislado (CWD + env limpio)
│       └── resource_governor.py  # CAPA 4: CPU/RAM/tiempo
├── docs/
│   ├── architecture.md           # Mapa de puertos y servicios
│   └── failure_modes/
│       ├── code_agent.md         # Matriz de fallos del Code Agent
│       └── skillforge_agent.md   # Sistema de backup/rollback
├── tests/
│   ├── sandbox/
│   │   └── test_ast_validator.py # 46 tests de seguridad (4 grupos)
│   └── test_sandbox.py           # 21 tests de integración
├── data/
│   ├── documents/                # PDFs/TXT para RAG
│   ├── chromadb/                 # Base de datos vectorial persistente
│   └── sandbox_workspace/        # Workspace aislado de ejecución (excluido de git)
├── scripts/
│   ├── goal_tracker.py           # Lee mensajes del bot, analiza avance de metas con Qwen y actualiza tasks.json
│   ├── morning_briefing.py       # Orquestador principal del briefing
│   ├── mcp_aiforge_server.py     # Servidor FastMCP aislado (stdio)
│   ├── morning_briefing_dashboard.py # Dashboard web en puerto 8765
│   ├── setup_morning_briefing.py # Autoconfiguración y registro en Task Scheduler
│   ├── telegram_bot_listener.py  # Bot de Telegram (escucha comandos y conversaciones)
│   ├── register_tasks_admin.ps1  # Registra las tareas en Windows (requiere Admin)
│   └── startup_briefing.bat      # Wrapper de arranque para Windows
├── pruebas/                      # Scripts de validación y testeo
│   └── sync_y_enviar_playwright.py # Orquestador Playwright para WhatsApp Web
├── knowledge/                    # Documentación interna del proyecto
├── agents_config.json            # Config centralizada (timeouts, sandbox, model_router)
├── mcp_servers.json              # Registro de servidores MCP
└── .env.example                  # Plantilla de variables de entorno
```

---

## 🤝 Cómo Agregar un Nuevo Agente

La arquitectura A2A hace que agregar un agente sea predecible. Sigue estos 4 pasos:

### Paso 1: Crear las tools del agente

```python
# agents/mi_agente_tools.py
from langchain_core.tools import tool

@tool
def mi_tool_principal(parametro: str) -> str:
    """
    Descripción clara de qué hace esta tool.
    El LLM del Orquestador usa esta docstring para decidir cuándo llamarla.
    """
    return f"Resultado para: {parametro}"

def get_mi_agente_tools():
    return [mi_tool_principal]
```

### Paso 2: Crear el agente

```python
# agents/mi_agente_agent.py
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from agents.mi_agente_tools import get_mi_agente_tools

def get_mi_agente():
    from langgraph.prebuilt import create_react_agent
    from agents.llm import get_llm
    return create_react_agent(get_llm(), tools=get_mi_agente_tools())
```

### Paso 3: Registrar en el Orquestador

```python
# agents/orchestrator.py — agregar en build_orchestrator_tools()
@tool
def orchestrator_consult_mi_agente(task: str) -> str:
    """Delega en mi nuevo agente especialista."""
    from agents.mi_agente_agent import get_mi_agente
    return _invoke_subagent("mi_agente", get_mi_agente, task)
```

Y añadir en `agents_config.json`:
```json
"mi_agente": { "enabled": true, "timeout_soft_s": 30, "timeout_hard_s": 90 }
```

### Paso 4: Tests y PR

```bash
python -m pytest tests/ -v
git checkout -b feat/mi-agente
git add agents/mi_agente_tools.py agents/mi_agente_agent.py agents/orchestrator.py
git commit -m "feat: Mi Nuevo Agente"
git push origin feat/mi-agente
```

### Reglas del AgentBase

| Método | Estado | Descripción |
|--------|--------|-------------|
| `invoke()` | 🔒 No tocar | Punto de entrada estandarizado con timing y trace_id |
| `_run()` | ✅ Implementar | Lógica principal del agente |
| `name` | ✅ Implementar | Propiedad abstracta — identificador del agente |

---

## 🗺️ Roadmap

### ✅ Completado
- Orquestador principal con LangGraph ReAct y 17 agentes especializados
- Sistema de auto-programación (SkillForge) con backup/rollback automático y validación AST
- Memoria semántica persistente con ChromaDB y MemoryGate (clasificación LLM)
- Integración MCP con GitHub CI/CD (anti-bloqueos Windows)
- Dashboard WebSocket en tiempo real con logs A2A
- SandboxManager con 4 capas de seguridad (67 tests: 46 + 21)
- ModelRouter con Circuit Breaker para fallback Local→Cloud
- Documentación técnica completa (`docs/architecture.md`, `docs/failure_modes/`)
- RAG sobre vault completo de Obsidian
- Sincronización diaria de hábitos y gamificación RPG vía WhatsApp (WSP Daily Sync) con Playwright y Ollama local (Qwen 2.5 14b)
- Morning Briefing Agent con integración de Obsidian, Google Calendar, OpenWeather, Gmail y feeds RSS (Telegram support)

### 🔄 En progreso
- Integración de ModelRouter en todos los AgentBase (actualmente en Orquestador)
- Panel de métricas del MemoryGate en el Dashboard
- Tests de integración end-to-end del Orquestador completo

### 📋 Planeado
- API REST pública para integración con sistemas externos
- Panel de administración de agentes (habilitar/deshabilitar sin reiniciar)
- Soporte multi-vault de Obsidian
- Modo Swarm: sub-agentes del Marketing Agent (Copywriter, Scraper, SEO)
- WSL migration para resolver bloqueos de subprocess en Windows definitivamente
- SkillForge UI: visualizador de herramientas generadas dinámicamente

---

## 📄 Licencia

Este proyecto es Open Source bajo la Licencia MIT.
