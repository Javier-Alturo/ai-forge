import os
import sys
from pathlib import Path

sys.path.insert(0, ".")

from agents.rag_tools import rag_add_document, rag_query, rag_index_documents


def test_rag_flow():
    # Asegurar que el entorno de testing use un directorio diferente si es posible
    os.environ["CHROMA_DIR"] = "./data/chroma_db_test"
    
    print("Test 1: Indexing simple document...")
    res = rag_add_document.invoke({"filename": "test_rag_doc.txt", "content": "AI-Forge es un orquestador increíble que usa LlamaIndex para RAG con un threshold de 0.3."})
    print(res)
    assert "test_rag_doc.txt" in res or "indexado" in res.lower()
    
    print("Test 2: Querying relevant info...")
    ans = rag_query.invoke({"question": "¿Qué threshold usa AI-Forge para RAG?"})
    print("Respuesta:", ans)
    assert "0.3" in ans
    
    print("Test 3: Querying irrelevant info (Anti-ruido)...")
    ans_irrelevant = rag_query.invoke({"question": "¿Cuál es la capital de Francia?"})
    print("Respuesta a irrelevante:", ans_irrelevant)
    assert "No se encontraron documentos" in ans_irrelevant or "relevantes" in ans_irrelevant

if __name__ == "__main__":
    test_rag_flow()
    print("✅ Todos los tests de RAG pasaron.")
