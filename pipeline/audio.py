from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class FFmpegNotFoundError(RuntimeError):
    pass


def ensure_ffmpeg_available() -> str:
    """
    Returns the ffmpeg executable path if available, else raises.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise FFmpegNotFoundError(
            "ffmpeg_not_found: ffmpeg executable is not in PATH. "
            "Install ffmpeg and ensure C:\\ffmpeg\\bin is in your user PATH."
        )
    return ffmpeg_path


def to_wav_16k_mono(input_path: Path, output_wav_path: Path) -> Path:
    """
    Convert any media (mp4/wav/...) to a WAV 16kHz mono PCM file suitable for ASR.
    """
    input_path = Path(input_path)
    output_wav_path = Path(output_wav_path)
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = ensure_ffmpeg_available()

    # -y overwrite, -vn drop video, 16k mono, pcm_s16le for compatibility
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_wav_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg_failed: could not convert input to wav\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stderr: {proc.stderr.strip()}"
        )

    return output_wav_path