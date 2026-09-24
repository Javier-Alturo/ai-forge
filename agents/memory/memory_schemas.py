"""
Schemas de tipos para el sistema de MemoryGate.
Define qué tipos de memoria existen y cómo se estructura un candidato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MemoryType(Enum):
    FACT = "fact"             # Dato verificable: "El cliente X usa Python 3.11"
    PREFERENCE = "preference" # Preferencia del usuario: "Prefiero respuestas cortas"
    DECISION = "decision"     # Decisión tomada: "Se eligió ChromaDB sobre Pinecone"
    EVENT = "event"           # Evento con timestamp: "Deploy exitoso 2025-04-29"
    EPHEMERAL = "ephemeral"   # No guardar: saludos, preguntas triviales, debug


@dataclass
class MemoryCandidate:
    content: str
    memory_type: MemoryType
    confidence: float          # 0.0 - 1.0
    reason: str = ""           # Explicación de la clasificación
    ttl_days: Optional[int] = None  # None = permanente

    @property
    def is_worth_storing(self) -> bool:
        """True si el candidato supera el umbral mínimo para ser guardado."""
        return (
            self.memory_type != MemoryType.EPHEMERAL
            and self.confidence >= 0.65
        )
