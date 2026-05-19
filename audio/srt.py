"""SRT caption-file writer.

Transcribes a generated voiceover audio file back into precisely-timed
SRT (SubRip) captions using OpenAI's whisper. Used during the upload
phase to attach captions to the published YouTube video.

Moved from phase_b_audio.py in Phase 6 slice 1 — function body
unchanged. phase_b_audio.py re-exports `generate_srt` from here for
backward compatibility; downstream callers can either keep the old
import path or migrate to `from audio.srt import generate_srt`.
"""

from __future__ import annotations


def generate_srt(audio_path: str, srt_path: str) -> str:
    """Transcribe `audio_path` and write SRT captions to `srt_path`.

    Uses whisper's "base" model (small enough for fast CPU inference,
    accurate enough for SRT alignment). Each segment from the whisper
    transcript becomes one SRT cue with `start --> end\\ntext`.

    Args:
        audio_path: path to the audio file to transcribe (.mp3, .wav, etc.)
        srt_path:   where to write the resulting SRT.

    Returns:
        srt_path on success (for chaining).
    """
    print(f"📝 [PHASE B] Transcribing audio back to precise SRT captions: {audio_path}")
    import whisper
    import datetime

    # Use the base model for speed and accuracy
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(result["segments"], start=1):
            start = datetime.timedelta(seconds=segment["start"])
            end = datetime.timedelta(seconds=segment["end"])

            # Format timedelta to SRT format (HH:MM:SS,mmm)
            def format_time(td):
                total_seconds = int(td.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                milliseconds = int(td.microseconds / 1000)
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

            f.write(f"{i}\n")
            f.write(f"{format_time(start)} --> {format_time(end)}\n")
            f.write(f"{segment['text'].strip()}\n\n")

    print(f"✅ SRT successfully saved to {srt_path}")
    return srt_path
