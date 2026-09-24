"""Tools del agente de marketing: investigación, contenido y ventas (Upwork/LinkedIn).

- Investigación vía DuckDuckGo (ddgs).
- Memoria persistente: ChromaDB (reutiliza agents/chroma_memory.py).
"""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.chroma_memory import add_embedding_note
from agents.llm import get_llm
from agents.web_search import search_web


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_COPY_SYSTEM = """Eres un copywriter B2B enfocado en conseguir clientes.
Escribe en el estilo pedido (LinkedIn/Twitter/Upwork/email), claro, específico y con CTA.
Evita humo: usa claims verificables y ejemplos concretos (n8n, LangGraph, WhatsApp, APIs).
Devuelve SOLO el texto final listo para copiar/pegar."""


@tool
def marketing_research_clients(topic: str, max_results: int = 8, save_strategy_to_memory: bool = True) -> str:
    """
    Busca en internet (DuckDuckGo) estrategias actuales para conseguir clientes
    en nichos de AI automation, n8n, LangGraph, agentes IA.
    """
    q = (topic or "").strip()
    if not q:
        q = "How to get clients AI automation n8n LangGraph agents Upwork LinkedIn 2026 strategies"
    a2a_log("marketing", "duckduckgo", "research_clients", q)
    results = search_web(q, max_results=int(max_results))

    if save_strategy_to_memory:
        llm = get_llm(temperature=0.15)
        prompt = (
            "Resume en 8-12 bullets accionables las mejores estrategias de captación de clientes que "
            "aparezcan en estos resultados. Manténlo general pero práctico para un freelancer que vende "
            "automatización con n8n, agentes con LangGraph, bots WhatsApp e integraciones API. "
            "Incluye 2-3 ideas de posicionamiento/diferenciación.\n\n"
            f"Resultados:\n{results}"
        )
        a2a_log("marketing", "ollama", "synthesize_strategy", q[:120])
        resp = llm.invoke([SystemMessage(content=_COPY_SYSTEM), HumanMessage(content=prompt)])
        summary = getattr(resp, "content", str(resp)).strip()
        mid = add_embedding_note(
            f"[marketing_strategy] {summary}\n\nFuente (query): {q}\nTimestamp: {_utc_now_iso()}",
            kind="marketing_strategy",
        )
        a2a_log("marketing", "chromadb", "save_strategy", f"query={q} id={mid}")
        return f"{results}\n\n---\nEstrategia sintetizada guardada en memoria.\n\n{summary}"

    return results


@tool
def marketing_generate_post(topic: str, platform: str = "LinkedIn", objective: str = "Get leads") -> str:
    """Genera copy para LinkedIn/Twitter sobre un tema de AI automation dado."""
    llm = get_llm(temperature=0.2)
    plat = (platform or "LinkedIn").strip()
    obj = (objective or "Get leads").strip()
    t = (topic or "").strip()
    if not t:
        return "Falta topic."
    a2a_log("marketing", "ollama", "generate_post", f"{plat} | {t[:120]}")
    prompt = (
        f"Plataforma: {plat}\n"
        f"Objetivo: {obj}\n"
        "Contexto del servicio: automatizaciones con n8n, agentes IA con LangGraph, bots WhatsApp, integraciones API. "
        "Diferenciador: sistemas multi-agente A2A, LLMs locales, expertise técnico real.\n\n"
        f"Tema: {t}\n\n"
        "Requisitos:\n"
        "- Hook fuerte en la primera línea.\n"
        "- 3-6 bullets con valor práctico.\n"
        "- 1 mini-caso o ejemplo (aunque sea hipotético y marcado como ejemplo).\n"
        "- CTA simple (DM / comment / Upwork).\n"
        "- Si es Twitter/X, <= 280 caracteres o un mini-hilo de 4-6 tuits.\n"
    )
    resp = llm.invoke([SystemMessage(content=_COPY_SYSTEM), HumanMessage(content=prompt)])
    return getattr(resp, "content", str(resp)).strip()


