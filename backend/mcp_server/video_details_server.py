from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from services.downloader import (
    TranscriptUnavailableError,
    VideoDownloadError,
    get_video_transcript,
)
from services.summarizer import SummarizationError
from services.summarizer import summarize_transcript as _summarize_transcript
from services.topic_assistant import TopicAssistantError
from services.topic_assistant import explain_topic as _explain_topic
from services.topic_assistant import quiz_overall as _quiz_overall
from services.topic_assistant import quiz_topic as _quiz_topic

HOST = "127.0.0.1"
PORT = 8765

mcp = MCPServer("video-details")


@mcp.tool()
def fetch_video_details(url: str) -> dict:
    """Fetch transcript text and metadata for a video URL from existing
    captions/subtitles only (no video/audio download)."""
    try:
        transcript, metadata = get_video_transcript(url)
    except TranscriptUnavailableError as exc:
        raise ToolError(f"TRANSCRIPT_UNAVAILABLE: {exc}")
    except VideoDownloadError as exc:
        raise ToolError(f"VIDEO_DOWNLOAD_ERROR: {exc}")

    return {"transcript": transcript, **metadata}


@mcp.tool()
def summarize_transcript(transcript: str, target_language: str | None = None) -> dict:
    """Summarize a video transcript with Gemini into an intro, key points,
    and a learning-roadmap topic tree, optionally written in a chosen
    target_language regardless of the transcript's own language."""
    try:
        return _summarize_transcript(transcript, target_language)
    except SummarizationError as exc:
        raise ToolError(str(exc))


@mcp.tool()
def explain_topic(heading: str, content: str, example: str | None = None) -> dict:
    """Generate a deeper AI explanation (4-6 points) for one roadmap topic
    that goes beyond its existing explanation."""
    try:
        points = _explain_topic(heading, content, example)
    except TopicAssistantError as exc:
        raise ToolError(str(exc))

    return {"points": points}


@mcp.tool()
def quiz_topic(heading: str, content: str, example: str | None = None) -> dict:
    """Generate a 4-5 question multiple-choice quiz testing understanding of
    one roadmap topic."""
    try:
        questions = _quiz_topic(heading, content, example)
    except TopicAssistantError as exc:
        raise ToolError(str(exc))

    return {"questions": questions}


@mcp.tool()
def quiz_overall(roadmap: list[dict], count: int = 12) -> dict:
    """Generate a multiple-choice quiz covering an entire roadmap, spread
    across all of its modules."""
    try:
        questions = _quiz_overall(roadmap, count)
    except TopicAssistantError as exc:
        raise ToolError(str(exc))

    return {"questions": questions}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=HOST, port=PORT)
