import sys
import os

sys.path.insert(0, ".")

from agents.brain_agent import get_brain_agent

def test_brain_agent():
    print("Iniciando Brain Agent Test...")
    agent = get_brain_agent()
    # Mocking un usuario pidiendo la síntesis semanal
    res = agent.invoke({"input": "Genera mi resumen semanal leyendo las notas recientes."})
    print("STATUS:", res.status)
    print("DURACIÓN:", res.duration_ms, "ms")
    print("\nRESPUESTA DEL AGENTE:\n")
    print(res.data)
    
if __name__ == "__main__":
    # Aseguramos un vault temporal si no hay uno
    if not os.environ.get("OBSIDIAN_VAULT_PATH"):
        os.environ["OBSIDIAN_VAULT_PATH"] = "./data/obsidian_test_vault"
        os.makedirs("./data/obsidian_test_vault", exist_ok=True)
        # Añadir notas de prueba
        with open("./data/obsidian_test_vault/nota1.md", "w", encoding="utf-8") as f:
            f.write("# Idea de IA\nCreo que los agentes LangGraph son el futuro de la automatización empresarial.")
        with open("./data/obsidian_test_vault/proyecto_x.md", "w", encoding="utf-8") as f:
            f.write("# Proyecto AI-Forge\nEstamos implementando la Fase 8, el Segundo Cerebro automático.")
            
    test_brain_agent()
