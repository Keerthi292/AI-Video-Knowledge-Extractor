import subprocess
from pathlib import Path


class AudioExtractionError(Exception):
    pass


def extract_audio(video_path: Path) -> Path:
    """Extract mono 16kHz WAV audio from a video file using FFmpeg.

    Whisper expects 16kHz mono PCM audio, so we convert directly to that
    format here instead of doing a second conversion step later.
    """
    audio_path = video_path.with_suffix(".wav")

    command = [
        "ffmpeg",
        "-y",  # overwrite output file if it already exists
        "-i", str(video_path),  # input file
        "-vn",  # drop video stream, keep audio only
        "-acodec", "pcm_s16le",  # uncompressed 16-bit PCM (what Whisper expects)
        "-ar", "16000",  # resample to 16kHz
        "-ac", "1",  # downmix to mono
        str(audio_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        if "does not contain any stream" in result.stderr:
            raise AudioExtractionError(
                f"{video_path.name} has no audio track to transcribe"
            )

        # FFmpeg prints a long banner before the actual error; the last
        # non-empty line is almost always the useful part.
        stderr_lines = [line for line in result.stderr.strip().splitlines() if line]
        last_line = stderr_lines[-1] if stderr_lines else "unknown error"
        raise AudioExtractionError(
            f"FFmpeg failed to extract audio from {video_path.name}: {last_line}"
        )

    if not audio_path.exists():
        raise AudioExtractionError(
            f"FFmpeg reported success but no audio file was created for {video_path.name}"
        )

    return audio_path
