import json
import logging
import os
import time
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Tried in order: Gemini models often return 503 "high demand" for a while,
# and pinned versions eventually get retired (404), so any failure moves on
# to the next. The "-latest" aliases track Google's current models; the
# Lite ones are a last resort (fine for audio, often 503 on YouTube URLs).
TRANSCRIPTION_MODELS = (
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
)
# If every model is busy, wait and go through the list once more.
TRANSCRIPTION_ROUNDS = 2
TRANSCRIPTION_RETRY_DELAY_SECONDS = 10

# Upper bound on a single model attempt. Without it a stuck request hangs
# forever (the SDK has no default timeout); long videos legitimately take a
# few minutes to transcribe, so this is generous.
ATTEMPT_TIMEOUT_MS = 300_000

# Only the speech matters, so have Gemini sample YouTube video frames rarely
# and at low resolution - far fewer tokens to process per minute of video.
YOUTUBE_FRAMES_PER_SECOND = 0.2
YOUTUBE_MEDIA_RESOLUTION = types.MediaResolution.MEDIA_RESOLUTION_LOW

# Gemini processes uploaded audio asynchronously; poll until it's ready.
FILE_READY_TIMEOUT_SECONDS = 120
FILE_READY_POLL_INTERVAL_SECONDS = 2

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "transcript": {"type": "string"},
    },
    "required": ["language", "transcript"],
}

PROMPT = """Transcribe the speech in this audio/video verbatim, in the language it is
spoken (do not translate). Return the full transcript as plain text with no
timestamps or speaker labels, and the ISO 639-1 code of the main spoken
language (e.g. "en", "hi"). If there is no speech, return an empty transcript."""


class TranscriptionError(Exception):
    pass


def _wait_until_active(client: genai.Client, file: types.File) -> types.File:
    deadline = time.monotonic() + FILE_READY_TIMEOUT_SECONDS
    while file.state == types.FileState.PROCESSING:
        if time.monotonic() >= deadline:
            raise TranscriptionError("Gemini took too long to process the uploaded audio")
        time.sleep(FILE_READY_POLL_INTERVAL_SECONDS)
        file = client.files.get(name=file.name)
    if file.state == types.FileState.FAILED:
        raise TranscriptionError("Gemini could not process the uploaded audio")
    return file


def _client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise TranscriptionError("GEMINI_API_KEY environment variable is not set")
    return genai.Client(api_key=api_key)


def _generate(
    client: genai.Client, model: str, media: types.Part, media_resolution: types.MediaResolution | None
) -> dict:
    response = client.models.generate_content(
        model=model,
        contents=types.Content(parts=[media, types.Part(text=PROMPT)]),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            media_resolution=media_resolution,
            http_options=types.HttpOptions(timeout=ATTEMPT_TIMEOUT_MS),
        ),
    )
    return json.loads(response.text)


def _transcribe(
    client: genai.Client,
    media: types.Part,
    source: str,
    fallback_media: types.Part | None = None,
    media_resolution: types.MediaResolution | None = None,
) -> tuple[str, str | None]:
    """`media`/`media_resolution` are the preferred (cheaper) request; if a
    model rejects them as invalid, that model is retried once with plain
    `fallback_media` and default resolution."""
    errors = []
    started = time.monotonic()
    for round_number in range(TRANSCRIPTION_ROUNDS):
        if round_number:
            time.sleep(TRANSCRIPTION_RETRY_DELAY_SECONDS)
        for model in TRANSCRIPTION_MODELS:
            attempt_started = time.monotonic()
            try:
                try:
                    result = _generate(client, model, media, media_resolution)
                except Exception as exc:
                    if fallback_media is None or "INVALID_ARGUMENT" not in str(exc):
                        raise
                    logger.warning("%s rejected the low-cost video settings, retrying without them: %s", model, exc)
                    result = _generate(client, model, fallback_media, None)
            except Exception as exc:
                logger.warning(
                    "Transcription with %s failed after %.1fs for %s: %s",
                    model, time.monotonic() - attempt_started, source, exc,
                )
                errors.append(f"{model}: {exc}")
                continue

            text = (result.get("transcript") or "").strip()
            language = (result.get("language") or "").strip().lower() or None
            logger.info(
                "Transcribed %s with %s in %.1fs (%.1fs total incl. %d failed attempt(s))",
                source, model, time.monotonic() - attempt_started, time.monotonic() - started, len(errors),
            )
            return text, language

    raise TranscriptionError(f"Gemini failed to transcribe {source}: {'; '.join(errors)}")


def transcribe_audio(audio_path: Path) -> tuple[str, str | None]:
    """Transcribe audio to text, returning (text, detected_language_code).

    Offloads speech-to-text to Gemini instead of running Whisper locally:
    free-tier hosts have a fraction of a CPU core, which made local
    transcription take many times the video's length.
    """
    client = _client()
    uploaded = None
    try:
        try:
            uploaded = client.files.upload(file=str(audio_path))
        except Exception as exc:
            raise TranscriptionError(f"Could not upload {audio_path.name} to Gemini: {exc}")
        uploaded = _wait_until_active(client, uploaded)
        media = types.Part(file_data=types.FileData(file_uri=uploaded.uri, mime_type=uploaded.mime_type))
        return _transcribe(client, media, audio_path.name)
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass


def transcribe_youtube_url(url: str) -> tuple[str, str | None]:
    """Transcribe a public YouTube video by handing Gemini the URL directly.

    Google fetches the video on its side, so this works from cloud hosts
    whose IPs YouTube bot-walls for yt-dlp - no cookies or PO tokens needed.
    """
    return _transcribe(
        _client(),
        types.Part(
            file_data=types.FileData(file_uri=url),
            video_metadata=types.VideoMetadata(fps=YOUTUBE_FRAMES_PER_SECOND),
        ),
        url,
        fallback_media=types.Part(file_data=types.FileData(file_uri=url)),
        media_resolution=YOUTUBE_MEDIA_RESOLUTION,
    )
