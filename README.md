# AI-Video-Knowledge-Extractor

AI-powered video knowledge extractor that converts uploaded videos into transcripts, concise summaries, and key points using Whisper and Gemini, with a SvelteKit frontend and FastAPI backend.

## Architecture

SvelteKit → FastAPI → FFmpeg → Whisper → Gemini → Summary + Key Points + Transcript → SvelteKit

The user uploads a video from the SvelteKit UI. FastAPI receives it and orchestrates the pipeline: FFmpeg extracts audio from the video, Whisper transcribes that audio to text, and Gemini reads the transcript to generate a summary and key points. The results are sent back to SvelteKit and displayed to the user.

## Why Each Technology

| Tech | Role | Why this one |
|---|---|---|
| **SvelteKit** | Frontend UI | Lets the user upload a video and see results in a clean web page. |
| **FastAPI** | Backend orchestrator | Python backend — a natural fit since Whisper and most AI tooling are Python-native. |
| **FFmpeg** | Audio extraction | Strips clean audio out of any video container for Whisper to consume. |
| **Whisper** | Speech-to-text | Turns spoken audio into text that other AI can reason over. |
| **Gemini** | Summarization / reasoning | Takes the raw transcript and produces a summary and key points. |

## Project Structure

**Backend (FastAPI)**
- `backend/main.py` — FastAPI app, routes
- `backend/requirements.txt` — Python dependencies
- `backend/services/audio_extractor.py` — FFmpeg wrapper
- `backend/services/transcriber.py` — Whisper wrapper
- `backend/services/summarizer.py` — Gemini wrapper
- `backend/uploads/` — temp storage for uploaded videos/audio
- `backend/.env` — API keys (Gemini)

**Frontend (SvelteKit)**
- `frontend/src/routes/+page.svelte` — main page: upload form + results display
- `frontend/src/lib/api.ts` — functions to call FastAPI backend

## Out of Scope for V1

- No user accounts/auth
- No database (results shown once, not persisted)
- No video URL/YouTube downloading — just direct file upload
- No async job queues/background workers — processing happens synchronously per request
- No cloud storage — just local disk for temp files
- No streaming/progress bars — user waits for the full result

## Running Locally

Backend:
```bash
cd backend
python3 -m venv venv          # first time only
./venv/bin/pip install -r requirements.txt   # first time only
./venv/bin/uvicorn main:app --port 8000 --reload
```

Frontend:
```bash
cd frontend
npm run dev -- --open
```

Set `GEMINI_API_KEY` in `backend/.env` (see `backend/.env.example`) — get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

## Status

All V1 steps are complete: FastAPI backend, video upload, FFmpeg audio extraction, Whisper transcription, Gemini summarization, full pipeline wiring with cleanup, and the SvelteKit frontend end-to-end.
