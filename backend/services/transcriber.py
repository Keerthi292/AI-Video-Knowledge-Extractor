from functools import lru_cache
from pathlib import Path

import whisper


class TranscriptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_model():
    """Load the Whisper model once and reuse it across requests.

    Loading is slow (reads model weights from disk into memory), so we
    cache the loaded model instead of reloading it on every request.
    """
    # device="cpu" is explicit: auto-detection picks up any visible CUDA
    # device even if its compute capability isn't supported by the
    # installed torch build, which fails loudly at inference time.
    return whisper.load_model("tiny", device="cpu")


def transcribe_audio(audio_path: Path) -> str:
    try:
        model = _get_model()
        result = model.transcribe(str(audio_path))
    except Exception as exc:
        raise TranscriptionError(
            f"Whisper failed to transcribe {audio_path.name}: {exc}"
        )

    return result["text"].strip()
