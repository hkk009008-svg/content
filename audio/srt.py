"""SRT caption-file writer.

Transcribes a voiceover audio file into precisely-timed SRT (SubRip)
captions using OpenAI's local whisper model.
"""

from __future__ import annotations


def generate_srt(audio_path: str, srt_path: str, language: str = "English") -> str:
    """Transcribe `audio_path` and write SRT captions to `srt_path`.

    Uses whisper's "base" model (small enough for fast CPU inference,
    accurate enough for SRT alignment). Each segment from the whisper
    transcript becomes one SRT cue with `start --> end\\ntext`.

    Args:
        audio_path: path to the audio file to transcribe (.mp3, .wav, etc.)
        srt_path:   where to write the resulting SRT.
        language:   target language name (English, Korean, Japanese, ...). Passed
                    as a hint to whisper so transcription doesn't drift on
                    non-English audio. Defaults to English to preserve old behavior.

    Returns:
        srt_path on success (for chaining).
    """
    print(f"📝 [AUDIO] Transcribing audio back to precise SRT captions: {audio_path} ({language})")
    import whisper
    import datetime

    # Map our project language name to a whisper-recognized code/name.
    # whisper accepts both ISO codes ('ko') and English names ('korean').
    lang_map = {
        "english": "english", "korean": "korean", "japanese": "japanese",
        "mandarin": "chinese", "mandarin (simplified)": "chinese",
        "spanish": "spanish", "french": "french", "german": "german",
        "hindi": "hindi", "arabic": "arabic", "portuguese": "portuguese",
        "italian": "italian", "russian": "russian",
    }
    whisper_lang = lang_map.get((language or "english").lower().strip(), None)

    # Use the base model for speed and accuracy
    model = whisper.load_model("base")
    # When language is unknown, leave whisper to auto-detect; otherwise pin it.
    transcribe_kwargs = {}
    if whisper_lang:
        transcribe_kwargs["language"] = whisper_lang
    result = model.transcribe(audio_path, **transcribe_kwargs)

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