@tool
def marketing_content_calendar(
    goal: str = "Upwork + LinkedIn lead gen",
    platforms: list[str] | None = None,
    posts_per_week: int = 7,
) -> str:
    """Genera calendario de contenido semanal con temas, plataformas y CTAs."""
    llm = get_llm(temperature=0.2)
    plats = platforms or ["LinkedIn", "X", "Upwork"]
    a2a_log("marketing", "ollama", "content_calendar", f"posts={posts_per_week} plats={plats}")
    prompt = (
        "Crea un calendario semanal (7 días) para conseguir clientes internacionales.\n"
        f"Objetivo: {goal}\n"
        f"Plataformas: {', '.join(plats)}\n"
        f"Posts por semana: {int(posts_per_week)}\n\n"
        "Para cada día devuelve:\n"
        "- Tema\n"
        "- Plataforma\n"
        "- Formato (post/hilo/carrusel/caso de estudio)\n"
        "- Angle (dolor/resultado/proceso/teardown)\n"
        "- CTA\n"
        "- Idea de ejemplo (n8n/LangGraph/WhatsApp/API)\n"
        "Manténlo específico y repetible."
    )
    resp = llm.invoke([SystemMessage(content=_COPY_SYSTEM), HumanMessage(content=prompt)])
    return getattr(resp, "content", str(resp)).strip()


@tool
def marketing_analyze_competitor(query: str = "Upwork AI automation n8n LangGraph freelancer profile") -> str:
    """
    Busca perfiles de freelancers exitosos en Upwork en nicho AI automation y analiza su posicionamiento.
    """
    q = (query or "").strip()
    if not q:
        q = "Upwork AI automation n8n LangGraph freelancer profile top rated"
    a2a_log("marketing", "duckduckgo", "competitor_search", q)
    results = search_web(q, max_results=8)

    llm = get_llm(temperature=0.15)
    prompt = (
        "A partir de estos resultados web, extrae patrones de posicionamiento típicos de freelancers exitosos "
        "en AI automation: títulos, nichos, ofertas, proof, precios, stack, y cómo estructuran su perfil. "
        "Luego sugiere 5 mejoras concretas para el perfil/portafolio del usuario (n8n, LangGraph, WhatsApp bots, APIs, A2A, LLM local).\n\n"
        f"Resultados:\n{results}"
    )
    a2a_log("marketing", "ollama", "competitor_analysis", q[:120])
    resp = llm.invoke([SystemMessage(content=_COPY_SYSTEM), HumanMessage(content=prompt)])
    analysis = getattr(resp, "content", str(resp)).strip()

    mid = add_embedding_note(
        f"[competitor_analysis] {analysis}\n\nFuente (query): {q}\nTimestamp: {_utc_now_iso()}",
        kind="marketing_competitor",
    )
    a2a_log("marketing", "chromadb", "save_competitor_analysis", f"id={mid}")
    return f"{results}\n\n---\n{analysis}\n\n(Análisis guardado en memoria.)"


