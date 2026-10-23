"""Computer use local: PyAutoGUI + visión vía Ollama (p.ej. llava).

Seguridad: por defecto el agente solo puede MIRAR la pantalla (captura + localizar).
Clic, teclado, mover el mouse y abrir apps requieren AIFORGE_ALLOW_COMPUTER_USE=1.
Abrir apps solo acepta nombres de AIFORGE_ALLOWED_APPS (nunca rutas ni comandos).
"""

from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import sys

import httpx
import pyautogui
from langchain_core.tools import tool
from agents.a2a_log import a2a_log

OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "llava")

DEFAULT_ALLOWED_APPS = "notepad,calc,mspaint"


def control_allowed() -> bool:
    return os.environ.get("AIFORGE_ALLOW_COMPUTER_USE", "").strip() == "1"


def allowed_apps() -> set[str]:
    raw = os.environ.get("AIFORGE_ALLOWED_APPS", DEFAULT_ALLOWED_APPS)
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


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
def computer_open_app(app_name: str) -> str:
    """Abre una aplicación de la lista permitida por nombre (p.ej. notepad, calc)."""
    a2a_log("computer_use", "os", "open_app", app_name[:120])
    name = app_name.strip().lower()
    if name not in allowed_apps() or not re.fullmatch(r"[a-z0-9_.-]+", name):
        return f"⛔ App no permitida: {app_name}. Permitidas: {', '.join(sorted(allowed_apps()))}"
    if sys.platform == "win32":
        os.startfile(name)  # type: ignore[attr-defined]
    else:
        subprocess.Popen([name], shell=False)
    return f"Lanzado: {name}"


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
    read_only = [computer_screenshot, computer_find_element]
    if not control_allowed():
        a2a_log("computer_use", "policy", "read_only", "AIFORGE_ALLOW_COMPUTER_USE no activo")
        return read_only
    return read_only + [computer_click, computer_type_text, computer_move_mouse, computer_open_app]
