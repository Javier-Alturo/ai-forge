"""Orquestador principal: grafo LangGraph ReAct que invoca otros agentes como tools (A2A)."""

from __future__ import annotations

from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from agents.a2a_log import a2a_log
from agents.llm import OLLAMA_BASE, OLLAMA_MODEL, get_llm
from agents.message_utils import extract_final_ai_text
from core.model_router import ModelRouter

# Re-export para main.py
__all__ = ["OLLAMA_BASE", "OLLAMA_MODEL", "run_turn", "arun_turn_stream", "get_orchestrator_graph"]

_ORCHESTRATOR: Any = None
# Checkpointer en memoria: mantiene historial de conversación por thread_id durante la sesión.
# Para persistencia entre reinicios, sustituir por SqliteSaver (langgraph-checkpoint-sqlite).
_CHECKPOINTER = MemorySaver()

ORCH_PROMPT = """Eres el ORQUESTADOR principal del sistema multi-agente (A2A con LangGraph).
Responde al usuario en español.

Herramientas internas (cada una invoca un grafo agente independiente):
- orchestrator_consult_web_search_agent: información actual en internet, noticias, verificación externa.
- orchestrator_consult_memory_agent: memoria persistente ChromaDB + embeddings (recordatorios, búsqueda semántica).
- orchestrator_consult_code_agent: código Python general (stdlib por defecto), ejecución local.
- orchestrator_consult_neural_network_agent: diseño de redes, código PyTorch, entrenamiento breve en CPU, métricas.
- orchestrator_consult_fitness_agent: seguimiento de entrenamiento (PPL), PRs, sesiones, molestias, reportes semanales.
- orchestrator_consult_taskforge_agent: sistema de productividad personal del usuario — tareas del dia, metas a largo plazo (ej: ingles B2), habitos diarios, recordatorios, metricas semanales e historial. USAR SIEMPRE para cualquier peticion sobre tareas, metas, habitos, recordatorios o productividad.
- orchestrator_consult_marketing_agent: USAR SIEMPRE para buscar clientes/leads/trabajos/oportunidades en Upwork, Reddit o LinkedIn. También para research, copy, outreach y propuestas. Tiene un scraper real de Playwright y un sistema de Scoring para filtrar leads.
- orchestrator_consult_file_agent: leer/escribir archivos, listar carpetas, mover/copiar, buscar por nombre o contenido.
- orchestrator_consult_email_agent: Gmail (listar, enviar, buscar) con OAuth2.
- orchestrator_consult_calendar_agent: Google Calendar (eventos próximos, crear, borrar, buscar) con OAuth2.
- orchestrator_consult_voice_agent: grabación por micrófono + transcripción Whisper local.
- orchestrator_consult_image_agent: generación de imágenes Stable Diffusion (diffusers, GPU CUDA recomendada).
- orchestrator_consult_computer_use_agent: PyAutoGUI + visión Ollama (llava): screenshot, clic, teclado, mouse, apps.
- orchestrator_consult_github_agent: API GitHub (repos, archivos, issues, PRs) con GITHUB_TOKEN.
- orchestrator_consult_rag_agent: RAG LlamaIndex + Chroma sobre data/documents/.
- orchestrator_consult_obsidian_agent: leer, escribir y buscar notas en el vault local de Obsidian del usuario.
- orchestrator_consult_brain_agent: tu SEGUNDO CEREBRO. Analiza notas recientes de Obsidian y genera insights/newsletters.
- orchestrator_consult_morning_briefing_agent: USAR para generar un reporte diario ("Morning Briefing") consolidado con tareas, clima, calendario, correos y noticias.
- rag_query_obsidian: consulta DIRECTA a la base de conocimiento de Obsidian (notas del proyecto, agentes, documentacion personal). Usala ANTES de delegar si el usuario pregunta sobre el proyecto, como funciona algo, o pide contexto.
- rag_index_obsidian_vault: indexa el vault de Obsidian en Chroma (ejecutar una vez o cuando haya notas nuevas).

Herramientas MCP (Model Context Protocol): si aparecen en tu lista, provienen de servidores MCP externos
conectados por configuracion (suelen llevar prefijo del nombre del servidor, p.ej. demo_echo).
Usalas cuando el usuario pida capacidades que esas tools declaren en su descripcion.

Reglas:
- MEMORIA DE CONVERSACIÓN: Tienes acceso al historial COMPLETO de esta sesión en tu contexto (todos los mensajes anteriores están en tu ventana de contexto). Si el usuario pregunta "¿qué te pregunté antes?", "¿qué dijiste?", "resume la conversación", "recuérdame X" — LEE TU PROPIO HISTORIAL DE MENSAJES y responde directamente. NUNCA uses herramientas para responder sobre la conversación actual.
- Para saludos o preguntas triviales que no requieran datos externos ni ejecucion, responde directamente SIN herramientas.
- Si el usuario pregunta sobre el proyecto AI-Forge, los agentes, herramientas o documentacion, usa PRIMERO rag_query_obsidian para obtener contexto relevante de las notas.
- Si delegas, sintetiza al final la respuesta util; no dejes solo salidas crudas sin contexto.
- Una peticion puede requerir varias herramientas en secuencia si es necesario.
- REGLA CRÍTICA DE ROUTING: Si el usuario pide buscar "clientes", "leads", "trabajos", "oportunidades", "scraping de Upwork", "scraping de Reddit" o cualquier variación → usa SIEMPRE orchestrator_consult_marketing_agent. NUNCA uses orchestrator_consult_web_search_agent para leads de trabajo."""


