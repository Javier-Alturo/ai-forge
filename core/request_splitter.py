"""Split a request that asks for several independent things.

The local model handles one tool per turn well, but when a message needs two or three agents it
often skips one, claims an action it never ran, or garbles the parallel calls. So a request with
several independent tasks is split here and each task is answered as its own turn.

A request is only sent to the splitter model when it looks like a list (a conjunction, a comma, a
numbered item), so plain requests pay nothing. AIFORGE_SPLIT_REQUESTS=0 turns it off.
"""

from __future__ import annotations

import json
import logging
import os
import re

from langchain_core.messages import HumanMessage, SystemMessage

log = logging.getLogger("ai_forge.request_splitter")

MAX_PARTS = 4
_LOOKS_LIKE_A_LIST = re.compile(r"\by\b|\be\b|,|;|\badem[aá]s\b|\btambi[eé]n\b|\bluego\b|\d\s*[).]", re.IGNORECASE)
_JSON_LIST = re.compile(r"\[.*\]", re.DOTALL)

SPLIT_PROMPT = """Divide la petición del usuario en tareas INDEPENDIENTES. Responde solo con una lista JSON de textos.

Reglas:
- Una tarea es algo que se puede hacer sin conocer el resultado de las otras.
- Si la petición es una sola tarea, devuelve una lista con un único elemento: la petición tal cual.
- NO separes los pasos de una misma tarea, ni una tarea que usa el resultado de otra: eso es UNA tarea.
- Si una parte necesita lo que produce la otra ("y pruébalo", "y dime qué ves", "y entrénalo", "en ella", "y resúmelo"), es UNA tarea.
- Varias cosas del mismo tipo para la misma herramienta ("correos de Ana y de Luis") son UNA tarea.
- Cada tarea debe entenderse sola: repite el contexto que haga falta. No inventes tareas ni cambies datos.

Ejemplos:
"Calcula el factorial de 10 y busca en internet qué es Rust" -> ["Calcula el factorial de 10", "Busca en internet qué es Rust"]
"¿Qué eventos tengo mañana y tengo correos nuevos?" -> ["¿Qué eventos tengo mañana?", "¿Tengo correos nuevos?"]
"Agrega la tarea de pagar la luz, anota que corrí 5 km y dime el estado de git" -> ["Agrega la tarea de pagar la luz", "Anota que corrí 5 km", "Dime el estado de git"]
"Escribe un script que lea un archivo y cuente las palabras" -> ["Escribe un script que lea un archivo y cuente las palabras"]
"Busca en internet el precio del oro y guárdalo en una nota" -> ["Busca en internet el precio del oro y guárdalo en una nota"]
"Busca correos de Ana y de Luis" -> ["Busca correos de Ana y de Luis"]
"Resume mis notas de ayer y de hoy" -> ["Resume mis notas de ayer y de hoy"]
"Toma una foto con la cámara y descríbela" -> ["Toma una foto con la cámara y descríbela"]
"Crea una carpeta nueva y mueve el informe a ella" -> ["Crea una carpeta nueva y mueve el informe a ella"]
"Diseña un modelo en PyTorch y entrénalo" -> ["Diseña un modelo en PyTorch y entrénalo"]
"Escribe una función y pruébala con un ejemplo" -> ["Escribe una función y pruébala con un ejemplo"]
"Hola, ¿cómo estás y qué puedes hacer?" -> ["Hola, ¿cómo estás y qué puedes hacer?"]"""


def splitting_enabled() -> bool:
    return os.environ.get("AIFORGE_SPLIT_REQUESTS", "1").strip().lower() not in ("0", "false", "no", "off")


def looks_like_a_list(text: str) -> bool:
    return bool(_LOOKS_LIKE_A_LIST.search(text))


def parse_parts(reply: str, original: str) -> list[str]:
    """The model's JSON list, or [original] if it is not a usable split."""
    match = _JSON_LIST.search(reply)
    try:
        parts = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        parts = None
    if not isinstance(parts, list) or not all(isinstance(p, str) and p.strip() for p in parts):
        return [original]
    parts = [p.strip() for p in parts]
    return parts if 1 < len(parts) <= MAX_PARTS else [original]


def split_request(llm, text: str) -> list[str]:
    """Independent tasks in `text`; [text] when it is one task, splitting is off or anything fails."""
    if not splitting_enabled() or not looks_like_a_list(text):
        return [text]
    try:
        reply = llm.invoke(
            [SystemMessage(content=SPLIT_PROMPT), HumanMessage(content=text)],
            config={"metadata": {"subagent": "request_splitter"}, "run_name": "request_splitter"},
        )
    except Exception:  # a broken splitter must not cost the user their answer
        log.exception("Request splitter failed; handling the request as one task")
        return [text]
    parts = parse_parts(str(reply.content), text)
    if len(parts) > 1:
        log.info("Request split into %d tasks", len(parts))
    return parts
