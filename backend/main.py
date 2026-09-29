import asyncio
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from services import db
from services.audio_extractor import AudioExtractionError, extract_audio
from services.downloader import POT_PROVIDER_BASE_URL, YTDLP_COOKIES_FILE, VideoDownloadError, download_audio
from services.mcp_client import MCPToolError, VideoDetailsMCPClient
from services.transcriber import TranscriptionError, transcribe_audio, transcribe_youtube_url
from services.video_search import search_youtube_videos

logger = logging.getLogger(__name__)

YOUTUBE_URL_RE = re.compile(r"^https?://(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)
YOUTUBE_VIDEO_ID_RE = re.compile(
    r"^https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)


def normalize_video_url(url: str) -> str:
    """Accept URLs pasted without a scheme ("youtube.com/watch?v=..."), and
    reduce any YouTube link (youtu.be, shorts, tracking params like xstg/si)
    to the canonical watch URL. Without this, a scheme-less YouTube link
    skips the Gemini path and goes straight to yt-dlp, which YouTube
    bot-walls."""
    url = url.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        url = f"https://{url}"
    match = YOUTUBE_VIDEO_ID_RE.match(url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return url


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    mcp_client = VideoDetailsMCPClient()
    await mcp_client.connect()
    app.state.mcp_client = mcp_client
    yield
    await mcp_client.close()


app = FastAPI(title="AI Video Knowledge Extractor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_origin_regex=r"https://.*\.(netlify\.app|vercel\.app)",
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm"}
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def _iter_topics(roadmap: list[dict]):
    for topic in roadmap:
        yield topic
        for child in topic.get("children") or []:
            yield child


async def enrich_video_resources(roadmap: list[dict]) -> None:
    """Replace resource suggestions with real YouTube video links (via
    yt-dlp search, no API key needed), so resources are actually clickable
    and correct rather than just plausible-sounding titles. AI-suggested
    article resources are dropped since we have no equivalent free article
    search."""
    topics_with_resources = [
        topic for topic in _iter_topics(roadmap) if topic.get("resources")
    ]
    if not topics_with_resources:
        return

    async def fetch(topic: dict) -> None:
        real_videos = await asyncio.to_thread(search_youtube_videos, topic["heading"], 2)
        topic["resources"] = [{"type": "video", **v} for v in real_videos]

    await asyncio.gather(*(fetch(topic) for topic in topics_with_resources))


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Fast local auth guard used by every protected endpoint. Deliberately
    does NOT go through the MCP tool server (unlike the auth/history
    endpoints below) - this runs on every single request, so it stays a
    direct DB check rather than adding an MCP round trip to every call."""
    token = _bearer_token(authorization)
    user = db.get_user_from_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid, please log in again")

    return user


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return authorization.removeprefix("Bearer ").strip()


async def _transcribe_url_via_audio(url: str) -> tuple[str, str | None]:
    """Fallback for URLs with no usable captions: download just the audio
    and transcribe it with Gemini. Returns (transcript, language)."""
    try:
        raw_audio_path = await asyncio.to_thread(download_audio, url, UPLOAD_DIR)
    except VideoDownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audio_path: Path | None = None
    try:
        try:
            audio_path = await asyncio.to_thread(extract_audio, raw_audio_path)
        except AudioExtractionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        try:
            return await asyncio.to_thread(transcribe_audio, audio_path)
        except TranscriptionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
    finally:
        raw_audio_path.unlink(missing_ok=True)
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)


async def _transcribe_url_via_yt_dlp(url: str) -> tuple[str, str | None]:
    """Captions via the MCP server (no video/audio download); if the video
    has none, download just the audio and transcribe it with Gemini."""
    try:
        details = await app.state.mcp_client.fetch_video_details(url)
        return details["transcript"], details.get("language")
    except MCPToolError as exc:
        message = str(exc)
        if "TRANSCRIPT_UNAVAILABLE:" in message:
            return await _transcribe_url_via_audio(url)
        if "VIDEO_DOWNLOAD_ERROR:" in message:
            raise HTTPException(status_code=400, detail=message.split("VIDEO_DOWNLOAD_ERROR:", 1)[1].strip())
        raise HTTPException(status_code=502, detail=f"Video details MCP tool failed: {message}")


def _gemini_failure_message(exc: TranscriptionError) -> str:
    if "RESOURCE_EXHAUSTED" in str(exc):
        return (
            "Gemini's free usage limit has been reached for now, so this YouTube video "
            "couldn't be analyzed. Please try again later (the limit resets daily)."
        )
    return "Gemini is busy right now and couldn't analyze this YouTube video. Please try again in a few minutes."


class TopicRequest(BaseModel):
    heading: str
    content: str
    example: str | None = None


class OverallQuizRequest(BaseModel):
    roadmap: list[dict]


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class DoneTopicsRequest(BaseModel):
    done_topics: list[str]


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/health/ytdlp-cookies")
def ytdlp_cookies_status():
    """Reports whether YTDLP_COOKIES_FILE is configured and actually points
    at a file, without exposing its path or contents - just enough to debug
    a misconfigured Render secret file from the browser."""
    configured = bool(YTDLP_COOKIES_FILE)
    return {
        "configured": configured,
        "file_found": configured and Path(YTDLP_COOKIES_FILE).is_file(),
    }


@app.get("/api/health/pot-provider")
async def pot_provider_status():
    """Reports whether POT_PROVIDER_BASE_URL is configured and actually
    reachable from this server, without exposing the URL itself - just
    enough to debug a misconfigured/unreachable companion service."""
    configured = bool(POT_PROVIDER_BASE_URL)
    reachable = False
    if configured:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{POT_PROVIDER_BASE_URL}/ping")
                reachable = response.status_code == 200
        except httpx.HTTPError:
            reachable = False
    return {"configured": configured, "reachable": reachable}


@app.post("/api/auth/signup")
async def signup(body: SignupRequest):
    try:
        return await app.state.mcp_client.signup(body.email, body.password)
    except MCPToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    try:
        return await app.state.mcp_client.login(body.email, body.password)
    except MCPToolError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.post("/api/auth/guest")
async def guest_login():
    return await app.state.mcp_client.guest_login()


@app.post("/api/auth/logout")
async def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        try:
            await app.state.mcp_client.logout(authorization.removeprefix("Bearer ").strip())
        except MCPToolError:
            pass  # logout is best-effort; an already-invalid token is fine
    return {"success": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"email": user["email"], "is_guest": user["is_guest"]}


@app.get("/api/history")
async def history(authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    try:
        return await app.state.mcp_client.list_history(token)
    except MCPToolError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.get("/api/history/{analysis_id}")
async def history_item(analysis_id: int, authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    try:
        analysis = await app.state.mcp_client.get_history_item(token, analysis_id)
    except MCPToolError as exc:
        message = str(exc)
        status_code = 401 if "Not authenticated" in message else 404
        raise HTTPException(status_code=status_code, detail=message)
    return {"success": True, **analysis}


@app.put("/api/history/{analysis_id}/done-topics")
async def update_done_topics(
    analysis_id: int, body: DoneTopicsRequest, authorization: str | None = Header(default=None)
):
    token = _bearer_token(authorization)
    try:
        return await app.state.mcp_client.update_done_topics(token, analysis_id, body.done_topics)
    except MCPToolError as exc:
        message = str(exc)
        status_code = 401 if "Not authenticated" in message else 404
        raise HTTPException(status_code=status_code, detail=message)


@app.post("/api/topic/explain")
async def topic_explain(body: TopicRequest, user: dict = Depends(get_current_user)):
    try:
        return await app.state.mcp_client.explain_topic(body.heading, body.content, body.example)
    except MCPToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/topic/quiz")
async def topic_quiz(body: TopicRequest, user: dict = Depends(get_current_user)):
    try:
        return await app.state.mcp_client.quiz_topic(body.heading, body.content, body.example)
    except MCPToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/quiz/overall")
async def overall_quiz(body: OverallQuizRequest, user: dict = Depends(get_current_user)):
    try:
        return await app.state.mcp_client.quiz_overall(body.roadmap, count=12)
    except MCPToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/analyze")
async def analyze_video(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    target_language: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide either a video file or a video URL")

    if file and url:
        raise HTTPException(status_code=400, detail="Provide only one of: video file or video URL")

    if url:
        url = normalize_video_url(url)

    if url:
        transcript: str | None = None
        detected_language: str | None = None

        # YouTube bot-walls yt-dlp from cloud-host IPs, so for YouTube links
        # let Gemini fetch the video on Google's side first.
        gemini_error: TranscriptionError | None = None
        if YOUTUBE_URL_RE.match(url):
            try:
                transcript, detected_language = await asyncio.to_thread(transcribe_youtube_url, url)
            except TranscriptionError as exc:
                logger.warning("Gemini YouTube transcription failed, falling back to yt-dlp: %s", exc)
                gemini_error = exc

        # Other URLs (or if Gemini couldn't handle the YouTube link) go via yt-dlp.
        if not transcript:
            try:
                transcript, detected_language = await _transcribe_url_via_yt_dlp(url)
            except HTTPException as exc:
                # On cloud hosts the yt-dlp fallback just hits YouTube's bot
                # wall, which hides why the Gemini attempt failed - report that.
                if gemini_error is not None:
                    raise HTTPException(status_code=503, detail=_gemini_failure_message(gemini_error)) from exc
                raise

        try:
            analysis = await app.state.mcp_client.summarize_transcript(transcript, target_language)
        except MCPToolError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        await enrich_video_resources(analysis["roadmap"])

        analysis_id = db.save_analysis(user["id"], url, analysis, detected_language)

        return {
            "success": True,
            "id": analysis_id,
            "intro": analysis["intro"],
            "key_points": analysis["key_points"],
            "roadmap": analysis["roadmap"],
            "source": url,
            "detected_language": detected_language,
            "done_topics": [],
        }

    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format: {file.filename}",
        )

    temp_filename = f"{uuid.uuid4()}{extension}"
    temp_path = UPLOAD_DIR / temp_filename

    with open(temp_path, "wb") as buffer:
        buffer.write(await file.read())

    audio_path: Path | None = None

    try:
        try:
            audio_path = await asyncio.to_thread(extract_audio, temp_path)
        except AudioExtractionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        try:
            transcript, detected_language = await asyncio.to_thread(transcribe_audio, audio_path)
        except TranscriptionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        try:
            analysis = await app.state.mcp_client.summarize_transcript(transcript, target_language)
        except MCPToolError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        await enrich_video_resources(analysis["roadmap"])

        analysis_id = db.save_analysis(user["id"], file.filename, analysis, detected_language)

        return {
            "success": True,
            "id": analysis_id,
            "intro": analysis["intro"],
            "key_points": analysis["key_points"],
            "roadmap": analysis["roadmap"],
            "source": file.filename,
            "detected_language": detected_language,
            "done_topics": [],
        }
    finally:
        temp_path.unlink(missing_ok=True)
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)


# --- Live progress: same pipeline as /api/analyze, streamed as Server-Sent Events ---

SSE_KEEPALIVE_SECONDS = 15


async def _analysis_pipeline(
    user: dict,
    url: str | None,
    file_path: Path | None,
    source: str,
    target_language: str | None,
    emit,
) -> dict:
    """The /api/analyze pipeline, reporting each stage through `emit(step,
    message)`. Raises HTTPException exactly like /api/analyze does."""
    if url:
        transcript: str | None = None
        detected_language: str | None = None

        gemini_error: TranscriptionError | None = None
        if YOUTUBE_URL_RE.match(url):
            await emit("transcribe", "Gemini is watching and transcribing the YouTube video…")
            try:
                transcript, detected_language = await asyncio.to_thread(transcribe_youtube_url, url)
            except TranscriptionError as exc:
                logger.warning("Gemini YouTube transcription failed, falling back to yt-dlp: %s", exc)
                gemini_error = exc

        if not transcript:
            await emit("transcribe", "Reading the video's captions (or downloading its audio if there are none)…")
            try:
                transcript, detected_language = await _transcribe_url_via_yt_dlp(url)
            except HTTPException as exc:
                if gemini_error is not None:
                    raise HTTPException(status_code=503, detail=_gemini_failure_message(gemini_error)) from exc
                raise
    else:
        await emit("extract", "Extracting audio from your video…")
        audio_path: Path | None = None
        try:
            try:
                audio_path = await asyncio.to_thread(extract_audio, file_path)
            except AudioExtractionError as exc:
                raise HTTPException(status_code=500, detail=str(exc))

            await emit("transcribe", "Transcribing the audio with Gemini…")
            try:
                transcript, detected_language = await asyncio.to_thread(transcribe_audio, audio_path)
            except TranscriptionError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
        finally:
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)

    await emit("summarize", "Building your learning roadmap…")
    try:
        analysis = await app.state.mcp_client.summarize_transcript(transcript, target_language)
    except MCPToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    await emit("resources", "Finding related videos for each topic…")
    await enrich_video_resources(analysis["roadmap"])

    await emit("save", "Saving to your history…")
    analysis_id = db.save_analysis(user["id"], source, analysis, detected_language)

    return {
        "success": True,
        "id": analysis_id,
        "intro": analysis["intro"],
        "key_points": analysis["key_points"],
        "roadmap": analysis["roadmap"],
        "source": source,
        "detected_language": detected_language,
        "done_topics": [],
    }


@app.post("/api/analyze/stream")
async def analyze_video_stream(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    target_language: str | None = Form(None),
    user: dict = Depends(get_current_user),
):
    """Same as /api/analyze, but responds with a text/event-stream of
    `{"type": "progress", "step", "message"}` events while it works, then one
    final `{"type": "result", "data"}` or `{"type": "error", "status",
    "detail"}` event. Input validation errors are still plain HTTP errors."""
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide either a video file or a video URL")

    if file and url:
        raise HTTPException(status_code=400, detail="Provide only one of: video file or video URL")

    if url:
        url = normalize_video_url(url)

    temp_path: Path | None = None
    if file:
        extension = Path(file.filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported video format: {file.filename}")

        # Save the upload now - it may be closed once this handler returns
        # the streaming response.
        temp_path = UPLOAD_DIR / f"{uuid.uuid4()}{extension}"
        with open(temp_path, "wb") as buffer:
            buffer.write(await file.read())

    source = url or file.filename
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def emit(step: str, message: str) -> None:
        await queue.put({"type": "progress", "step": step, "message": message})

    async def run() -> None:
        try:
            result = await _analysis_pipeline(user, url, temp_path, source, target_language, emit)
            await queue.put({"type": "result", "data": result})
        except HTTPException as exc:
            await queue.put({"type": "error", "status": exc.status_code, "detail": exc.detail})
        except Exception:
            logger.exception("Streaming analysis failed")
            await queue.put({"type": "error", "status": 500, "detail": "Something went wrong while analyzing the video"})
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            await queue.put(None)

    async def events():
        task = asyncio.create_task(run())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    # SSE comment line - keeps proxies from closing an idle
                    # connection during long Gemini calls.
                    yield ": keep-alive\n\n"
                    continue
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Guest account upgrade ---


class UpgradeGuestRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/upgrade")
async def upgrade_guest(body: UpgradeGuestRequest, authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    try:
        return await app.state.mcp_client.upgrade_guest(token, body.email, body.password)
    except MCPToolError as exc:
        message = str(exc)
        status_code = 401 if "Not authenticated" in message else 400
        raise HTTPException(status_code=status_code, detail=message)


# --- Public share links ---


def _owned_resource_error(exc: MCPToolError) -> HTTPException:
    message = str(exc)
    status_code = 401 if "Not authenticated" in message else 404
    return HTTPException(status_code=status_code, detail=message)


@app.post("/api/history/{analysis_id}/share")
async def create_share_link(analysis_id: int, authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    try:
        return await app.state.mcp_client.create_share_link(token, analysis_id)
    except MCPToolError as exc:
        raise _owned_resource_error(exc)


@app.delete("/api/history/{analysis_id}/share")
async def revoke_share_link(analysis_id: int, authorization: str | None = Header(default=None)):
    token = _bearer_token(authorization)
    try:
        return await app.state.mcp_client.revoke_share_link(token, analysis_id)
    except MCPToolError as exc:
        raise _owned_resource_error(exc)


@app.get("/api/shared/{share_token}")
async def shared_analysis(share_token: str):
    """Public - no login required."""
    try:
        return await app.state.mcp_client.get_shared_analysis(share_token)
    except MCPToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    # Running this file directly (`python main.py`) starts the whole backend:
    # the FastAPI app's `lifespan` above spawns the video-details MCP tool
    # server as a subprocess and connects to it, so no separate process needs
    # to be started by hand.
    uvicorn.run(app, host="0.0.0.0", port=8000)