import time
import concurrent.futures
from agents.registry import get_agent_config
from agents.agent_base import AgentBase

def _invoke_subagent(name: str, getter, task: str) -> str:
    cfg = get_agent_config(name)

    if not cfg.enabled:
        return f"Error: El agente {name} está deshabilitado por configuración."

    start_time = time.time()
    a2a_log("orchestrator", name, "invoke_subgraph", task)
    agent = getter()

    # Fase 4: inyectar el ModelRouter en agentes que hereden de AgentBase
    if isinstance(agent, AgentBase) and getattr(agent, "router", None) is None:
        try:
            agent.router = _get_model_router()
            a2a_log("orchestrator", name, "router_injected", f"router→{name}")
        except Exception:
            pass  # No bloquear si el router falla al inyectarse

    def _run():
        if isinstance(agent, AgentBase):
            # Fase 3: Nueva interfaz estandarizada
            res = agent.invoke({"input": task})
            if res.status == "error":
                raise Exception(res.error)
            return res.data
        else:
            # Legacy: LangGraph create_react_agent dict response
            return agent.invoke(
                {"messages": [HumanMessage(content=task)]},
                config={"recursion_limit": 35},
            )


    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        for attempt in range(1, 3):
            future = executor.submit(_run)
            try:
                result = future.result(timeout=cfg.soft_s)
                break
            except concurrent.futures.TimeoutError:
                a2a_log(name, "orchestrator", "timeout_soft", f"Tardando más de {cfg.soft_s}s, esperando...")
                try:
                    wait_left = max(1, cfg.hard_s - cfg.soft_s)
                    result = future.result(timeout=wait_left)
                    break
                except concurrent.futures.TimeoutError:
                    if attempt < 2:
                        a2a_log(name, "orchestrator", "timeout_hard_retry", f"Intento {attempt} superó {cfg.hard_s}s. Reintentando...")
                        continue
                    a2a_log(name, "orchestrator", "timeout_hard", f"Cancelado tras {cfg.hard_s}s")
                    return f"Error: El agente {name} superó el tiempo máximo de {cfg.hard_s}s y fue cancelado."
                except Exception as e:
                    if attempt < 2:
                        a2a_log(name, "orchestrator", "subgraph_error_retry", f"Intento {attempt} falló: {e}. Reintentando...")
                        continue
                    a2a_log(name, "orchestrator", "subgraph_error", str(e))
                    return f"Error en agente {name}: {e}"
            except Exception as e:
                if attempt < 2:
                    a2a_log(name, "orchestrator", "subgraph_error_retry", f"Intento {attempt} falló: {e}. Reintentando...")
                    continue
                a2a_log(name, "orchestrator", "subgraph_error", str(e))
                return f"Error en agente {name}: {e}"

    duration_ms = int((time.time() - start_time) * 1000)
    
    if isinstance(agent, AgentBase):
        text = str(result)
    else:
        text = extract_final_ai_text(result)
        
    a2a_log(name, "orchestrator", "subgraph_done", f"[{duration_ms}ms] " + (text[:200] if text else "(vacío)"))
    return text or "(El subagente no devolvió texto.)"




