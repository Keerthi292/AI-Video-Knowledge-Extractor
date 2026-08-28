import re
import time
import uuid
from pathlib import Path

import requests
import yt_dlp

CAPTION_FETCH_RETRIES = 3
CAPTION_FETCH_RETRY_DELAY_SECONDS = 2

PREFERRED_LANGUAGES = ("en", "en-US", "en-GB", "en-orig")


class VideoDownloadError(Exception):
    pass


class TranscriptUnavailableError(Exception):
    pass


def _pick_subtitle_track(subtitles: dict) -> list | None:
    """Pick a subtitle track from a yt-dlp subtitles/automatic_captions dict.

    Prefers English variants, falling back to whatever language is first
    available, so we still get a transcript for non-English videos.
    """
    if not subtitles:
        return None

    for lang in PREFERRED_LANGUAGES:
        if lang in subtitles:
            return subtitles[lang]

    return next(iter(subtitles.values()), None)


def _vtt_to_text(vtt: str) -> str:
    """Convert WebVTT captions into plain, deduplicated transcript text.

    Auto-generated captions repeat lines across overlapping cues (rolling
    captions), so consecutive duplicate lines are collapsed.
    """
    lines = []
    for raw_line in vtt.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT":
            continue
        if "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^(Kind|Language):", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if lines and lines[-1] == line:
            continue
        lines.append(line)

    return " ".join(lines)


def _fetch_captions_with_retry(caption_url: str) -> requests.Response:
    """Fetch a caption file, retrying on transient errors (YouTube's caption
    endpoint rate-limits with 429s under normal use)."""
    last_error: Exception | None = None

    for attempt in range(CAPTION_FETCH_RETRIES):
        try:
            response = requests.get(caption_url, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and status not in (429, 500, 502, 503, 504):
                break
            if attempt < CAPTION_FETCH_RETRIES - 1:
                time.sleep(CAPTION_FETCH_RETRY_DELAY_SECONDS * (attempt + 1))

    raise VideoDownloadError(f"Could not fetch captions: {last_error}")


def get_video_transcript(url: str) -> tuple[str, dict]:
    """Fetch a transcript for a video URL without downloading the video/audio.

    Uses yt-dlp only to read metadata and locate existing (manual or
    auto-generated) captions, then downloads just the small caption file.
    """
    options = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise VideoDownloadError(f"Could not read video info from URL: {exc}")

    track = _pick_subtitle_track(info.get("subtitles") or {})
    if track is None:
        track = _pick_subtitle_track(info.get("automatic_captions") or {})

    if track is None:
        raise TranscriptUnavailableError(
            "No captions/subtitles are available for this video, so a transcript "
            "can't be extracted without downloading and transcribing it."
        )

    vtt_entry = next(
        (entry for entry in track if entry.get("ext") == "vtt"),
        track[0],
    )

    response = _fetch_captions_with_retry(vtt_entry["url"])

    transcript = _vtt_to_text(response.text)
    if not transcript:
        raise TranscriptUnavailableError("Captions were found but contained no text.")

    metadata = {
        "title": info.get("title"),
        "description": info.get("description"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
    }

    return transcript, metadata


def download_audio(url: str, dest_dir: Path) -> Path:
    """Download only the audio track for a video URL, for transcription.

    Fallback for when no usable captions/subtitles exist. We only ever need
    the audio, so grabbing bestaudio avoids pulling the full video stream.
    """
    output_template = str(dest_dir / f"{uuid.uuid4()}.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": 500 * 1024 * 1024,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            audio_path = Path(ydl.prepare_filename(info))
    except yt_dlp.utils.DownloadError as exc:
        raise VideoDownloadError(f"Could not download audio from URL: {exc}")

    if not audio_path.exists():
        raise VideoDownloadError(f"Download reported success but no file was created for {url}")

    return audio_path
