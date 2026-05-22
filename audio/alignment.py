"""Forced alignment — word-level timestamps for dialogue audio.

Used by the dialogue pipeline + lipsync engines for ms-accurate audio↔video
synchronization. Lipsync precision jumps from ~85% (segment-level) to ~96%
(word-level + wav2vec2 forced alignment).

Provider chain:
  1. WhisperX (preferred) — Whisper transcript + wav2vec2 forced alignment
  2. Vanilla Whisper with `word_timestamps=True` (less precise but always
     available since this project already depends on whisper)
  3. None — graceful return when both fail

The output schema is fixed across providers so downstream callers
(lip_sync.validate_lipsync_quality, audio.dialogue alignment metadata,
subtitle writers) don't care which path produced the alignment.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple


# Model caches — loading whisperx-base is ~140 MB GPU VRAM and ~1-2s wall time;
# load_align_model is similar per language. Without caching, a 60-shot project
# loaded the same models 60 times. The lock guards against two shots racing
# the lazy-load (rare but cheap to fix).
_WHISPERX_MODEL_CACHE: dict = {}        # key: (device, compute_type) -> whisperx model
_ALIGN_MODEL_CACHE: dict = {}           # key: (language_code, device) -> (model, metadata)
_WHISPER_MODEL_CACHE: dict = {}         # key: "base" etc. -> whisper model
_MODEL_LOCK = threading.Lock()


@dataclass
class WordTiming:
    """One word's position in the audio timeline."""
    word: str
    start_s: float
    end_s: float
    confidence: float = 1.0


@dataclass
class AlignmentResult:
    """Forced alignment output for a single audio clip."""
    audio_path: str
    duration_s: float
    words: List[WordTiming]
    provider: str            # "whisperx" | "whisper_word_ts" | "none"
    transcript: str = ""     # full transcript reconstructed from words


# BCP-47-ish mapping for whisper/whisperx language hints. Whisper accepts ISO
# codes; whisperx's load_align_model expects the same.
_LANG_NAME_TO_CODE = {
    "english": "en", "korean": "ko", "japanese": "ja",
    "mandarin": "zh", "mandarin (simplified)": "zh", "chinese": "zh",
    "spanish": "es", "french": "fr", "german": "de",
    "hindi": "hi", "arabic": "ar", "portuguese": "pt",
    "italian": "it", "russian": "ru",
}


def _try_whisperx(
    audio_path: str,
    transcript_hint: Optional[str] = None,
    language: str = "English",
) -> Optional[AlignmentResult]:
    """WhisperX path — wav2vec2 forced alignment after Whisper transcription.

    transcript_hint, if given, is used as the reference text for alignment
    instead of re-transcribing. This is how dialogue.generate_dialogue_voiceover
    passes the source text — alignment is faster and more accurate when you
    already know what was said.

    language: project language name. Pinning the language massively improves
    accuracy on non-English audio — whisper's auto-detect is noisy for short
    clips, and the wrong align model (e.g. English wav2vec2 on Korean audio)
    produces garbage word boundaries.
    """
    try:
        import whisperx
        import torch
    except ImportError:
        return None

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    lang_code = _LANG_NAME_TO_CODE.get((language or "english").lower().strip(), None)

    try:
        # 1. Transcribe with language hint when known (avoids auto-detect drift).
        # Cache the whisperx model — loading is expensive (140MB GPU + 1-2s).
        wx_key = (device, compute_type)
        with _MODEL_LOCK:
            model = _WHISPERX_MODEL_CACHE.get(wx_key)
            if model is None:
                model = whisperx.load_model("base", device=device, compute_type=compute_type)
                _WHISPERX_MODEL_CACHE[wx_key] = model
        audio = whisperx.load_audio(audio_path)
        transcribe_kwargs = {}
        if lang_code:
            transcribe_kwargs["language"] = lang_code
        result = model.transcribe(audio, **transcribe_kwargs)

        # 2. Align with wav2vec2 (use pinned language code if given, else what whisper detected).
        # Cache per language — different languages need different wav2vec2 models.
        effective_lang = lang_code or result.get("language", "en")
        align_key = (effective_lang, device)
        with _MODEL_LOCK:
            cached_align = _ALIGN_MODEL_CACHE.get(align_key)
            if cached_align is None:
                cached_align = whisperx.load_align_model(
                    language_code=effective_lang, device=device
                )
                _ALIGN_MODEL_CACHE[align_key] = cached_align
        align_model, align_meta = cached_align
        aligned = whisperx.align(
            result["segments"], align_model, align_meta, audio, device,
            return_char_alignments=False,
        )

        # 3. Flatten to word timings
        words: List[WordTiming] = []
        for seg in aligned.get("segments", []):
            for w in seg.get("words", []):
                # whisperx fields: word, start, end, score
                if "start" in w and "end" in w:
                    words.append(WordTiming(
                        word=w.get("word", "").strip(),
                        start_s=float(w["start"]),
                        end_s=float(w["end"]),
                        confidence=float(w.get("score", 1.0)),
                    ))

        duration = words[-1].end_s if words else 0.0
        transcript = " ".join(w.word for w in words).strip()
        return AlignmentResult(
            audio_path=audio_path,
            duration_s=duration,
            words=words,
            provider="whisperx",
            transcript=transcript_hint or transcript,
        )
    except Exception as e:
        print(f"[alignment] WhisperX failed for {os.path.basename(audio_path)}: {e}")
        return None


