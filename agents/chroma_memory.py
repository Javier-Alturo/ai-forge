"""Memoria persistente con ChromaDB + sentence-transformers (all-MiniLM-L6-v2 por defecto)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = _ROOT / "data"
LEGACY_JSON = _ROOT / "memory_store.json"

from agents.chroma_client import CHROMA_DIR, get_chroma_client  # noqa: E402

_EMBED_MODEL = os.environ.get("MEMORY_EMBED_MODEL", "all-MiniLM-L6-v2")
_COLLECTION_NAME = "memory_items"

_client: Any = None
_collection: Any = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _embedding_function():
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    return SentenceTransformerEmbeddingFunction(model_name=_EMBED_MODEL)


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    _client = get_chroma_client()
    _collection = _client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=_embedding_function(),
    )
    _migrate_legacy_json_if_needed(_collection)
    return _collection


def _migrate_legacy_json_if_needed(coll: Any) -> None:
    if coll.count() > 0:
        return
    if not LEGACY_JSON.exists():
        return
    try:
        data = json.loads(LEGACY_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    for r in data.get("reminders", []):
        iid = str(r.get("id", uuid.uuid4().hex[:8]))
        cid = f"reminder_{iid}"
        ids.append(cid)
        docs.append(str(r.get("text", "")))
        metas.append(
            {
                "kind": "reminder",
                "item_id": iid,
                "created_at": str(r.get("created_at", "")),
            }
        )
    for p in data.get("progress", []):
        iid = str(p.get("id", uuid.uuid4().hex[:8]))
        cid = f"progress_{iid}"
        ids.append(cid)
        docs.append(str(p.get("text", "")))
        metas.append(
            {
                "kind": "progress",
                "item_id": iid,
                "updated_at": str(p.get("updated_at", "")),
            }
        )
    if ids:
        coll.add(ids=ids, documents=docs, metadatas=metas)
    try:
        LEGACY_JSON.rename(LEGACY_JSON.with_suffix(".json.migrated"))
    except OSError:
        pass


def list_memory() -> str:
    coll = _get_collection()
    if coll.count() == 0:
        return "La memoria está vacía."
    res = coll.get(include=["documents", "metadatas"], limit=500)
    reminders: list[str] = []
    progress: list[str] = []
    other: list[str] = []
    for doc, meta in zip(res["documents"], res["metadatas"]):
        m = meta or {}
        kind = m.get("kind", "note")
        iid = m.get("item_id", "?")
        if kind == "reminder":
            reminders.append(f"- [{iid}] {doc} (creado: {m.get('created_at', '')})")
        elif kind == "progress":
            progress.append(f"- [{iid}] {doc} (actualizado: {m.get('updated_at', '')})")
        else:
            other.append(f"- [{iid}] ({kind}) {doc}")
    parts = [
        f"Recordatorios ({len(reminders)}):",
        *reminders[:200],
        "",
        f"Progreso ({len(progress)}):",
        *progress[:200],
    ]
    if other:
        parts += ["", f"Otras entradas ({len(other)}):", *other[:100]]
    return "\n".join(parts).strip()


def add_reminder(text: str) -> str:
    coll = _get_collection()
    rid = str(uuid.uuid4())[:8]
    cid = f"reminder_{rid}"
    coll.add(
        ids=[cid],
        documents=[text.strip()],
        metadatas=[{"kind": "reminder", "item_id": rid, "created_at": _utc_now_iso()}],
    )
    return f"Recordatorio guardado con id {rid}."


def add_progress(text: str) -> str:
    coll = _get_collection()
    pid = str(uuid.uuid4())[:8]
    cid = f"progress_{pid}"
    coll.add(
        ids=[cid],
        documents=[text.strip()],
        metadatas=[{"kind": "progress", "item_id": pid, "updated_at": _utc_now_iso()}],
    )
    return f"Entrada de progreso guardada con id {pid}."


def delete_by_id(kind: str, item_id: str) -> str:
    coll = _get_collection()
    k = "reminder" if kind == "reminder" else "progress"
    res = coll.get(where={"kind": k, "item_id": item_id}, include=[])
    ids = res.get("ids") or []
    if not ids:
        return f"No se encontró ningún elemento con id {item_id} en {k}."
    coll.delete(ids=ids)
    return f"Elemento {item_id} eliminado de {k}."


def semantic_search(query: str, n_results: int = 8) -> str:
    coll = _get_collection()
    if coll.count() == 0:
        return "Memoria vacía."
    q = coll.query(query_texts=[query], n_results=min(n_results, max(1, coll.count())))
    lines: list[str] = []
    docs = q.get("documents", [[]])[0] or []
    metas = q.get("metadatas", [[]])[0] or []
    dists = (q.get("distances") or [[]])[0] or []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else None
        m = meta or {}
        lines.append(
            f"[{m.get('kind', '?')}|id={m.get('item_id', '?')}] {doc}\n  (distancia={dist})"
        )
    return "\n\n".join(lines) if lines else "Sin resultados."


def get_context_for_query(query: str, n: int = 6) -> str:
    """Top-N fragmentos más relevantes como contexto plano."""
    coll = _get_collection()
    if coll.count() == 0:
        return ""
    n = min(max(1, n), coll.count())
    q = coll.query(query_texts=[query], n_results=n)
    docs = q.get("documents", [[]])[0] or []
    metas = q.get("metadatas", [[]])[0] or []
    parts: list[str] = []
    for doc, meta in zip(docs, metas):
        m = meta or {}
        parts.append(f"- ({m.get('kind', '?')}) {doc}")
    return "\n".join(parts)


def add_embedding_note(text: str, kind: str = "note") -> str:
    """Entrada arbitraria con embedding (kind por defecto 'note')."""
    coll = _get_collection()
    rid = str(uuid.uuid4())[:12]
    cid = f"{kind}_{rid}"
    coll.add(
        ids=[cid],
        documents=[text.strip()],
        metadatas=[{"kind": kind[:32], "item_id": rid, "created_at": _utc_now_iso()}],
    )
    return f"Entrada indexada con id {rid} (kind={kind})."
