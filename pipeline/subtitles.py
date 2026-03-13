from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def format_srt_time(seconds: float) -> str:
    """
    Convert seconds -> SRT timestamp "HH:MM:SS,mmm".
    """
    if seconds < 0:
        seconds = 0.0

    hours = int(seconds // 3600)
    seconds = seconds % 3600
    minutes = int(seconds // 60)
    seconds = seconds % 60

    whole_seconds = int(seconds)
    milliseconds = int(round((seconds - whole_seconds) * 1000))

    # handle rounding overflow (e.g., 1.9996 -> 2.000)
    if milliseconds == 1000:
        whole_seconds += 1
        milliseconds = 0
        if whole_seconds == 60:
            minutes += 1
            whole_seconds = 0
            if minutes == 60:
                hours += 1
                minutes = 0

    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


def write_srt(segments: Iterable[Segment], output_path: Path) -> None:
    """
    Write segments to an SRT file.
    """
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        start = format_srt_time(seg.start)
        end = format_srt_time(seg.end)
        text = (seg.text or "").strip()

        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")  # blank line required

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")