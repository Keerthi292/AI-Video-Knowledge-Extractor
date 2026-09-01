from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel


class TranscriptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_model() -> WhisperModel:
    """Load the Whisper model once and reuse it across requests.

    Loading is slow (reads model weights from disk into memory), so we
    cache the loaded model instead of reloading it on every request.
    int8 quantization keeps the memory footprint small enough for
    memory-constrained hosts (faster-whisper's CTranslate2 backend, unlike
    openai-whisper's full PyTorch runtime, doesn't need much headroom).
    """
    return WhisperModel("tiny", device="cpu", compute_type="int8")


def transcribe_audio(audio_path: Path) -> tuple[str, str | None]:
    """Transcribe audio to text, returning (text, detected_language_code)."""
    try:
        model = _get_model()
        segments, info = model.transcribe(str(audio_path))
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as exc:
        raise TranscriptionError(
            f"Whisper failed to transcribe {audio_path.name}: {exc}"
        )

    return text, info.language
