import uuid
import sys

sys.path.insert(0, ".")

from agents.orchestrator import _invoke_subagent, build_orchestrator_tools


def test_orchestrator_subagents():
    # El test verifica que la interfaz AgentBase funciona a nivel del orquestador
    # Usaremos el file_agent como prueba, ya que no hace LLM calls intensivos si le damos un comando de "ls"
    print("Test 1: Invoke subagent con AgentBase interface...")
    
    tools = build_orchestrator_tools()
    # Find file agent tool
    file_tool = next((t for t in tools if t.name == "orchestrator_consult_file_agent"), None)
    assert file_tool is not None, "Tool no encontrada"
    
    # We invoke it with a safe command (listar directorio actual)
    res = file_tool.invoke({"task": "lista los archivos en ./"})
    print("Respuesta de la tool:", res)
    assert len(res) > 0

if __name__ == "__main__":
    test_orchestrator_subagents()
    print("✅ Todos los tests del Orquestador pasaron.")
