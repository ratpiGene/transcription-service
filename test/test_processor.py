import pytest

from app.media_rules import (
    InputType,
    detect_input_type_from_suffix,
    available_outputs_for,
)


def test_detect_input_type_video_mp4():
    assert detect_input_type_from_suffix(".mp4") == InputType.VIDEO


def test_detect_input_type_audio_wav():
    assert detect_input_type_from_suffix(".wav") == InputType.AUDIO


def test_detect_input_type_audio_mp3():
    assert detect_input_type_from_suffix(".mp3") == InputType.AUDIO


def test_detect_input_type_is_case_insensitive():
    assert detect_input_type_from_suffix(".MP4") == InputType.VIDEO
    assert detect_input_type_from_suffix(".WAV") == InputType.AUDIO


def test_detect_input_type_invalid_extension():
    with pytest.raises(ValueError, match="unsupported_file_type"):
        detect_input_type_from_suffix(".avi")


def test_available_outputs_for_video():
    outputs = available_outputs_for(InputType.VIDEO)
    assert outputs == [
        "video_embedded",
        "video_with_subtitle_track",
        "subtitles_srt",
        "transcript_text",
    ]


def test_available_outputs_for_audio():
    outputs = available_outputs_for(InputType.AUDIO)
    assert outputs == [
        "subtitles_srt",
        "transcript_text",
    ]