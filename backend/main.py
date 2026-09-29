import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from services import db
from services.logging_setup import configure_app_logging
from services.audio_extractor import AudioExtractionError, extract_audio
from services.downloader import POT_PROVIDER_BASE_URL, YTDLP_COOKIES_FILE, VideoDownloadError, download_audio
from services.mcp_client import MCPToolError, VideoDetailsMCPClient
from services.transcriber import (
    TranscriptionError,
    delete_uploaded_media,
    transcribe_audio,
    transcribe_youtube_url,
    upload_media,
)
from services.video_search import search_youtube_videos

logger = logging.getLogger(__name__)
configure_app_logging(__name__)

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

# --- User-facing errors never name the AI provider or its models ---

_PROVIDER_NAME_RE = re.compile(r"\bgoogle[ -]?gemini\b|\bgemini[-\w.]*", re.IGNORECASE)


def public_error_message(message: str) -> str:
    """Error text as shown to users: raw provider failures become plain
    messages, and any provider/model name that's left is replaced with a
    neutral "AI" (server logs keep the full detail)."""
    if "RESOURCE_EXHAUSTED" in message or "429" in message:
        return "The AI service's usage limit has been reached for now. Please try again later."
    if "UNAVAILABLE" in message or "503" in message or "high demand" in message:
        return "The AI service is busy right now. Please try again in a few minutes."
    if "invalid JSON" in message or "request failed" in message or "returned no" in message or "malformed" in message:
        return "The AI service had a problem with this request. Please try again."
    return _PROVIDER_NAME_RE.sub("AI", message)


@app.exception_handler(HTTPException)
async def _public_http_exception_handler(request, exc: HTTPException):
    if isinstance(exc.detail, str):
        if _PROVIDER_NAME_RE.search(exc.detail):
            logger.warning("Error shown to user as a generic message: %s", exc.detail)
        exc.detail = public_error_message(exc.detail)
    return await http_exception_handler(request, exc)


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
            "The AI service's usage limit has been reached for now, so this YouTube video "
            "couldn't be analyzed. Please try again later (the limit resets daily)."
        )
    return "The AI service is busy right now and couldn't analyze this YouTube video. Please try again in a few minutes."


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


# --- Live progress + time limit: streamed as Server-Sent Events ---
#
# Faster than /api/analyze: for YouTube links, uploads and caption-less
# videos, Gemini watches/listens and writes the roadmap in ONE call instead of
# first writing out a full verbatim transcript (slow, and never stored).

SSE_KEEPALIVE_SECONDS = 15
# Hard cap on a whole streamed analysis; every Gemini call only gets what's left.
ANALYSIS_TIME_LIMIT_SECONDS = 240
# Held back from Gemini's budget for finding related videos and saving.
FINISHING_RESERVE_SECONDS = 20
RESOURCES_TIME_LIMIT_SECONDS = 15
# With less Gemini budget than this left, don't bother starting a fallback path.
MIN_FALLBACK_SECONDS = 45
TIME_LIMIT_MESSAGE = (
    "The AI service is too slow right now to finish this analysis in time. "
    "Please try again in a few minutes."
)


def _media_error(exc: MCPToolError) -> HTTPException:
    message = str(exc)
    for marker in ("GEMINI_QUOTA:", "GEMINI_BUSY:"):
        if marker in message:
            return HTTPException(status_code=503, detail=message.split(marker, 1)[1].strip())
    return HTTPException(status_code=500, detail=message)


