import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from services.audio_extractor import AudioExtractionError, extract_audio
from services.summarizer import SummarizationError, summarize_transcript
from services.transcriber import TranscriptionError, transcribe_audio

app = FastAPI(title="AI Video Knowledge Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm"}
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze_video(file: UploadFile = File(...)):
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
            analysis = summarize_transcript(transcript)
        except SummarizationError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return {
            "success": True,
            "summary": analysis["summary"],
            "key_points": analysis["key_points"],
            "transcript": transcript,
        }
    finally:
        temp_path.unlink(missing_ok=True)
        if audio_path is not None:
            audio_path.unlink(missing_ok=True)
