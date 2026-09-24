"""
MemoryGate — Filtro de entrada a ChromaDB.

RESPONSABILIDAD: Decidir si un mensaje merece ser guardado en memoria
permanente y con qué tipo, antes de delegarlo al MemoryManager.

QUIÉN LO LLAMA: El Orquestador, después de cada turno de conversación.

Flujo:
    contenido → clasificar con LLM local → ¿es EPHEMERAL? → descartar
                                         → ¿confianza baja? → descartar
                                         → ¿es duplicado? → descartar
                                         → guardar en ChromaDB
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Optional

from agents.a2a_log import a2a_log
from agents.memory.memory_schemas import MemoryCandidate, MemoryType

# Umbral mínimo de confianza para persistir en memoria
CONFIDENCE_THRESHOLD = 0.65

# Umbral de deduplicación semántica (distancia coseno L2)
# < 0.15 significa que el contenido es casi idéntico a algo ya guardado
DEDUP_DISTANCE_THRESHOLD = 0.15


class MemoryGate:
    """
    Filtro inteligente de entrada a ChromaDB.

    Clasifica el contenido usando el LLM local para decidir si vale la pena
    recordarlo permanentemente. Aplica deduplicación semántica antes de guardar.

    Ejemplo:
        gate = MemoryGate(llm, chroma_collection)
        doc_id = gate.evaluate_and_store(
            content="El cliente prefiere respuestas en español",
            context="conversación sobre preferencias de formato"
        )
        # doc_id es None si fue rechazado o un UUID si fue guardado
    """

    def __init__(self, llm, chroma_collection):
        self.llm = llm
        self.collection = chroma_collection

    def evaluate_and_store(self, content: str, context: str = "") -> Optional[str]:
        """
        Pipeline completo: clasificar → deduplicar → guardar.
        Retorna el ID del documento guardado o None si fue rechazado.
        """
        content = content.strip()
        if not content:
            return None

        # PASO 1: Clasificar con LLM local
        candidate = self._classify(content, context)
        a2a_log(
            "memory_gate", "llm", "classify",
            f"type={candidate.memory_type.value} confidence={candidate.confidence:.2f} reason={candidate.reason}"
        )

        # PASO 2: Filtrar por tipo y confianza
        if not candidate.is_worth_storing:
            a2a_log("memory_gate", "chromadb", "rejected",
                    f"EPHEMERAL o confidence baja ({candidate.confidence:.2f}): {content[:80]}")
            return None

        # PASO 3: Deduplicación semántica
        if self._is_duplicate(content):
            a2a_log("memory_gate", "chromadb", "deduplicated",
                    f"Contenido similar ya existe en ChromaDB: {content[:80]}")
            return None

        # PASO 4: Guardar
        doc_id = self._store(candidate)
        a2a_log("memory_gate", "chromadb", "stored",
                f"[{candidate.memory_type.value}] id={doc_id}: {content[:80]}")
        return doc_id

    def _classify(self, content: str, context: str) -> MemoryCandidate:
        """
        Usa el LLM local para clasificar si el contenido merece ser recordado.
        Este es el único lugar donde se decide qué entra a la DB.
        """
        prompt = f"""Clasifica si este fragmento de conversación merece ser guardado en memoria permanente.

CONTEXTO PREVIO: {context[:500]}
FRAGMENTO: {content}

Responde SOLO en JSON con este esquema exacto:
{{
  "memory_type": "fact|preference|decision|event|ephemeral",
  "confidence": 0.0,
  "reason": "string corto explicando la decisión",
  "ttl_days": null
}}

REGLAS:
- "ephemeral" con confidence 0.0: saludos, preguntas de debugging puntual, contenido sin valor de largo plazo.
- "fact": datos verificables que el sistema necesita recordar en futuras sesiones.
- "preference": preferencias del usuario que afectan cómo el sistema debe responder.
- "decision": decisiones arquitectónicas o de negocio tomadas.
- "event": eventos importantes con timestamp que vale la pena registrar.
- confidence >= 0.65 para que se guarde (excepto ephemeral que siempre es 0.0).
"""
        try:
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)])
            raw = getattr(response, "content", str(response))

            # Extraer JSON del texto
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                mem_type_str = data.get("memory_type", "ephemeral")
                try:
                    mem_type = MemoryType(mem_type_str)
                except ValueError:
                    mem_type = MemoryType.EPHEMERAL

                return MemoryCandidate(
                    content=content,
                    memory_type=mem_type,
                    confidence=float(data.get("confidence", 0.0)),
                    reason=data.get("reason", ""),
                    ttl_days=data.get("ttl_days"),
                )
        except Exception as e:  # noqa: BLE001
            a2a_log("memory_gate", "llm", "classify_error", str(e))

        # Fallback conservador: si el LLM falla, no guardar
        return MemoryCandidate(
            content=content,
            memory_type=MemoryType.EPHEMERAL,
            confidence=0.0,
            reason="Error en clasificación LLM — fallback conservador",
        )

    def _is_duplicate(self, content: str) -> bool:
        """
        Deduplicación semántica.
        Rechaza si la distancia coseno (L2) < DEDUP_DISTANCE_THRESHOLD
        (muy similar a algo ya guardado).
        """
        try:
            if self.collection.count() == 0:
                return False

            results = self.collection.query(
                query_texts=[content],
                n_results=1,
            )
            distances = (results.get("distances") or [[]])[0]
            if distances:
                return distances[0] < DEDUP_DISTANCE_THRESHOLD
        except Exception as e:  # noqa: BLE001
            a2a_log("memory_gate", "chromadb", "dedup_error", str(e))
        return False

    def _store(self, candidate: MemoryCandidate) -> str:
        """
        Guarda el candidato en ChromaDB con metadata de tipo y TTL.
        Retorna el doc_id generado.
        """
        from agents.chroma_memory import _utc_now_iso
        item_id = str(uuid.uuid4())[:12]
        cid = f"{candidate.memory_type.value}_{item_id}"

        metadata = {
            "kind": candidate.memory_type.value,
            "item_id": item_id,
            "confidence": candidate.confidence,
            "reason": candidate.reason[:200],
            "created_at": _utc_now_iso(),
        }
        if candidate.ttl_days is not None:
            metadata["ttl_days"] = candidate.ttl_days

        self.collection.add(
            ids=[cid],
            documents=[candidate.content],
            metadatas=[metadata],
        )
        return item_id