async def _analysis_pipeline(
    user: dict,
    url: str | None,
    file_path: Path | None,
    source: str,
    target_language: str | None,
    emit,
    deadline: float,
) -> dict:
    """Analyze a URL or uploaded file within `deadline` (time.monotonic()),
    reporting each stage through `emit(step, message)`. Raises
    HTTPException like /api/analyze does."""

    def gemini_budget() -> float:
        return deadline - time.monotonic() - FINISHING_RESERVE_SECONDS

    async def analyze_audio_file(path: Path) -> dict:
        await emit("upload", "Uploading the audio…")
        try:
            uploaded = await asyncio.to_thread(upload_media, path)
        except TranscriptionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        try:
            await emit("analyze", "Listening to the audio and building your roadmap…")
            return await app.state.mcp_client.summarize_media(
                uploaded.uri, uploaded.mime_type, False, target_language, gemini_budget()
            )
        except MCPToolError as exc:
            raise _media_error(exc)
        finally:
            await asyncio.to_thread(delete_uploaded_media, uploaded.name)

    async def analyze_via_captions_or_audio(video_url: str) -> dict:
        await emit("captions", "Reading the video's captions…")
        try:
            details = await app.state.mcp_client.fetch_video_details(video_url)
        except MCPToolError as exc:
            message = str(exc)
            if "VIDEO_DOWNLOAD_ERROR:" in message:
                raise HTTPException(status_code=400, detail=message.split("VIDEO_DOWNLOAD_ERROR:", 1)[1].strip())
            if "TRANSCRIPT_UNAVAILABLE:" not in message:
                raise HTTPException(status_code=502, detail=f"Video details MCP tool failed: {message}")

            await emit("download", "No captions found — downloading the audio…")
            try:
                raw_audio_path = await asyncio.to_thread(download_audio, video_url, UPLOAD_DIR)
            except VideoDownloadError as download_exc:
                raise HTTPException(status_code=400, detail=str(download_exc))
            audio_path: Path | None = None
            try:
                try:
                    audio_path = await asyncio.to_thread(extract_audio, raw_audio_path)
                except AudioExtractionError as extract_exc:
                    raise HTTPException(status_code=500, detail=str(extract_exc))
                return await analyze_audio_file(audio_path)
            finally:
                raw_audio_path.unlink(missing_ok=True)
                if audio_path is not None:
                    audio_path.unlink(missing_ok=True)

        await emit("analyze", "Building your roadmap from the captions…")
        try:
            analysis = await app.state.mcp_client.summarize_transcript_within(
                details["transcript"], target_language, gemini_budget()
            )
        except MCPToolError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        analysis["language"] = details.get("language")
        return analysis

    if url and YOUTUBE_URL_RE.match(url):
        # Gemini fetches YouTube on Google's side - no bot wall, no download.
        await emit("analyze", "Watching the video and building your roadmap…")
        try:
            analysis = await app.state.mcp_client.summarize_media(url, None, True, target_language, gemini_budget())
        except MCPToolError as exc:
            gemini_error = _media_error(exc)
            logger.warning("Gemini YouTube analysis failed, falling back to captions: %s", exc)
            if gemini_budget() < MIN_FALLBACK_SECONDS:
                raise gemini_error
            try:
                analysis = await analyze_via_captions_or_audio(url)
            except HTTPException as fallback_exc:
                # On cloud hosts the fallback just hits YouTube's bot wall,
                # which hides why the Gemini attempt failed - report that.
                raise gemini_error from fallback_exc
    elif url:
        analysis = await analyze_via_captions_or_audio(url)
    else:
        await emit("extract", "Extracting audio from your video…")
        audio_path: Path | None = None
        try:
            try:
                audio_path = await asyncio.to_thread(extract_audio, file_path)
            except AudioExtractionError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
            analysis = await analyze_audio_file(audio_path)
        finally:
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)

    detected_language = analysis.pop("language", None)

    await emit("resources", "Finding related videos for each topic…")
    resources_timeout = max(1.0, min(RESOURCES_TIME_LIMIT_SECONDS, deadline - time.monotonic() - 5))
    try:
        await asyncio.wait_for(enrich_video_resources(analysis["roadmap"]), timeout=resources_timeout)
    except asyncio.TimeoutError:
        logger.warning("Related-video search hit its %.0fs limit; keeping what was found", resources_timeout)
        # Drop the AI-suggested placeholders the search didn't get to.
        for topic in _iter_topics(analysis["roadmap"]):
            if topic.get("resources"):
                topic["resources"] = [r for r in topic["resources"] if r.get("url")]

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
    started = time.monotonic()
    current_step: dict = {"name": None, "started": started}

    def log_step_done() -> None:
        if current_step["name"]:
            logger.info(
                "Analysis step %r took %.1fs (%s)",
                current_step["name"], time.monotonic() - current_step["started"], source,
            )

    async def emit(step: str, message: str) -> None:
        if step != current_step["name"]:
            log_step_done()
            current_step.update(name=step, started=time.monotonic())
        await queue.put({"type": "progress", "step": step, "message": message})

    async def run() -> None:
        try:
            result = await asyncio.wait_for(
                _analysis_pipeline(
                    user, url, temp_path, source, target_language, emit,
                    deadline=started + ANALYSIS_TIME_LIMIT_SECONDS,
                ),
                timeout=ANALYSIS_TIME_LIMIT_SECONDS,
            )
            log_step_done()
            logger.info("Analysis finished in %.1fs total (%s)", time.monotonic() - started, source)
            await queue.put({"type": "result", "data": result})
        except HTTPException as exc:
            detail = public_error_message(exc.detail) if isinstance(exc.detail, str) else exc.detail
            await queue.put({"type": "error", "status": exc.status_code, "detail": detail})
        except asyncio.TimeoutError:
            logger.warning("Analysis hit the %ss time limit (%s)", ANALYSIS_TIME_LIMIT_SECONDS, source)
            await queue.put({"type": "error", "status": 504, "detail": TIME_LIMIT_MESSAGE})
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
