import os
import sys
import time

sys.path.insert(0, ".")

from agents.memory_manager import write

import uuid
from agents.chroma_memory import list_memory, delete_by_id, semantic_search

def test_deduplication():
    # 1. Guardar una nota original
    print("Testing deduplication...")
    unique_text = f"Nota-{uuid.uuid4()} {uuid.uuid4()} {uuid.uuid4()}"
    res1 = write(unique_text, kind="note")
    print(res1)
    assert "exitosa" in res1 or "guardado" in res1
    
    # 2. Intentar guardar una nota idéntica
    res2 = write(unique_text, kind="note")
    print(res2)
    assert "duplicado" in res2 or "Ignorado" in res2, "Fallo: Deberia haber bloqueado el duplicado"

def test_memory_flow():
    print("Testing full memory flow...")
    # Guardar recordatorio unico para evitar bloqueos por similitud semantica
    unique_text = f"Reminder-{uuid.uuid4()} {uuid.uuid4()} {uuid.uuid4()}"
    res = write(unique_text, kind="reminder")
    print(res)
    assert "exitosa" in res or "guardado" in res
    
    # Listar memoria y buscar
    lst = list_memory()
    print("Listado actual report length:", len(lst))
    # Extraemos el identificador unico de este test para buscarlo en la respuesta
    unique_marker = unique_text.split(" ")[0]
    assert unique_marker in lst
    
    # Busqueda semantica
    search = semantic_search("reminder")
    print("Búsqueda:", search)
    assert "Reminder" in search

if __name__ == "__main__":
    os.environ["CHROMA_DIR"] = "./data/chroma_db_test"
    test_deduplication()
    test_memory_flow()
    print("✅ Todos los tests de memoria pasaron.")
