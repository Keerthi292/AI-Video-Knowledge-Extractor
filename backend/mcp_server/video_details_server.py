from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from services import db
from services.logging_setup import configure_app_logging
from services.db import AuthError
from services.downloader import (
    TranscriptUnavailableError,
    VideoDownloadError,
    get_video_transcript,
)
from services.summarizer import SummarizationError
from services.summarizer import summarize_media as _summarize_media
from services.summarizer import summarize_transcript as _summarize_transcript
from services.topic_assistant import TopicAssistantError
from services.topic_assistant import explain_topic as _explain_topic
from services.topic_assistant import quiz_overall as _quiz_overall
from services.topic_assistant import quiz_topic as _quiz_topic

HOST = "127.0.0.1"
PORT = 8765

mcp = MCPServer("video-details")
configure_app_logging()


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
def summarize_transcript(
    transcript: str, target_language: str | None = None, time_budget_seconds: float | None = None
) -> dict:
    """Summarize a video transcript with Gemini into an intro, key points,
    and a learning-roadmap topic tree, optionally written in a chosen
    target_language regardless of the transcript's own language.
    time_budget_seconds optionally caps how long Gemini may take."""
    try:
        return _summarize_transcript(transcript, target_language, time_budget_seconds)
    except SummarizationError as exc:
        raise ToolError(str(exc))


@mcp.tool()
def summarize_media(
    file_uri: str,
    mime_type: str | None = None,
    youtube: bool = False,
    target_language: str | None = None,
    time_budget_seconds: float | None = None,
) -> dict:
    """Build the same intro/key points/roadmap as summarize_transcript, but
    directly from a public YouTube URL (youtube=true) or a Gemini Files API
    URI of uploaded audio/video - one Gemini call, no separate transcription
    step. Also returns "language", the detected spoken language. Falls back
    across Gemini models within time_budget_seconds."""
    try:
        return _summarize_media(file_uri, mime_type, youtube, target_language, time_budget_seconds)
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


def _require_user(token: str) -> dict:
    user = db.get_user_from_token(token)
    if user is None:
        raise ToolError("Not authenticated: invalid or expired session token")
    return user


@mcp.tool()
def signup(email: str, password: str) -> dict:
    """Create a new account and return a session token for it."""
    try:
        user_id = db.create_user(email, password)
    except AuthError as exc:
        raise ToolError(str(exc))

    token = db.create_session(user_id)
    return {"token": token, "email": email.strip().lower()}


@mcp.tool()
def guest_login() -> dict:
    """Create a throwaway guest account and return a session token for it,
    for the Skip-login path (no email/password required)."""
    user_id = db.create_guest_user()
    token = db.create_session(user_id)
    return {"token": token, "email": None, "is_guest": True}


@mcp.tool()
def login(email: str, password: str) -> dict:
    """Log in to an existing account and return a session token."""
    try:
        user_id = db.verify_user(email, password)
    except AuthError as exc:
        raise ToolError(str(exc))

    token = db.create_session(user_id)
    return {"token": token, "email": email.strip().lower()}


@mcp.tool()
def logout(token: str) -> dict:
    """End a session token."""
    db.delete_session(token)
    return {"success": True}


@mcp.tool()
def list_history(token: str) -> dict:
    """List the logged-in user's own past analyses (never another user's -
    scoped strictly to the account the token belongs to)."""
    user = _require_user(token)
    return {"analyses": db.list_analyses(user["id"])}


@mcp.tool()
def get_history_item(token: str, analysis_id: int) -> dict:
    """Fetch one of the logged-in user's own saved analyses by id. Returns
    an error if the analysis doesn't exist or belongs to a different
    account."""
    user = _require_user(token)
    analysis = db.get_analysis(user["id"], analysis_id)
    if analysis is None:
        raise ToolError("Analysis not found")
    return analysis


@mcp.tool()
def update_done_topics(token: str, analysis_id: int, done_topics: list[str]) -> dict:
    """Overwrite which topics are marked done for one of the logged-in
    user's own analyses."""
    user = _require_user(token)
    updated = db.set_done_topics(user["id"], analysis_id, done_topics)
    if not updated:
        raise ToolError("Analysis not found")
    return {"success": True}


@mcp.tool()
def upgrade_guest(token: str, email: str, password: str) -> dict:
    """Turn the token's guest account into a real email/password account,
    keeping all of its history. The same session token stays valid."""
    user = _require_user(token)
    try:
        db.upgrade_guest_user(user["id"], email, password)
    except AuthError as exc:
        raise ToolError(str(exc))
    return {"token": token, "email": email.strip().lower(), "is_guest": False}


@mcp.tool()
def create_share_link(token: str, analysis_id: int) -> dict:
    """Make one of the logged-in user's analyses publicly viewable (read-only)
    and return its share token. Reuses the existing token if already shared."""
    user = _require_user(token)
    share_token = db.create_share_token(user["id"], analysis_id)
    if share_token is None:
        raise ToolError("Analysis not found")
    return {"share_token": share_token}


@mcp.tool()
def revoke_share_link(token: str, analysis_id: int) -> dict:
    """Stop sharing one of the logged-in user's analyses; the old link stops
    working."""
    user = _require_user(token)
    if not db.revoke_share_token(user["id"], analysis_id):
        raise ToolError("Analysis not found")
    return {"success": True}


@mcp.tool()
def get_shared_analysis(share_token: str) -> dict:
    """Public read-only view of a shared analysis (no login needed). Contains
    no account data."""
    analysis = db.get_shared_analysis(share_token)
    if analysis is None:
        raise ToolError("Shared analysis not found")
    return analysis


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host=HOST, port=PORT)
