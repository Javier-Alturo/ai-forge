"""Tools LangChain del agente de código (generación + ejecución + A2A a memoria)."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.llm import get_llm
from agents.message_utils import extract_final_ai_text
from agents.python_runner import run_python_code

CODE_SYSTEM = """Eres un agente de código. A partir de la petición del usuario, genera UN bloque markdown:

```python
# código aquí
```

Reglas:
- Python 3, solo biblioteca estándar salvo que el usuario pida explícitamente otra dependencia.
- Imprime resultados con print(). Sin input().
- Sé breve y correcto.
"""


def extract_python_block(text: str) -> str | None:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def generate_and_run(user_request: str) -> str:
    """API imperativa (sin tool) para reutilizar desde otros módulos."""
    llm = get_llm(temperature=0.1)
    messages = [
        SystemMessage(content=CODE_SYSTEM),
        HumanMessage(content=user_request),
    ]
    a2a_log("code", "ollama", "invoke_generate", user_request)
    resp = llm.invoke(messages)
    raw = getattr(resp, "content", str(resp))
    code = extract_python_block(raw) or raw.strip()
    if "```" in code:
        code = extract_python_block(raw) or code

    a2a_log("code", "python_runner", "run_generated_script", code[:120])
    execution = run_python_code(code, timeout_sec=45)
    return f"--- Código generado ---\n{code}\n\n--- Ejecución ---\n{execution}"


def build_code_tools():
    @tool
    def code_generate_and_execute(description: str) -> str:
        """Genera código Python a partir de una descripción y lo ejecuta en local. Solo stdlib por defecto."""
        return generate_and_run(description)

    @tool
    def code_handoff_to_memory_agent(instruction: str) -> str:
        """
        Delega en el agente de MEMORIA. instruction: texto en español con la acción deseada
        (p. ej. 'Añade progreso: resultado del script fue ...').
        """
        from agents.memory_agent import get_memory_agent

        a2a_log("code", "memory", "invoke_memory_agent_graph", instruction)
        agent = get_memory_agent()
        result = agent.invoke(
            {"messages": [HumanMessage(content=instruction)]},
            config={"recursion_limit": 20},
        )
        return extract_final_ai_text(result)

    return [code_generate_and_execute, code_handoff_to_memory_agent]