def build_orchestrator_tools():
    from agents.calendar_agent import get_calendar_agent
    from agents.code_agent_graph import get_code_agent
    from agents.computer_use_agent import get_computer_use_agent
    from agents.email_agent import get_email_agent
    from agents.file_agent import get_file_agent
    from agents.fitness_agent import get_fitness_agent
    from agents.taskforge_agent import get_taskforge_agent
    from agents.github_agent import get_github_agent
    from agents.image_agent import get_image_agent
    from agents.marketing_agent import get_marketing_agent
    from agents.memory_agent import get_memory_agent
    from agents.neural_network_agent import get_neural_network_agent
    from agents.obsidian_agent import get_obsidian_agent
    from agents.brain_agent import get_brain_agent
    from agents.rag_agent import get_rag_agent
    from agents.voice_agent import get_voice_agent
    from agents.web_search_agent import get_web_search_agent
    from agents.morning_briefing_agent import get_morning_briefing_agent

    # Arrancar daemon de recordatorios WhatsApp (una sola vez por proceso)
    try:
        from agents.reminder_agent import start_reminder_daemon
        start_reminder_daemon()
    except Exception:
        pass  # No bloquear si Playwright no esta disponible

    @tool
    def orchestrator_consult_web_search_agent(task: str) -> str:
        """Delega en el agente de búsqueda web (DuckDuckGo; puede guardar hallazgos en memoria)."""
        return _invoke_subagent("web_search", get_web_search_agent, task)

    @tool
    def orchestrator_consult_memory_agent(task: str) -> str:
        """Delega en el agente de memoria ChromaDB + embeddings (recordatorios, búsqueda semántica)."""
        return _invoke_subagent("memory", get_memory_agent, task)

    @tool
    def orchestrator_consult_code_agent(task: str) -> str:
        """Delega en el agente de código Python (generar y ejecutar; opcional memoria)."""
        return _invoke_subagent("code", get_code_agent, task)

    @tool
    def orchestrator_consult_neural_network_agent(task: str) -> str:
        """Delega en el agente de redes neuronales PyTorch (diseño, código, entrenamiento, guardar métricas en memoria)."""
        return _invoke_subagent("neural_network", get_neural_network_agent, task)

    @tool
    def orchestrator_consult_fitness_agent(task: str) -> str:
        """Delega en el agente de fitness (sesiones, PRs, historial, lesiones, reporte semanal)."""
        return _invoke_subagent("fitness", get_fitness_agent, task)

    @tool
    def orchestrator_consult_taskforge_agent(task: str) -> str:
        """Delega en el agente TaskForge: tareas del dia, metas a largo plazo, habitos, recordatorios por WhatsApp y metricas de productividad."""
        return _invoke_subagent("taskforge", get_taskforge_agent, task)

    @tool
    def orchestrator_consult_marketing_agent(task: str) -> str:
        """Delega en el agente de marketing (buscar clientes/leads reales con scraper, research, contenido, propuestas, outreach)."""
        return _invoke_subagent("marketing", get_marketing_agent, task)

    @tool
    def orchestrator_consult_file_agent(task: str) -> str:
        """Delega en el agente de archivos del sistema (leer, escribir, listar, mover/copiar, buscar)."""
        return _invoke_subagent("file", get_file_agent, task)

    @tool
    def orchestrator_consult_email_agent(task: str) -> str:
        """Delega en el agente de Gmail (OAuth2: credentials.json + token.json)."""
        return _invoke_subagent("email", get_email_agent, task)

    @tool
    def orchestrator_consult_calendar_agent(task: str) -> str:
        """Delega en el agente de Google Calendar (mismas credenciales OAuth que Gmail)."""
        return _invoke_subagent("calendar", get_calendar_agent, task)

    @tool
    def orchestrator_consult_voice_agent(task: str) -> str:
        """Delega en el agente de voz (micrófono + Whisper local)."""
        return _invoke_subagent("voice", get_voice_agent, task)

    @tool
    def orchestrator_consult_image_agent(task: str) -> str:
        """Delega en el agente de imágenes Stable Diffusion (diffusers, CUDA recomendada)."""
        return _invoke_subagent("image", get_image_agent, task)

    @tool
    def orchestrator_consult_computer_use_agent(task: str) -> str:
        """Delega en computer use: captura de pantalla, clic, teclado, mouse, abrir apps (PyAutoGUI + llava)."""
        return _invoke_subagent("computer_use", get_computer_use_agent, task)

    @tool
    def orchestrator_consult_github_agent(task: str) -> str:
        """Delega en GitHub: repos, archivos, issues, PRs (requiere GITHUB_TOKEN)."""
        return _invoke_subagent("github", get_github_agent, task)

    @tool
    def orchestrator_consult_rag_agent(task: str) -> str:
        """Delega en RAG: indexar/consultar documentos en data/documents/ (LlamaIndex + Chroma)."""
        return _invoke_subagent("rag", get_rag_agent, task)

    @tool
    def orchestrator_consult_obsidian_agent(task: str) -> str:
        """Delega en el agente de Obsidian (leer, escribir, añadir, buscar notas Markdown en el vault)."""
        return _invoke_subagent("obsidian", get_obsidian_agent, task)

    @tool
    def orchestrator_consult_brain_agent(task: str) -> str:
        """Delega en el agente Cerebro. Ejecuta revisiones automáticas de notas recientes y genera insights o reportes semanales."""
        return _invoke_subagent("brain", get_brain_agent, task)

    @tool
    def orchestrator_consult_morning_briefing_agent(task: str) -> str:
        """Delega en el agente de Morning Briefing. Genera un reporte completo diario recopilando clima, calendario, correos, noticias RSS, tareas pendientes y contexto de proyectos."""
        return _invoke_subagent("morning_briefing", get_morning_briefing_agent, task)

    @tool
    def orchestrator_consult_skillforge_agent(task: str) -> str:
        """Delega en el agente SkillForge (Creador de Habilidades). Úsalo cuando necesites programar y guardar una nueva herramienta o skill permanente."""
        from agents.skillforge_agent import get_skillforge_agent
        return _invoke_subagent("skillforge", get_skillforge_agent, task)

    @tool
    def orchestrator_consult_mcp_agent(task: str) -> str:
        """Delega en el agente MCP especializado. Úsalo EXCLUSIVAMENTE para interactuar con el control de versiones y repositorios: hacer commits, push, revisar diffs, listar ramas y crear Pull Requests en GitHub. Pásale todos los detalles técnicos exactos (mensajes de commit, nombres de ramas, body del PR) para que el agente MCP invoque sus herramientas nativas."""
        from agents.mcp_agent import get_mcp_agent
        return _invoke_subagent("mcp_agent", get_mcp_agent, task)

    # ─── Herramienta DIRECTA de búsqueda de leads (evita confusión de routing) ───
    @tool
    def find_real_leads(query: str, platforms: str = "Upwork,Reddit", min_score: int = 7) -> str:
        """Busca ofertas de trabajo y clientes REALES usando un scraper. Úsala cuando el usuario pida:
        'buscar leads', 'buscar clientes', 'scraping de Upwork', 'scraping de Reddit',
        'buscar trabajos reales', 'oportunidades de trabajo reales' o similares.
        Devuelve URLs reales con propuestas personalizadas. NO usa DuckDuckGo ni búsqueda web.
        Parámetros: query = términos de búsqueda, platforms = plataformas separadas por coma (Upwork/Reddit/LinkedIn), min_score = calidad mínima del lead (1-10, default 7).
        """
        from agents.marketing_tools import marketing_scrape_leads
        from agents.rag_tools import rag_query_obsidian
        from agents.a2a_log import a2a_log as _log

        plats = [p.strip() for p in platforms.split(",")]
        _log("orchestrator", "lead_scraper", "find_real_leads", f"query={query} platforms={plats} min_score={min_score}")

        result = marketing_scrape_leads.invoke({
            "query": query,
            "platforms": plats,
            "min_score": min_score
        })
        return result

    # Tools directas de RAG sobre Obsidian (sin subagente, mas rapido para consultas de contexto)
    from agents.rag_tools import rag_index_obsidian_vault, rag_query_obsidian  # noqa: PLC0415

    base_tools = [
        orchestrator_consult_web_search_agent,
        orchestrator_consult_memory_agent,
        orchestrator_consult_code_agent,
        orchestrator_consult_neural_network_agent,
        orchestrator_consult_fitness_agent,
        orchestrator_consult_taskforge_agent,
        orchestrator_consult_marketing_agent,
        orchestrator_consult_file_agent,
        orchestrator_consult_email_agent,
        orchestrator_consult_calendar_agent,
        orchestrator_consult_voice_agent,
        orchestrator_consult_image_agent,
        orchestrator_consult_computer_use_agent,
        orchestrator_consult_github_agent,
        orchestrator_consult_rag_agent,
        orchestrator_consult_obsidian_agent,
        orchestrator_consult_brain_agent,
        orchestrator_consult_morning_briefing_agent,
        orchestrator_consult_skillforge_agent,
        orchestrator_consult_mcp_agent,
        find_real_leads,          # <-- Herramienta directa de scraping de leads
        rag_query_obsidian,
        rag_index_obsidian_vault,
    ]

    # Cargar herramientas dinámicas autogeneradas
    try:
        import inspect
        from langchain_core.tools import BaseTool
        import agents.dynamic_tools as dt
        
        # Refrescar el módulo por si se guardaron nuevas herramientas en runtime
        import importlib
        importlib.reload(dt)
        
        dynamic_tools = []
        for name, obj in inspect.getmembers(dt):
            if isinstance(obj, BaseTool):
                dynamic_tools.append(obj)
        
        base_tools.extend(dynamic_tools)
    except Exception as e:
        from agents.a2a_log import a2a_log
        a2a_log("orchestrator", "system", "dynamic_tools_error", f"Error cargando tools dinámicas: {e}")

    return base_tools


