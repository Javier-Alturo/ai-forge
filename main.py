"""
CLI del sistema multi-agente (LangGraph + Ollama).

Uso:
  python main.py
  python main.py "busca noticias sobre Python 3.13"
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sistema A2A multi-agente (LangGraph + Ollama): orquestador, web, memoria, código, PyTorch."
    )
    parser.add_argument(
        "message",
        nargs="*",
        help="Mensaje para el orquestador. Si se omite, entra en modo interactivo.",
    )
    args = parser.parse_args()

    from agents.llm import format_llm_cli_banner  # noqa: E402
    from agents.orchestrator import run_turn  # noqa: E402

    # Cada ejecución de main.py genera un hilo de conversación único.
    # Todos los turnos de esta sesión comparten contexto (el orquestador "recuerda").
    session_id = str(uuid.uuid4())

    print(format_llm_cli_banner())
    print(
        "A2A: los cruces orquestador<->agente y agente<->agente se registran en stderr con prefijo [A2A ...].\n"
        "Comandos: escribe tu mensaje, 'voz' para dictado+Whisper, 'salir' para terminar, 'ayuda' para ejemplos.\n"
    )

    def handle_line(line: str) -> None:
        line = line.strip()
        if not line:
            return
        if line.lower() in ("salir", "exit", "quit"):
            raise KeyboardInterrupt
        if line.lower() == "ayuda":
            print(
                "Ejemplos:\n"
                "  - Hola, ¿qué puedes hacer?\n"
                "  - Busca en la web qué es LangGraph y guarda un resumen en memoria\n"
                "  - Guarda un recordatorio: comprar leche mañana\n"
                "  - Muestra mi memoria / mi progreso\n"
                "  - Ejecuta código Python que calcule los primeros 15 primos\n"
                "  - Diseña una red pequeña en PyTorch y entrénala unos segundos con datos sintéticos\n"
                "  - voz  (comando: graba micrófono, transcribe Whisper y pasa el texto al orquestador)\n"
            )
            return
        if line.lower() == "voz":
            from agents.voice_agent import run_voice_cli_session  # noqa: E402

            try:
                run_voice_cli_session()
            except Exception as exc:  # noqa: BLE001
                print(f"\nError (voz): {exc}\n", file=sys.stderr)
            return
        try:
            msg = run_turn(line, thread_id=session_id)
            print("\n" + (msg.content or "") + "\n")
        except Exception as exc:  # noqa: BLE001
            print(f"\nError: {exc}\n", file=sys.stderr)

    if args.message:
        handle_line(" ".join(args.message))
        return

    while True:
        try:
            line = input("Tú> ")
        except (EOFError, KeyboardInterrupt):
            print("\nAdiós.")
            break
        try:
            handle_line(line)
        except KeyboardInterrupt:
            print("\nAdiós.")
            break


if __name__ == "__main__":
    main()
