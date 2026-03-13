from __future__ import annotations

import subprocess
from pathlib import Path


def _run_ffmpeg(cmd: list[str]):
    """Run ffmpeg command and raise if error."""
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg_failed:\nSTDOUT={result.stdout}\nSTDERR={result.stderr}"
        )


# =========================
# HARD SUBTITLES (burned)
# =========================
def embed_subtitles_in_video(
    input_video: Path,
    subtitles_srt: Path,
    output_video: Path,
):
    """
    Burn subtitles directly into video frames.
    Always visible.
    """

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_video),
        "-vf", f"subtitles={subtitles_srt}",
        "-c:a", "copy",
        str(output_video),
    ]

    _run_ffmpeg(cmd)


# =========================
# SOFT SUBTITLE TRACK
# =========================
def add_subtitle_track(
    input_video: Path,
    subtitles_srt: Path,
    output_video: Path,
):
    """
    Add subtitle track selectable by player.
    No heavy re-encode.
    """

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_video),
        "-i", str(subtitles_srt),
        "-c", "copy",
        "-c:s", "mov_text",
        str(output_video),
    ]

    _run_ffmpeg(cmd)