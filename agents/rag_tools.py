"""RAG sobre documentos locales con LlamaIndex + ChromaDB."""

from __future__ import annotations

import os
from pathlib import Path

from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.chroma_client import CHROMA_DIR, get_chroma_client

_ROOT = Path(os.environ.get("_AI_FORGE_ROOT", str(Path(__file__).resolve().parent.parent)))
DOC_DIR = _ROOT / "data" / "documents"
RAG_COLLECTION = "rag_chunks"
_EMBED = os.environ.get("MEMORY_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
OBSIDIAN_COLLECTION = "obsidian_knowledge"
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", ""))

# Flag para evitar recargar HuggingFaceEmbedding en cada llamada a tool.
# all-MiniLM-L6-v2 pesa ~90 MB y tarda ~4s en cargar; sin cache se cargaria
# una vez por cada tool RAG invocada en la misma sesion.
_settings_initialized: bool = False


def _ensure_dirs() -> None:
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def _rag_vector_store():
    from llama_index.vector_stores.chroma import ChromaVectorStore

    _ensure_dirs()
    client = get_chroma_client()
    coll = client.get_or_create_collection(RAG_COLLECTION)
    return ChromaVectorStore(chroma_collection=coll)


def _settings() -> None:
    """Inicializa LlamaIndex Settings una sola vez por proceso (embed_model + llm)."""
    global _settings_initialized
    if _settings_initialized:
        return

    from llama_index.core import Settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    Settings.embed_model = HuggingFaceEmbedding(model_name=_EMBED)
    Settings.chunk_size = 512
    Settings.chunk_overlap = 64
    
    try:
        from llama_index.llms.ollama import Ollama

        Settings.llm = Ollama(
            model=os.environ.get("OLLAMA_MODEL", "qwen2.5:14b"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            request_timeout=120.0,
        )
    except Exception:  # noqa: BLE001
        pass


    _settings_initialized = True
    a2a_log("rag", "huggingface", "embed_model_loaded", _EMBED)


@tool
def rag_index_documents() -> str:
    """Indexa todos los documentos en data/documents/ (PDF, TXT, MD)."""
    a2a_log("rag", "llamaindex", "index_documents", str(DOC_DIR))
    try:
        from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
    except ImportError as exc:
        return f"LlamaIndex no instalado: {exc}"
    _ensure_dirs()
    if not any(DOC_DIR.iterdir()):
        return "Carpeta data/documents vacía. Añade archivos .pdf, .txt o .md."
    _settings()
    reader = SimpleDirectoryReader(
        input_dir=str(DOC_DIR),
        recursive=True,
        required_exts=[".pdf", ".txt", ".md"],
    )
    docs = reader.load_data()
    if not docs:
        return "No se encontraron documentos con extensiones .pdf, .txt, .md."
    vs = _rag_vector_store()
    ctx = StorageContext.from_defaults(vector_store=vs)
    VectorStoreIndex.from_documents(docs, storage_context=ctx, show_progress=False)
    return f"Indexados {len(docs)} fragmentos/documentos en Chroma colección '{RAG_COLLECTION}'."


@tool
def rag_query(question: str) -> str:
    """Consulta RAG sobre los documentos indexados."""
    a2a_log("rag", "llamaindex", "query", question[:200])
    try:
        from llama_index.core import VectorStoreIndex
        from llama_index.core.postprocessor import SimilarityPostprocessor
    except ImportError as exc:
        return f"LlamaIndex no instalado: {exc}"
    _settings()
    vs = _rag_vector_store()
    try:
        index = VectorStoreIndex.from_vector_store(vs)
        top_k = 6 if len(question.split()) > 10 else 3
        qe = index.as_query_engine(
            similarity_top_k=top_k,
            node_postprocessors=[SimilarityPostprocessor(similarity_cutoff=0.3)]
        )
        resp = qe.query(question)
        if not resp.source_nodes:
            return "No se encontraron documentos lo suficientemente relevantes para responder a tu pregunta."
        return str(resp)
    except Exception as exc:  # noqa: BLE001
        return f"Error RAG (¿colección vacía? ejecuta rag_index_documents): {exc}"



@tool
def rag_add_document(filename: str, content: str) -> str:
    """Crea un archivo bajo data/documents/ y lo indexa (extensión .txt o .md recomendada)."""
    a2a_log("rag", "filesystem", "add_document", filename[:80])
    _ensure_dirs()
    name = Path(filename).name
    if not name.endswith((".txt", ".md")):
        name += ".md"
    path = DOC_DIR / name
    path.write_text(content, encoding="utf-8")
    try:
        from llama_index.core import Document, StorageContext, VectorStoreIndex
    except ImportError as exc:
        return f"Archivo guardado en {path}; error import LlamaIndex: {exc}"
    _settings()
    vs = _rag_vector_store()
    ctx = StorageContext.from_defaults(vector_store=vs)
    doc = Document(text=content, metadata={"file_name": name, "path": str(path)})
    VectorStoreIndex.from_documents([doc], storage_context=ctx, show_progress=False)
    return f"Guardado e indexado: {path}"


@tool
def rag_list_indexed(max_rows: int = 50) -> str:
    """Lista ids/metadatos de fragmentos en la colección RAG de Chroma."""
    a2a_log("rag", "chromadb", "list_indexed", RAG_COLLECTION)
    import chromadb

    _ensure_dirs()
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        coll = client.get_collection(RAG_COLLECTION)
    except Exception as exc:  # noqa: BLE001
        return f"Colección no disponible: {exc}"
    if coll.count() == 0:
        return "(Colección RAG vacía; ejecuta rag_index_documents.)"
    res = coll.get(include=["metadatas"], limit=int(max_rows))
    metas = res.get("metadatas") or []
    ids = res.get("ids") or []
    lines = [f"{i}: id={ids[i]} meta={metas[i]}" for i in range(min(len(ids), len(metas)))]
    return "\n".join(lines)


@tool
def rag_index_obsidian_vault() -> str:
    """Indexa todas las notas Markdown del vault de Obsidian en la coleccion 'obsidian_knowledge' de Chroma."""
    if not OBSIDIAN_VAULT or not OBSIDIAN_VAULT.exists():
        return f"OBSIDIAN_VAULT_PATH no configurado o no existe: '{OBSIDIAN_VAULT}'. Revisa tu .env."
    a2a_log("rag", "llamaindex", "index_obsidian", str(OBSIDIAN_VAULT))
    try:
        from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
        import chromadb
        from llama_index.vector_stores.chroma import ChromaVectorStore
    except ImportError as exc:
        return f"LlamaIndex no instalado: {exc}"
    _ensure_dirs()
    _settings()
    md_files = list(OBSIDIAN_VAULT.rglob("*.md"))
    if not md_files:
        return f"No se encontraron archivos .md en el vault: {OBSIDIAN_VAULT}"
    reader = SimpleDirectoryReader(
        input_dir=str(OBSIDIAN_VAULT),
        recursive=True,
        required_exts=[".md"],
    )
    docs = reader.load_data()
    if not docs:
        return "No se pudieron cargar documentos del vault de Obsidian."
    client = get_chroma_client()
    coll = client.get_or_create_collection(OBSIDIAN_COLLECTION)
    vs = ChromaVectorStore(chroma_collection=coll)
    ctx = StorageContext.from_defaults(vector_store=vs)
    VectorStoreIndex.from_documents(docs, storage_context=ctx, show_progress=False)
    return f"Vault indexado: {len(docs)} notas de Obsidian en coleccion '{OBSIDIAN_COLLECTION}'."


@tool
def rag_query_obsidian(question: str) -> str:
    """Consulta la base de conocimiento del vault de Obsidian (coleccion 'obsidian_knowledge').
    Usa esta herramienta cuando el usuario pregunte sobre el proyecto, los agentes, notas personales
    o cualquier conocimiento documentado en Obsidian."""
    a2a_log("rag", "llamaindex", "query_obsidian", question[:200])
    try:
        from llama_index.core import VectorStoreIndex
        from llama_index.core.postprocessor import SimilarityPostprocessor
        from llama_index.vector_stores.chroma import ChromaVectorStore
    except ImportError:
        return "LlamaIndex no esta instalado. Asegurate de instalarlo con 'pip install llama-index'."

    _ensure_dirs()
    _settings()
    client = get_chroma_client()
    try:
        coll = client.get_collection(OBSIDIAN_COLLECTION)
    except Exception:  # chromadb raises different errors depending on version
        return "El vault de Obsidian no esta indexado aun. Ejecuta primero rag_index_obsidian_vault."
    vs = ChromaVectorStore(chroma_collection=coll)
    try:
        index = VectorStoreIndex.from_vector_store(vs)
        top_k = 6 if len(question.split()) > 10 else 3
        qe = index.as_query_engine(
            similarity_top_k=top_k,
            node_postprocessors=[SimilarityPostprocessor(similarity_cutoff=0.3)]
        )
        resp = qe.query(question)
        if not resp.source_nodes:
            return "No se encontraron notas de Obsidian lo suficientemente relevantes para responder a tu pregunta."
        return str(resp)
    except Exception as exc:
        return f"Error consultando Obsidian RAG: {exc}"


def get_rag_tools():
    return [
        rag_index_documents,
        rag_query,
        rag_add_document,
        rag_list_indexed,
    ]