@tool
def marketing_upwork_proposal(job_description: str, tone: str = "confident, technical, concise") -> str:
    """Genera una propuesta personalizada para Upwork usando contexto del RAG de Obsidian."""
    llm = get_llm(temperature=0.2)
    from agents.rag_tools import rag_query_obsidian
    
    # Intentar obtener contexto de proyectos similares en Obsidian
    a2a_log("marketing", "rag", "query_context", "proyectos automatizacion n8n langgraph casos exito")
    context = rag_query_obsidian.invoke({"question": "Dime mis experiencias previas, casos de éxito y habilidades en n8n, LangGraph y automatización."})
    
    a2a_log("marketing", "ollama", "upwork_proposal", job_description[:140])
    prompt = (
        f"Tone: {tone}\n"
        f"Context from my Obsidian notes: {context}\n\n"
        "You are the freelancer described in the profile. Write a high-converting Upwork proposal for:\n"
        "- n8n / LangGraph / AI agents / WhatsApp / API integrations\n\n"
        "Structure:\n1) Problem recognition (empathy).\n2) 3-step technical plan.\n3) 2 specific questions to start a conversation.\n4) CTA.\n\n"
        f"Job posting:\n{job_description}"
    )
    resp = llm.invoke([SystemMessage(content=_COPY_SYSTEM), HumanMessage(content=prompt)])
    proposal = getattr(resp, "content", str(resp)).strip()
    
    mid = add_embedding_note(
        f"[upwork_proposal] {proposal}\n\nTimestamp: {_utc_now_iso()}",
        kind="marketing_upwork",
    )
    a2a_log("marketing", "chromadb", "save_upwork_proposal", f"id={mid}")
    return proposal

def _score_lead(title: str, description: str) -> int:
    """Usa el LLM para calificar un lead del 1 al 10 según relevancia."""
    llm = get_llm(temperature=0.1)
    prompt = (
        "Rate this job lead from 1 to 10 based on relevance for a developer specializing in: "
        "n8n automation, LangGraph agents, and Python/API integrations. "
        "1 = totally irrelevant, 10 = perfect match.\n"
        "Respond ONLY with the number.\n\n"
        f"Title: {title}\nDescription: {description[:500]}"
    )
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = getattr(resp, "content", str(resp)).strip()
        import re
        match = re.search(r'\d+', text)
        return int(match.group()) if match else 5
    except:
        return 5

@tool
def marketing_cold_outreach(
    prospect: str,
    pain_point: str,
    offer: str = "n8n automation + LangGraph agents + WhatsApp bot integrations",
    channel: str = "email",
) -> str:
    """Genera mensaje de outreach en inglés para potenciales clientes de automatización."""
    p = (prospect or "").strip()
    pp = (pain_point or "").strip()
    if not p or not pp:
        return "Falta prospect o pain_point."
    llm = get_llm(temperature=0.2)
    a2a_log("marketing", "ollama", "cold_outreach", f"{channel} | {p[:80]}")
    prompt = (
        f"Channel: {channel}\n"
        "Write in English. Keep it short (70-140 words). No fluff.\n"
        f"Prospect: {p}\n"
        f"Pain point: {pp}\n"
        f"Offer: {offer}\n\n"
        "Constraints:\n"
        "- Mention a specific automation outcome (time saved / fewer errors / faster response).\n"
        "- 1 proof line (technical credibility: n8n, LangGraph, API integrations, A2A; local LLM option).\n"
        "- 1 clear CTA (15-min call or quick questions).\n"
    )
    resp = llm.invoke([SystemMessage(content=_COPY_SYSTEM), HumanMessage(content=prompt)])
    msg = getattr(resp, "content", str(resp)).strip()
    add_embedding_note(
        f"[cold_outreach] {msg}\n\nProspect: {p}\nTimestamp: {_utc_now_iso()}",
        kind="marketing_outreach",
    )
    return msg


