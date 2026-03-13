from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from transformers import pipeline

_ASR_CACHE = {}

@dataclass(frozen=True)
class TranscriptionSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    full_text: str
    segments: list[TranscriptionSegment]


def _pick_device() -> tuple[Any, Any]:
    """
    Returns (device, dtype) for transformers pipeline.
    Uses GPU if available; otherwise CPU.
    """
    if torch.cuda.is_available():
        return 0, torch.float16  # device index for transformers pipeline
    return -1, torch.float32


def load_asr_model(model_name: str = "openai/whisper-medium.en"):
    """
    Cached loader: loads model once per process, then reuses it.
    """
    if model_name in _ASR_CACHE:
        return _ASR_CACHE[model_name]

    device, dtype = _pick_device()
    asr = pipeline(
        task="automatic-speech-recognition",
        model=model_name,
        device=device,
        dtype=dtype,
    )
    _ASR_CACHE[model_name] = asr
    return asr


def transcribe_wav(
    wav_path: str,
    asr_pipeline,
    chunk_length_s: int = 28,
) -> TranscriptionResult:
    """
    Transcribe a WAV file and return full text + timestamped segments.
    """
    raw = asr_pipeline(
        wav_path,
        chunk_length_s=chunk_length_s,
        return_timestamps=True,
    )

    full_text = (raw.get("text") or "").strip()

    segments: list[TranscriptionSegment] = []
    for ch in raw.get("chunks", []):
        ts = ch.get("timestamp")
        if not ts or len(ts) != 2:
            continue
        start, end = ts
        if start is None or end is None:
            continue
        if start > end:
            continue
        segments.append(
            TranscriptionSegment(
                start=float(start),
                end=float(end),
                text=(ch.get("text") or "").strip(),
            )
        )

    return TranscriptionResult(full_text=full_text, segments=segments)