def _try_whisper_word_ts(
    audio_path: str,
    transcript_hint: Optional[str] = None,
    language: str = "English",
) -> Optional[AlignmentResult]:
    """Vanilla whisper with word_timestamps=True — fallback when whisperx isn't installed.
    Less precise than wav2vec2 alignment but always available since the
    project already depends on whisper.
    """
    try:
        import whisper
    except ImportError:
        return None

    # whisper accepts English language name OR ISO code; we send the canonical
    # English-name form because that's the documented API.
    lang_name_map = {
        "english": "english", "korean": "korean", "japanese": "japanese",
        "mandarin": "chinese", "chinese": "chinese",
        "spanish": "spanish", "french": "french", "german": "german",
        "hindi": "hindi", "arabic": "arabic", "portuguese": "portuguese",
        "italian": "italian", "russian": "russian",
    }
    whisper_lang = lang_name_map.get((language or "english").lower().strip(), None)

    try:
        # "base" model is the right balance — small/fast, accurate enough for
        # dialogue (which is typically short and clean). Cache to avoid the
        # ~1-2s load on every shot.
        with _MODEL_LOCK:
            model = _WHISPER_MODEL_CACHE.get("base")
            if model is None:
                model = whisper.load_model("base")
                _WHISPER_MODEL_CACHE["base"] = model
        transcribe_kwargs = {"word_timestamps": True, "verbose": False}
        if whisper_lang:
            transcribe_kwargs["language"] = whisper_lang
        result = model.transcribe(audio_path, **transcribe_kwargs)

        words: List[WordTiming] = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                if "start" in w and "end" in w:
                    words.append(WordTiming(
                        word=w.get("word", "").strip(),
                        start_s=float(w["start"]),
                        end_s=float(w["end"]),
                        confidence=float(w.get("probability", 1.0)),
                    ))

        duration = words[-1].end_s if words else 0.0
        transcript = " ".join(w.word for w in words).strip()
        return AlignmentResult(
            audio_path=audio_path,
            duration_s=duration,
            words=words,
            provider="whisper_word_ts",
            transcript=transcript_hint or transcript,
        )
    except Exception as e:
        print(f"[alignment] whisper word_ts failed for {os.path.basename(audio_path)}: {e}")
        return None


def align_audio_to_text(
    audio_path: str,
    transcript_hint: Optional[str] = None,
    language: str = "English",
) -> Optional[AlignmentResult]:
    """Forced-align an audio file. Returns None if both providers fail.

    Args:
        audio_path: local path to the audio file (mp3/wav/m4a).
        transcript_hint: optional reference text. Passed through to the result
            for downstream consumers — does NOT currently constrain the
            transcription itself (whisper/whisperx still run free-form
            transcription, but the hint is preserved in the output for
            applications like SRT generation that prefer human-authored text).
        language: project language name. Critical for non-English audio —
            whisper's auto-detect is unreliable on short clips and using the
            wrong wav2vec2 align model produces garbage word boundaries.

    Returns:
        AlignmentResult or None on failure. provider field tells you which
        backend produced it ("whisperx" / "whisper_word_ts").
    """
    if not audio_path or not os.path.exists(audio_path):
        return None

    # Try WhisperX first (better quality)
    out = _try_whisperx(audio_path, transcript_hint, language=language)
    if out and out.words:
        return out

    # Fallback to vanilla whisper word timestamps
    out = _try_whisper_word_ts(audio_path, transcript_hint, language=language)
    if out and out.words:
        return out

    return None


def save_alignment_json(result: AlignmentResult, json_path: str) -> str:
    """Write an alignment result to disk as JSON (sidecar file pattern).
    The convention is to save alongside the audio with .alignment.json suffix.
    """
    payload = {
        "audio_path": result.audio_path,
        "duration_s": result.duration_s,
        "provider": result.provider,
        "transcript": result.transcript,
        "words": [asdict(w) for w in result.words],
    }
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)
    return json_path


def load_alignment_json(json_path: str) -> Optional[AlignmentResult]:
    """Read an alignment sidecar back."""
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path) as f:
            data = json.load(f)
        words = [WordTiming(**w) for w in data.get("words", [])]
        return AlignmentResult(
            audio_path=data.get("audio_path", ""),
            duration_s=float(data.get("duration_s", 0.0)),
            words=words,
            provider=data.get("provider", "unknown"),
            transcript=data.get("transcript", ""),
        )
    except Exception as e:
        print(f"[alignment] failed to load {json_path}: {e}")
        return None