@tool
def marketing_scrape_leads(
    query: str,
    platforms: list[str] = ["Upwork", "Reddit"],
    headless: bool = False,
    min_score: int = 7
) -> str:
    """
    Escrapea leads de Upwork/Reddit usando DuckDuckGo como intermediario (evita Cloudflare).
    Filtra automáticamente usando Scoring con LLM. Solo muestra leads con score >= min_score.
    Guarda los leads aprobados en ChromaDB para aprendizaje futuro (RAG de leads).
    """
    from agents.lead_scraper import scrape_all
    
    q = (query or "AI automation n8n LangGraph").strip()
    a2a_log("marketing", "lead_scraper", "scrape_leads", f"platforms={platforms}")
    
    # Consultar leads similares anteriores en ChromaDB (aprendizaje RAG)
    try:
        from agents.chroma_memory import semantic_search
        past_leads = semantic_search(f"lead {q} automation", top_k=2, kind_filter="marketing_lead")
        past_context = "\n".join([p.get("content", "")[:200] for p in past_leads]) if past_leads else ""
        if past_context:
            a2a_log("marketing", "chromadb", "rag_past_leads", f"Encontré {len(past_leads)} leads previos similares")
    except Exception:
        past_context = ""
    
    leads = scrape_all(q, platforms, headless=headless)
    
    if not leads:
        if past_context:
            return (
                f"No encontré leads nuevos hoy en {platforms}.\n\n"
                f"💾 Leads similares anteriores en memoria:\n{past_context}\n\n"
                "Intenta mañana o amplía el query."
            )
        return f"No encontré leads nuevos hoy en {platforms}. Intenta mañana o amplía el query."
        
    output = []
    
    for lead in leads:
        score = _score_lead(lead['title'], lead['description'])
        
        if score < min_score:
            a2a_log("marketing", "scoring", "discarded", f"Score {score}: {lead['title'][:50]}")
            continue
            
        a2a_log("marketing", "scoring", "accepted", f"Score {score}: {lead['title'][:50]}")
        
        # Guardar el lead aprobado en ChromaDB para RAG futuro
        add_embedding_note(
            f"[marketing_lead] Score:{score} Platform:{lead['platform']}\n"
            f"Title: {lead['title']}\nURL: {lead['url']}\n"
            f"Description: {lead['description'][:300]}\nTimestamp: {_utc_now_iso()}",
            kind="marketing_lead",
        )
        a2a_log("marketing", "chromadb", "save_lead", f"Score {score}: {lead['title'][:40]}")
        
        # Generar propuesta con contexto de leads previos similares
        extra_ctx = f"\n\nLeads similares anteriores para referencia:\n{past_context}" if past_context else ""
        proposal = marketing_upwork_proposal.invoke({
            "job_description": (lead['description'] or lead['title']) + extra_ctx
        })
        
        output.append(
            f"🔥 [SCORE: {score}/10] {lead['title']} [{lead['platform']}]\n"
            f"🔗 URL: {lead['url']}\n"
            f"✍️ PROPUESTA SUGERIDA:\n{proposal}\n"
            f"{'='*50}"
        )
        
    if not output:
        return (
            f"Se encontraron {len(leads)} leads pero ninguno superó el umbral de {min_score}/10.\n"
            f"Prueba bajando el min_score a 5 o usando un query más amplio."
        )
            
    return f"✅ {len(output)} leads encontrados y aprobados:\n\n" + "\n".join(output)


@tool
def marketing_search_past_leads(query: str, top_k: int = 5) -> str:
    """Busca en la memoria de ChromaDB leads de clientes anteriores que ya fueron encontrados y aprobados.
    Útil para recuperar contactos previos o ver qué tipo de trabajo se ha encontrado antes."""
    try:
        from agents.chroma_memory import semantic_search
        a2a_log("marketing", "chromadb", "search_past_leads", query)
        results = semantic_search(query, top_k=top_k, kind_filter="marketing_lead")
        if not results:
            return "No hay leads anteriores guardados en memoria aún. Primero usa marketing_scrape_leads."
        output = []
        for r in results:
            content = r.get("content", "")
            output.append(f"📋 {content[:400]}\n---")
        return f"Leads anteriores encontrados ({len(results)}):\n\n" + "\n".join(output)
    except Exception as e:
        return f"Error buscando leads anteriores: {e}"


def get_marketing_tools():
    return [
        marketing_research_clients,
        marketing_generate_post,
        marketing_content_calendar,
        marketing_analyze_competitor,
        marketing_upwork_proposal,
        marketing_cold_outreach,
        marketing_scrape_leads,
        marketing_search_past_leads,
    ]


