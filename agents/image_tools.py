"""Tools del agente de imágenes (Stable Diffusion vía diffusers, CUDA si existe)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from agents.a2a_log import a2a_log

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUT = _ROOT / "outputs"

_SD_PIPE = None


def _outputs_dir() -> Path:
    p = Path(os.environ.get("IMAGE_OUTPUT_DIR", str(_DEFAULT_OUT))).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _get_pipeline():
    global _SD_PIPE
    if _SD_PIPE is not None:
        return _SD_PIPE
    import torch
    from diffusers import StableDiffusionPipeline

    model_id = os.environ.get(
        "SD_MODEL_ID",
        "runwayml/stable-diffusion-v1-5",
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    a2a_log("image", "diffusers", "load_pipeline", f"{model_id} device={device}")
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        safety_checker=None,
    )
    _SD_PIPE = pipe.to(device)
    return _SD_PIPE


@tool
def image_generate(
    prompt: str,
    negative_prompt: str = "",
    num_inference_steps: int = 25,
    width: int = 512,
    height: int = 512,
) -> str:
    """
    Genera una imagen con Stable Diffusion (runwayml/stable-diffusion-v1-5 por defecto).
    Guarda PNG en la carpeta outputs (o IMAGE_OUTPUT_DIR). Usa GPU CUDA si está disponible.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return "Falta el prompt."
    out_dir = _outputs_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"sd_{ts}.png"
    path = out_dir / fname

    pipe = _get_pipeline()
    import torch

    gen = torch.Generator(device=pipe.device)
    gen.manual_seed(int(os.environ.get("SD_SEED", "42")))
    a2a_log("image", "diffusers", "generate", prompt[:160])
    call_kw: dict = {
        "prompt": prompt,
        "num_inference_steps": int(num_inference_steps),
        "width": int(width),
        "height": int(height),
        "generator": gen,
    }
    if (negative_prompt or "").strip():
        call_kw["negative_prompt"] = negative_prompt.strip()
    img = pipe(**call_kw).images[0]
    img.save(str(path))
    return f"Imagen guardada: {path}"


@tool
def image_list_outputs(max_files: int = 30) -> str:
    """Lista archivos de imagen recientes en la carpeta de salida."""
    d = _outputs_dir()
    a2a_log("image", "filesystem", "list_outputs", str(d))
    files = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    if not files:
        return "(Sin imágenes en outputs.)"
    return "\n".join(str(f) for f in files)


def get_image_tools():
    return [image_generate, image_list_outputs]