# Singleton del ModelRouter — lee configuración de agents_config.json
_MODEL_ROUTER: ModelRouter | None = None

def _get_model_router() -> ModelRouter:
    global _MODEL_ROUTER
    if _MODEL_ROUTER is None:
        try:
            import json
            from pathlib import Path
            cfg_path = Path(__file__).parent.parent / "agents_config.json"
            full_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            _MODEL_ROUTER = ModelRouter.from_config(full_cfg)
            a2a_log("orchestrator", "model_router", "init",
                    f"local={_MODEL_ROUTER.local_model_name} cloud_fallback={_MODEL_ROUTER.allow_cloud}")
        except Exception as e:  # noqa: BLE001
            a2a_log("orchestrator", "model_router", "init_error", str(e))
            _MODEL_ROUTER = ModelRouter({"local_model": OLLAMA_MODEL})
    return _MODEL_ROUTER


def get_orchestrator_graph():
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        base_tools = build_orchestrator_tools()
        router = _get_model_router()
        try:
            llm, reason = router.get_model(prompt_token_count=0)
            if reason:
                a2a_log("orchestrator", "model_router", "fallback", reason.value)
        except RuntimeError:
            # Cloud no disponible o deshabilitado — usar local directamente
            llm = get_llm(temperature=0.12)

        _ORCHESTRATOR = create_react_agent(
            llm,
            tools=base_tools,
            prompt=ORCH_PROMPT,
            name="orchestrator_agent",
            checkpointer=_CHECKPOINTER,
        )
    return _ORCHESTRATOR


