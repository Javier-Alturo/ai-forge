"""Memory Manager.

Punto unico de escritura en la memoria persistente para todos los agentes.
Implementa deduplicacion semántica (evita guardar notas casi idénticas)
y asignación de prioridades.
"""

from __future__ import annotations

from agents.a2a_log import a2a_log
from agents.chroma_memory import _get_collection, _utc_now_iso
import uuid


def write(text: str, kind: str = "note", priority: int = 1) -> str:
    """Guarda un texto en la memoria si no es un duplicado semántico.
    
    Retorna un string descriptivo de la acción tomada (guardado o ignorado).
    """
    text = text.strip()
    if not text:
        return "El texto está vacío."
        
    coll = _get_collection()
    
    # 1. Deduplicación semántica
    if coll.count() > 0:
        q = coll.query(query_texts=[text], n_results=1)
        dists = (q.get("distances") or [[]])[0]
        if dists and len(dists) > 0:
            dist = dists[0]
            # Umbral de similitud (L2 distance). 0.15 significa que son casi idénticos.
            if dist < 0.15:
                meta = (q.get("metadatas") or [[{}]])[0][0]
                item_id = meta.get("item_id", "?")
                a2a_log("memory_manager", "chromadb", "deduplicated", f"Ignorado por similitud ({dist:.3f}) con {item_id}")
                return f"Ignorado (duplicado semántico de la nota {item_id})."

    # 2. Guardado
    item_id = str(uuid.uuid4())[:12]
    cid = f"{kind}_{item_id}"
    
    coll.add(
        ids=[cid],
        documents=[text],
        metadatas=[{
            "kind": kind[:32], 
            "item_id": item_id, 
            "priority": priority,
            "created_at": _utc_now_iso()
        }],
    )
    
    a2a_log("memory_manager", "chromadb", "write", f"[{kind}] id={item_id}")
    return f"Entrada guardada exitosamente con id {item_id} (prioridad={priority})."
