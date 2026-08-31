import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from services.audio_extractor import AudioExtractionError, extract_audio
from services.downloader import VideoDownloadError, download_audio
from services.mcp_client import MCPToolError, VideoDetailsMCPClient
from services.transcriber import TranscriptionError, transcribe_audio
from services.video_search import search_youtube_videos


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_client = VideoDetailsMCPClient()
    await mcp_client.connect()
    app.state.mcp_client = mcp_client
    yield
    await mcp_client.close()


app = FastAPI(title="AI Video Knowledge Extractor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_origin_regex=r"https://.*\.(netlify\.app|vercel\.app)",
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

SUMMARIES_DIR = Path(__file__).parent / "summaries"
SUMMARIES_DIR.mkdir(exist_ok=True)

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


def save_summary(analysis: dict, source: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    summary_path = SUMMARIES_DIR / f"{timestamp}-{uuid.uuid4().hex[:8]}.json"

    with open(summary_path, "w") as f:
        json.dump({"source": source, "generated_at": timestamp, **analysis}, f, indent=2)


async def _transcribe_url_via_audio(url: str) -> str:
    """Fallback for URLs with no usable captions: download just the audio
    and transcribe it locally with Whisper."""
    try:
        raw_audio_path = download_audio(url, UPLOAD_DIR)
    except VideoDownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    wav_path: Path | None = None
    try:
        try:
            wav_path = extract_audio(raw_audio_path)
        except AudioExtractionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        try:
            return transcribe_audio(wav_path)
        except TranscriptionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
    finally:
        raw_audio_path.unlink(missing_ok=True)
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)


class TopicRequest(BaseModel):
    heading: str
    content: str
    example: str | None = None


class OverallQuizRequest(BaseModel):
    roadmap: list[dict]


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/topic/explain")
async def topic_explain(body: TopicRequest):
    try:
        return await app.state.mcp_client.explain_topic(body.heading, body.content, body.example)
    except MCPToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/topic/quiz")
async def topic_quiz(body: TopicRequest):
    try:
        return await app.state.mcp_client.quiz_topic(body.heading, body.content, body.example)
    except MCPToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/quiz/overall")
async def overall_quiz(body: OverallQuizRequest):
    try:
        return await app.state.mcp_client.quiz_overall(body.roadmap, count=12)
    except MCPToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/analyze")
async def analyze_video(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide either a video file or a video URL")

    if file and url:
        raise HTTPException(status_code=400, detail="Provide only one of: video file or video URL")

    if url:
        # Try captions first via the MCP server (no video/audio download).
        # If no usable captions exist, fall back to downloading just the
        # audio and transcribing it with Whisper, same as an uploaded file.
        try:
            details = await app.state.mcp_client.fetch_video_details(url)
            transcript = details["transcript"]
        except MCPToolError as exc:
            message = str(exc)
            if "TRANSCRIPT_UNAVAILABLE:" in message:
                transcript = await _transcribe_url_via_audio(url)
            elif "VIDEO_DOWNLOAD_ERROR:" in message:
                raise HTTPException(status_code=400, detail=message.split("VIDEO_DOWNLOAD_ERROR:", 1)[1].strip())
            else:
                raise HTTPException(status_code=502, detail=f"Video details MCP tool failed: {message}")

        try:
            analysis = await app.state.mcp_client.summarize_transcript(transcript)
        except MCPToolError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        await enrich_video_resources(analysis["roadmap"])

        save_summary(analysis, source=url)

        return {
            "success": True,
            "intro": analysis["intro"],
            "key_points": analysis["key_points"],
            "roadmap": analysis["roadmap"],
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
            audio_path = extract_audio(temp_path)
        except AudioExtractionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        try:
            transcript = transcribe_audio(audio_path)
        except TranscriptionError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        try:
            analysis = await app.state.mcp_client.summarize_transcript(transcript)
        except MCPToolError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        await enrich_video_resources(analysis["roadmap"])

        save_summary(analysis, source=file.filename)

        return {
            "success": True,
            "intro": analysis["intro"],
            "key_points": analysis["key_points"],
            "roadmap": analysis["roadmap"],
        }
    finally:
        temp_path.unlink(missing_ok=True)
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)


if __name__ == "__main__":
    import uvicorn

    # Running this file directly (`python main.py`) starts the whole backend:
    # the FastAPI app's `lifespan` above spawns the video-details MCP tool
    # server as a subprocess and connects to it, so no separate process needs
    # to be started by hand.
    uvicorn.run(app, host="0.0.0.0", port=8000)