import uuid
from langgraph.errors import GraphRecursionError
from agents.logger import set_trace_id

def _run_memory_gate(user_text: str, response_text: str) -> None:
    """Evalúa el turno completo con MemoryGate en background (no bloquea la respuesta)."""
    try:
        from agents.memory.memory_gate import MemoryGate
        from agents.chroma_memory import _get_collection
        llm = get_llm(temperature=0.0)
        collection = _get_collection()
        gate = MemoryGate(llm, collection)
        content = f"Usuario: {user_text}\nAsistente: {response_text}"
        gate.evaluate_and_store(content=content, context=user_text[:300])
    except Exception as e:  # noqa: BLE001
        a2a_log("orchestrator", "memory_gate", "error", str(e))


def run_turn(user_text: str, thread_id: str = "default") -> AIMessage:
    """Un turno de conversación con memoria de hilo (thread_id identifica la sesión)."""
    trace = uuid.uuid4().hex[:8]
    set_trace_id(trace)

    a2a_log("cli", "orchestrator", "user_message", user_text)
    app = get_orchestrator_graph()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
    try:
        final = app.invoke(
            {"messages": [HumanMessage(content=user_text.strip())]},
            config=config,
        )
        text = extract_final_ai_text(final)
        body = text or "(sin respuesta)"
    except GraphRecursionError:
        a2a_log("orchestrator", "cli", "error", "Límite de recursión alcanzado (loops infinitos evitados).")
        body = "Error: Alcanzé el límite máximo de pasos de pensamiento para esta solicitud. Por favor, sé más específico o simplifica tu petición."

    # MemoryGate: evaluar el turno en background sin bloquear la respuesta al usuario
    import threading
    threading.Thread(
        target=_run_memory_gate,
        args=(user_text, body),
        daemon=True
    ).start()

    return AIMessage(content=body)



