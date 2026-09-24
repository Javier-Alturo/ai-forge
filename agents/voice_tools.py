"""Tools del agente de voz (micrófono + Whisper local)."""

from __future__ import annotations

import numpy as np
from langchain_core.tools import tool

from agents.a2a_log import a2a_log

_WHISPER_MODEL = None


def _get_whisper():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        import whisper

        name = __import__("os").environ.get("WHISPER_MODEL", "base")
        a2a_log("voice", "whisper", "load_model", name)
        _WHISPER_MODEL = whisper.load_model(name)
    return _WHISPER_MODEL


def record_and_transcribe_impl(
    max_seconds: float = 60.0,
    silence_seconds: float = 1.5,
    sample_rate: int = 16000,
) -> str:
    """
    Graba del micrófono en bloques hasta silencio prolongado o max_seconds.
    Transcribe con Whisper (modelo base por defecto).
    """
    import sounddevice as sd

    block_frames = int(0.25 * sample_rate)
    max_blocks = int(max_seconds / 0.25)
    silence_blocks_needed = max(1, int(silence_seconds / 0.25))
    chunks: list[np.ndarray] = []
    silence_run = 0

    def rms(frames: np.ndarray) -> float:
        if frames.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(frames), dtype=np.float64)))

    threshold = float(__import__("os").environ.get("VOICE_SILENCE_RMS", "0.012"))

    a2a_log("voice", "microphone", "recording_start", f"sr={sample_rate}")
    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        blocksize=block_frames,
    ) as stream:
        for _ in range(max_blocks):
            data, _ = stream.read(block_frames)
            mono = data.reshape(-1).astype(np.float32, copy=False)
            chunks.append(mono.copy())
            level = rms(mono)
            if level < threshold:
                silence_run += 1
                if silence_run >= silence_blocks_needed:
                    break
            else:
                silence_run = 0

    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    a2a_log("voice", "microphone", "recording_stop", f"samples={audio.size}")

    if audio.size < sample_rate * 0.3:
        return "(Grabación demasiado corta o sin audio detectado.)"

    model = _get_whisper()
    # Whisper espera float32 [-1,1] a 16 kHz
    import torch

    result = model.transcribe(audio, fp16=torch.cuda.is_available())
    text = (result.get("text") or "").strip()
    a2a_log("voice", "whisper", "transcribed", text[:200])
    return text or "(Sin texto reconocido.)"


@tool
def voice_record_and_transcribe(max_seconds: int = 60, silence_seconds: float = 1.5) -> str:
    """
    Graba audio del micrófono hasta detectar silencio (o hasta max_seconds) y transcribe con Whisper local.
    max_seconds: tiempo máximo de grabación. silence_seconds: silencio continuo para cortar.
    """
    return record_and_transcribe_impl(
        max_seconds=float(max_seconds),
        silence_seconds=float(silence_seconds),
    )


def get_voice_tools():
    return [voice_record_and_transcribe]