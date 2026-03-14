from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from pipeline.audio import to_wav_16k_mono
from pipeline.subtitles import Segment, write_srt
from pipeline.transcription import load_asr_model, transcribe_wav
from pipeline.video import embed_subtitles_in_video, add_subtitle_track


class InputType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class OutputType(str, Enum):
    VIDEO_EMBEDDED = "video_embedded"
    VIDEO_WITH_SUBTITLE_TRACK = "video_with_subtitle_track"
    SUBTITLES_SRT = "subtitles_srt"
    TRANSCRIPT_TEXT = "transcript_text"


VIDEO_EXTENSIONS = {".mp4"}          
AUDIO_EXTENSIONS = {".wav",".mp3"}       # mp3 can be inputed but will be converted to wav 


def detect_input_type(input_path: Path) -> InputType:
    ext = input_path.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return InputType.VIDEO
    if ext in AUDIO_EXTENSIONS:
        return InputType.AUDIO
    raise ValueError(f"unsupported_file_type: {ext} (allowed video={VIDEO_EXTENSIONS}, audio={AUDIO_EXTENSIONS})")


def available_outputs_for(input_type: InputType) -> list[OutputType]:
    if input_type == InputType.VIDEO:
        return [
            OutputType.VIDEO_EMBEDDED,
            OutputType.VIDEO_WITH_SUBTITLE_TRACK,
            OutputType.SUBTITLES_SRT,
            OutputType.TRANSCRIPT_TEXT,
        ]
    # input audio
    return [
        OutputType.SUBTITLES_SRT,
        OutputType.TRANSCRIPT_TEXT,
    ]


def validate_requested_outputs(input_type: InputType, requested: Iterable[OutputType]) -> list[OutputType]:
    requested_list = list(requested)
    if not requested_list:
        raise ValueError("validation_error: requested_outputs cannot be empty")

    allowed = set(available_outputs_for(input_type))
    invalid = [o for o in requested_list if o not in allowed]
    if invalid:
        raise ValueError(
            f"invalid_output_for_input: input_type={input_type.value}, invalid={ [o.value for o in invalid] }, "
            f"allowed={ [o.value for o in allowed] }"
        )

    # remove duplicates while preserving order
    seen: set[OutputType] = set()
    unique: list[OutputType] = []
    for o in requested_list:
        if o not in seen:
            unique.append(o)
            seen.add(o)
    return unique


@dataclass(frozen=True)
class ProcessOptions:
    language: str = "en"
    model: str = "openai/whisper-base.en"


@dataclass
class ProcessResult:
    input_path: Path
    input_type: InputType
    requested_outputs: list[OutputType]
    output_dir: Path
    # map output type -> file path generated
    artifacts: dict[OutputType, Path]


def process_media(
    input_path: Path,
    requested_outputs: Iterable[OutputType],
    output_dir: Path,
    options: ProcessOptions | None = None,
) -> ProcessResult:

    if options is None:
        options = ProcessOptions()

    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(f"input_not_found: {input_path}")

    input_type = detect_input_type(input_path)
    requested = validate_requested_outputs(input_type, requested_outputs)

    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[OutputType, Path] = {}

    # =========================
    # 1) Normalize -> WAV 16k mono
    # =========================
    wav_path = output_dir / "audio_16k.wav"
    to_wav_16k_mono(input_path, wav_path)

    # =========================
    # 2) Transcription
    # =========================
    asr = load_asr_model(options.model)
    tr = transcribe_wav(str(wav_path), asr)

    # =========================
    # 3) transcript.txt
    # =========================
    if OutputType.TRANSCRIPT_TEXT in requested:
        txt_path = output_dir / "transcript.txt"
        txt_path.write_text(tr.full_text + "\n", encoding="utf-8")
        artifacts[OutputType.TRANSCRIPT_TEXT] = txt_path

    # =========================
    # 4) subtitles.srt
    # (required for video outputs too)
    # =========================
    need_srt = (
        OutputType.SUBTITLES_SRT in requested
        or OutputType.VIDEO_EMBEDDED in requested
        or OutputType.VIDEO_WITH_SUBTITLE_TRACK in requested
    )

    srt_path = None

    if need_srt:
        srt_path = output_dir / "subtitles.srt"
        srt_segments = [Segment(s.start, s.end, s.text) for s in tr.segments]
        write_srt(srt_segments, srt_path)

        if OutputType.SUBTITLES_SRT in requested:
            artifacts[OutputType.SUBTITLES_SRT] = srt_path

    # =========================
    # 5) VIDEO OUTPUTS
    # =========================
    if input_type == InputType.VIDEO and srt_path is not None:

        # ----- hard subtitles -----
        if OutputType.VIDEO_EMBEDDED in requested:
            out_path = output_dir / "video_embedded.mp4"
            embed_subtitles_in_video(input_path, srt_path, out_path)
            artifacts[OutputType.VIDEO_EMBEDDED] = out_path

        # ----- selectable subtitle track -----
        if OutputType.VIDEO_WITH_SUBTITLE_TRACK in requested:
            out_path = output_dir / "video_with_subtitle_track.mp4"
            add_subtitle_track(input_path, srt_path, out_path)
            artifacts[OutputType.VIDEO_WITH_SUBTITLE_TRACK] = out_path

    return ProcessResult(
        input_path=input_path,
        input_type=input_type,
        requested_outputs=requested,
        output_dir=output_dir,
        artifacts=artifacts,
    )