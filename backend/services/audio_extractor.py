import subprocess
from pathlib import Path


class AudioExtractionError(Exception):
    pass


def extract_audio(video_path: Path) -> Path:
    """Extract mono 16kHz MP3 audio from a video file using FFmpeg.

    Speech needs little fidelity, so a low-bitrate mono MP3 keeps the file
    small - it gets uploaded to Gemini for transcription.
    """
    # Distinct name so an input that is already .mp3 isn't overwritten in place.
    audio_path = video_path.with_name(f"{video_path.stem}.audio.mp3")

    command = [
        "ffmpeg",
        "-y",  # overwrite output file if it already exists
        "-i", str(video_path),  # input file
        "-vn",  # drop video stream, keep audio only
        "-acodec", "libmp3lame",  # compressed MP3, ~8x smaller than raw PCM
        "-b:a", "32k",  # plenty for intelligible speech
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
