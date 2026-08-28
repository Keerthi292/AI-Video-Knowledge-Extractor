from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from services.downloader import (
    TranscriptUnavailableError,
    VideoDownloadError,
    get_video_transcript,
)

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


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=HOST, port=PORT)
