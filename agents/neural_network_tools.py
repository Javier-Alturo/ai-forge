"""Tools del agente de redes neuronales (PyTorch + A2A a memoria)."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from agents.a2a_log import a2a_log
from agents.llm import get_llm
from agents.message_utils import extract_final_ai_text
from agents.python_runner import run_python_code

DESIGN_SYS = """Eres un arquitecto de deep learning. Diseña una arquitectura PyTorch adecuada al objetivo.
Incluye: capas sugeridas, activaciones, función de pérdida, optimizador y tamaño aproximado.
Responde en español, formato claro con secciones breves. Sin código a menos que sea un pseudocódigo corto."""

TRAIN_CODE_SYS = """Genera UN único script Python completo en un bloque markdown ```python ... ``` que:
- Use PyTorch (import torch, torch.nn, etc.).
- Use CPU (device = torch.device('cpu')).
- Datos sintéticos: tensores aleatorios reproducibles (torch.manual_seed(42)).
- Red pequeña (p.ej. MLP 32->16->1 o similar) y tarea de regresión MSE.
- Entrene como máximo 5 épocas, batch razonable, imprime pérdida media por época.
- Sin input(), sin descargar datasets externos, sin red/GPU.
- Al final imprime una línea METRICS: loss_final=... epochs=...
"""


def _extract_python(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip()


def _nn_design_impl(user_goal: str) -> str:
    a2a_log("neural_network", "ollama", "nn_design_architecture", user_goal[:240])
    llm = get_llm(temperature=0.2)
    out = llm.invoke(
        [
            SystemMessage(content=DESIGN_SYS),
            HumanMessage(content=user_goal),
        ]
    )
    return str(getattr(out, "content", out) or "").strip()


def _nn_generate_impl(architecture_summary: str, extra_constraints: str = "") -> str:
    a2a_log("neural_network", "ollama", "nn_generate_training_code", architecture_summary[:200])
    llm = get_llm(temperature=0.15)
    prompt = (
        f"Arquitectura / objetivo:\n{architecture_summary}\n\n"
        f"Restricciones extra:\n{extra_constraints or 'ninguna'}"
    )
    out = llm.invoke(
        [
            SystemMessage(content=TRAIN_CODE_SYS),
            HumanMessage(content=prompt),
        ]
    )
    raw = str(getattr(out, "content", out) or "")
    return _extract_python(raw) if "```" in raw else raw.strip()


def _nn_save_memory_impl(metrics_and_notes: str) -> str:
    from agents.memory_agent import get_memory_agent

    instruction = (
        "Añade una entrada de progreso que documente este entrenamiento o experimento de red neuronal:\n"
        + metrics_and_notes.strip()
    )
    a2a_log("neural_network", "memory", "invoke_memory_agent_graph", instruction[:400])
    agent = get_memory_agent()
    result = agent.invoke(
        {"messages": [HumanMessage(content=instruction)]},
        config={"recursion_limit": 20},
    )
    return extract_final_ai_text(result)


def build_neural_network_tools():
    @tool
    def nn_run_sequential_training_pipeline(user_goal: str, save_metrics_to_memory: bool = True) -> str:
        """
        RECOMENDADO para entrenar de punta a punta en un solo paso (evita condiciones de carrera):
        1) diseña la arquitectura, 2) genera código PyTorch CPU con datos sintéticos,
        3) ejecuta el script, 4) opcionalmente delega en el agente de memoria con la salida real.
        user_goal: objetivo del experimento en lenguaje natural.
        save_metrics_to_memory: si True, guarda en memoria un resumen con la salida de ejecución.
        """
        a2a_log("neural_network", "neural_network", "sequential_pipeline", user_goal[:220])
        design = _nn_design_impl(user_goal)
        code = _nn_generate_impl(design, user_goal)
        a2a_log("neural_network", "python_runner", "nn_run_training_script", code[:160])
        run_out = run_python_code(code, timeout_sec=120)
        parts = [
            "=== Diseño ===\n" + design,
            "=== Código (extracto) ===\n" + code[:1200] + ("..." if len(code) > 1200 else ""),
            "=== Ejecución ===\n" + run_out,
        ]
        if save_metrics_to_memory:
            mem_note = "Salida del pipeline de entrenamiento (verbatim):\n" + run_out[:2000]
            parts.append("=== Memoria ===\n" + _nn_save_memory_impl(mem_note))
        return "\n\n".join(parts)

    @tool
    def nn_design_architecture(user_goal: str) -> str:
        """Diseña una arquitectura de red neuronal (capas, pérdida, optimizador) según el objetivo del usuario."""
        return _nn_design_impl(user_goal)

    @tool
    def nn_generate_pytorch_training_code(architecture_summary: str, extra_constraints: str = "") -> str:
        """
        Genera código PyTorch listo para entrenar un modelo pequeño en CPU con datos sintéticos.
        architecture_summary: resumen de la arquitectura deseada.
        extra_constraints: requisitos adicionales opcionales.
        """
        return _nn_generate_impl(architecture_summary, extra_constraints)

    @tool
    def nn_run_training_script(python_code: str) -> str:
        """
        Ejecuta un script Python de entrenamiento PyTorch en subproceso y devuelve stdout/stderr.
        python_code: código fuente completo (sin fences markdown).
        """
        code = _extract_python(python_code) if "```" in python_code else python_code.strip()
        a2a_log("neural_network", "python_runner", "nn_run_training_script", code[:160])
        return run_python_code(code, timeout_sec=120)

    @tool
    def nn_save_training_progress_to_memory(metrics_and_notes: str) -> str:
        """
        Guarda en el agente de MEMORIA un resumen de entrenamiento (métricas, pérdidas, decisiones).
        metrics_and_notes: texto en español para registrar como progreso o recordatorio.
        """
        return _nn_save_memory_impl(metrics_and_notes)

    return [
        nn_run_sequential_training_pipeline,
        nn_design_architecture,
        nn_generate_pytorch_training_code,
        nn_run_training_script,
        nn_save_training_progress_to_memory,
    ]
