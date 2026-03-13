from enum import Enum


class InputType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class OutputType(str, Enum):
    VIDEO_EMBEDDED = "video_embedded"
    VIDEO_WITH_SUBTITLE_TRACK = "video_with_subtitle_track"
    SUBTITLES_SRT = "subtitles_srt"
    TRANSCRIPT_TEXT = "transcript_text"


VIDEO_EXTENSIONS = {".mp4"}
AUDIO_EXTENSIONS = {".wav", ".mp3"}


def detect_input_type_from_suffix(suffix: str) -> InputType:
    s = suffix.lower()
    if s in VIDEO_EXTENSIONS:
        return InputType.VIDEO
    if s in AUDIO_EXTENSIONS:
        return InputType.AUDIO
    raise ValueError(f"unsupported_file_type: {s}")


def available_outputs_for(input_type: InputType) -> list[str]:
    if input_type == InputType.VIDEO:
        return [
            OutputType.VIDEO_EMBEDDED.value,
            OutputType.VIDEO_WITH_SUBTITLE_TRACK.value,
            OutputType.SUBTITLES_SRT.value,
            OutputType.TRANSCRIPT_TEXT.value,
        ]
    return [
        OutputType.SUBTITLES_SRT.value,
        OutputType.TRANSCRIPT_TEXT.value,
    ]