async def arun_turn_stream(user_text: str, thread_id: str = "default") -> AsyncGenerator[str, None]:
    """Versión streaming async del orquestador. Emite chunks de texto conforme el LLM los genera."""
    trace = uuid.uuid4().hex[:8]
    set_trace_id(trace)

    a2a_log("dashboard", "orchestrator", "stream_message", user_text)
    app = get_orchestrator_graph()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}
    full_response: list[str] = []
    try:
        async for chunk in app.astream(
            {"messages": [HumanMessage(content=user_text.strip())]},
            config=config,
            stream_mode="messages",
        ):
            msg, _metadata = chunk
            content = getattr(msg, "content", None)
            if not content:
                continue
            if isinstance(content, str):
                full_response.append(content)
                yield content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, str):
                        full_response.append(block)
                        yield block
                    elif isinstance(block, dict) and block.get("type") == "text":
                        full_response.append(block["text"])
                        yield block["text"]
    except GraphRecursionError:
        a2a_log("orchestrator", "dashboard", "error", "Límite de recursión alcanzado.")
        yield "\n\nError: Alcanzé el límite máximo de pasos de pensamiento. Intenta de nuevo."

    # MemoryGate: evaluar el turno completo en background después del stream
    if full_response:
        import threading
        threading.Thread(
            target=_run_memory_gate,
            args=(user_text, "".join(full_response)),
            daemon=True
        ).start()

