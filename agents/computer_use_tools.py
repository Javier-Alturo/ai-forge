"""Computer use local: PyAutoGUI + visión vía Ollama (p.ej. llava)."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pyautogui
from langchain_core.tools import tool
from agents.a2a_log import a2a_log

OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "llava")


def _screenshot_b64() -> str:
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _ollama_vision(prompt: str, image_b64: str) -> str:
    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
    }
    a2a_log("computer_use", "ollama_vision", "api_chat", VISION_MODEL)
    r = httpx.post(f"{OLLAMA_BASE}/api/chat", json=payload, timeout=180.0)
    r.raise_for_status()
    data = r.json()
    return str(data.get("message", {}).get("content", data))


@tool
def computer_screenshot(question: str = "Describe brevemente lo que ves en la pantalla.") -> str:
    """Captura la pantalla y la describe con el modelo de visión (Ollama llava por defecto). question: instrucción en lenguaje natural."""
    b64 = _screenshot_b64()
    return _ollama_vision(question, b64)


@tool
def computer_click(x: int, y: int, button: str = "left") -> str:
    """Hace clic en coordenadas de pantalla (píxeles). button: left, right o middle."""
    a2a_log("computer_use", "pyautogui", "click", f"{x},{y}")
    pyautogui.click(x=int(x), y=int(y), button=button)
    return f"Clic en ({x}, {y}) botón={button}."


@tool
def computer_type_text(text: str, interval: float = 0.02) -> str:
    """Escribe texto como si fuera teclado (PyAutoGUI; mejor con ASCII)."""
    a2a_log("computer_use", "pyautogui", "type", text[:80])
    pyautogui.write(text, interval=float(interval))
    return f"Escritos {len(text)} caracteres."


@tool
def computer_move_mouse(x: int, y: int, duration: float = 0.2) -> str:
    """Mueve el cursor a coordenadas x,y."""
    a2a_log("computer_use", "pyautogui", "move", f"{x},{y}")
    pyautogui.moveTo(int(x), int(y), duration=float(duration))
    return f"Mouse movido a ({x}, {y})."


@tool
def computer_open_app(app_name_or_path: str) -> str:
    """Abre una aplicación: ruta ejecutable o nombre (Windows: start)."""
    a2a_log("computer_use", "os", "open_app", app_name_or_path[:120])
    p = Path(app_name_or_path)
    if sys.platform == "win32":
        if p.is_file():
            os.startfile(str(p))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["cmd", "/c", "start", "", app_name_or_path], shell=False)
    else:
        subprocess.Popen(["xdg-open", app_name_or_path] if p.is_file() else ["sh", "-c", app_name_or_path])
    return f"Lanzado: {app_name_or_path}"


@tool
def computer_find_element(description: str) -> str:
    """
    Captura pantalla y pregunta al modelo de visión dónde está un elemento.
    Devuelve descripción y, si es posible, coordenadas sugeridas en texto.
    """
    b64 = _screenshot_b64()
    prompt = (
        "Localiza en la captura el elemento descrito. Responde SOLO un JSON válido "
        'con claves "x" y "y" (enteros, centro aproximado en píxeles de pantalla) y "confidence" 0-1. '
        f"Elemento: {description}"
    )
    raw = _ollama_vision(prompt, b64)
    m = re.search(r"\{[^{}]+\}", raw)
    coords = m.group(0) if m else "(sin JSON parseable)"
    return f"Modelo: {raw}\n\nExtraído: {coords}"


def get_computer_use_tools():
    return [
        computer_screenshot,
        computer_click,
        computer_type_text,
        computer_move_mouse,
        computer_open_app,
        computer_find_element,
    ]
