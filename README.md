# AI-Video-Knowledge-Extractor

AI-powered video knowledge extractor that converts uploaded videos into transcripts, concise summaries, and key points using Whisper and Gemini, with a SvelteKit frontend and FastAPI backend.

## Architecture (V1)

```text
SvelteKit
   ↓
FastAPI
   ↓
FFmpeg
   ↓
Whisper
   ↓
Gemini
   ↓
Summary + Key Points + Transcript
   ↓
SvelteKit
```

The user uploads a video from the SvelteKit UI. FastAPI receives it and orchestrates the pipeline: FFmpeg extracts audio from the video, Whisper transcribes that audio to text, and Gemini reads the transcript to generate a summary and key points. The results are sent back to SvelteKit and displayed to the user.

## Why Each Technology

| Tech | Role | Why this one |
|---|---|---|
| **SvelteKit** | Frontend UI | Lets the user upload a video and see results in a clean web page. Reactive, simple to build forms/UI with. |
| **FastAPI** | Backend orchestrator | Python backend — a natural fit because Whisper and most AI tooling are Python-native. Handles file uploads, coordinates the pipeline steps, exposes an API for the frontend. |
| **FFmpeg** | Audio extraction | Video files contain audio+video muxed together. Whisper only needs audio. FFmpeg strips out clean audio (e.g., `.wav`/`.mp3`) from any video format. |
| **Whisper** | Speech-to-text | Turns spoken audio into accurate text — this is what makes "watching a video" become "readable text" that other AI can reason over. |
| **Gemini** | Summarization / reasoning | A large language model that takes the raw transcript and produces a coherent summary and extracts key points. |

Each tool does one job well — this is a classic pipeline architecture: media → audio → text → insight → UI.

## How Data Moves Through the System

1. **User action**: In the SvelteKit app, the user uploads a video file.
2. **Upload**: SvelteKit sends the video file to a FastAPI endpoint (e.g., `POST /process-video`) as multipart form data.
3. **Save & extract audio**: FastAPI saves the video temporarily, then calls FFmpeg (as a subprocess) to extract audio into a `.wav` file.
4. **Transcribe**: FastAPI passes that `.wav` file to Whisper, which returns a text transcript.
5. **Summarize**: FastAPI sends the transcript text to Gemini's API with a prompt asking for a summary and key points.
6. **Respond**: FastAPI packages `{ transcript, summary, key_points }` as JSON and returns it to SvelteKit.
7. **Display**: SvelteKit receives the JSON and renders it on the page.

At each step, the output of one tool becomes the input of the next.

## Build Plan

- **Step 1**: Minimal FastAPI backend — a health-check endpoint, project structure.
- **Step 2**: Video upload endpoint — accept a video file, save it to disk.
- **Step 3**: FFmpeg integration — extract audio from the saved video.
- **Step 4**: Whisper integration — transcribe the extracted audio to text.
- **Step 5**: Gemini integration — send transcript, get summary + key points.
- **Step 6**: Wire the full pipeline together in one endpoint (upload → ... → results).
- **Step 7**: SvelteKit frontend — upload form.
- **Step 8**: SvelteKit frontend — display transcript, summary, key points.
- **Step 9**: Connect frontend to backend, test end-to-end.

We build backend-first, one piece at a time, testing each in isolation (e.g., test FFmpeg extraction before wiring Whisper) before connecting everything.

## Planned Project Structure

**Backend (FastAPI)**
```text
backend/
├── main.py                 # FastAPI app, routes
├── requirements.txt        # Python dependencies
├── services/
│   ├── audio_extractor.py  # FFmpeg wrapper
│   ├── transcriber.py      # Whisper wrapper
│   └── summarizer.py       # Gemini wrapper
├── uploads/                # temp storage for uploaded videos/audio
└── .env                    # API keys (Gemini)
```

**Frontend (SvelteKit)**
```text
frontend/
├── src/
│   ├── routes/
│   │   └── +page.svelte    # main page: upload form + results display
│   ├── lib/
│   │   └── api.ts          # functions to call FastAPI backend
├── package.json
```

## Out of Scope for V1

- No user accounts/auth
- No database (results shown once, not persisted)
- No video URL/YouTube downloading — just direct file upload
- No async job queues/background workers — processing happens synchronously per request
- No cloud storage — just local disk for temp files
- No streaming/progress bars — user waits for the full result

---

## Progress Log

### Step 1 — SvelteKit Frontend Foundation ✅

Built the frontend foundation only: a SvelteKit + TypeScript project (`frontend/`) with a single upload page. No backend, FFmpeg, Whisper, or Gemini integration yet — the Analyze button just logs to the console.

**What was built**

- Scaffolded with `npx sv create frontend --template minimal --types ts`
- `frontend/src/routes/+page.svelte` — the upload page with:
  - "AI Video Knowledge Extractor" heading
  - "Choose Video" file picker (styled to look like a button)
  - "Selected file: `<filename>`" text, shown only after a file is picked
  - "Analyze Video" button, disabled until a file is selected
- Two explicit UI states modeled with a TypeScript union: `IDLE` and `FILE_SELECTED`

**Code**

```svelte
<script lang="ts">
	type UiState = 'IDLE' | 'FILE_SELECTED';

	let selectedFile: File | null = $state(null);
	let uiState: UiState = $derived(selectedFile ? 'FILE_SELECTED' : 'IDLE');

	function handleFileChange(event: Event) {
		const input = event.target as HTMLInputElement;
		selectedFile = input.files?.[0] ?? null;
	}

	function handleAnalyze() {
		console.log('Analyze clicked for:', selectedFile?.name);
	}
</script>

<main>
	<h1>AI Video Knowledge Extractor</h1>

	<section>
		<h2>Upload a video</h2>

		<label class="choose-video">
			Choose Video
			<input type="file" accept="video/*" onchange={handleFileChange} />
		</label>

		{#if uiState === 'FILE_SELECTED' && selectedFile}
			<p class="selected-file">
				Selected file:<br />
				<strong>{selectedFile.name}</strong>
			</p>
		{/if}

		<button disabled={uiState !== 'FILE_SELECTED'} onclick={handleAnalyze}>
			Analyze Video
		</button>
	</section>
</main>
```

**Concepts**

- **SvelteKit**: a full application framework built on Svelte. Plain Svelte gives you components; SvelteKit adds file-based routing, a dev server, SSR, and build tooling — the Svelte-world equivalent of Next.js for React.
- **`.svelte` file**: a single-file component containing markup, a `<script>` block for logic, and a `<style>` block for CSS scoped to that component. Compiled at build time into JS that updates the DOM directly (no virtual DOM diffing).
- **`+page.svelte`**: in SvelteKit's file-based routing, any `+page.svelte` defines the UI for the route matching its folder. `src/routes/+page.svelte` renders at `/`, so it's the home page.
- **File input**: `<input type="file" accept="video/*" onchange={handleFileChange} />` is a native HTML file picker. `accept="video/*"` is a UX hint for the OS dialog, not a hard restriction. Wrapping it in a `<label>` and hiding the raw input lets it look like a styled button — clicking the label opens the same picker.
- **Storing the selected file**: the `change` event exposes `event.target.files`, a `FileList`. `files?.[0]` is the chosen `File` object (name, size, type, plus the binary data), assigned into the reactive `selectedFile` variable. Nothing is uploaded yet — just a reference held in memory.
- **Svelte 5 reactivity (runes)**:
  - `$state(...)` marks `selectedFile` as reactive — reassigning it triggers UI updates wherever it's used.
  - `$derived(...)` computes `uiState` automatically from `selectedFile`, so the two states can never drift out of sync with reality (no manual toggling).
  - The button's `disabled={uiState !== 'FILE_SELECTED'}` and the `{#if}` block both re-evaluate instantly when `selectedFile` changes.

**How to run and test**

```bash
cd frontend
npm run dev -- --open
```

1. Page loads at `http://localhost:5173` → heading, "Choose Video" button, and a disabled "Analyze Video" button (`IDLE` state).
2. Click "Choose Video", pick a video file → "Selected file: `<filename>`" appears and "Analyze Video" becomes enabled (`FILE_SELECTED` state).
3. Click "Analyze Video" → check the browser console for `Analyze clicked for: <filename>` (no network call yet, by design).

Verified with `npx svelte-check` (0 errors) and `npm run build` (succeeds).

### Step 2 — FastAPI Backend Foundation ✅

Built the backend foundation only: a FastAPI + Uvicorn project (`backend/`) with a single upload endpoint. No FFmpeg, Whisper, or Gemini integration yet, and not wired to the frontend — tested directly with `curl`.

**What was built**

- `backend/requirements.txt` — `fastapi`, `uvicorn[standard]`, `python-multipart`
- `backend/main.py` — the FastAPI app with:
  - `POST /api/analyze` — accepts a video file as `multipart/form-data`, validates its format, saves it to `backend/uploads/` under a random name, and returns a JSON confirmation
  - `GET /api/health` — a simple health-check endpoint used to confirm the server is running
- `backend/uploads/` — temp storage directory for uploaded videos (git-ignored, kept in git via `.gitkeep`)
- `backend/venv/` — a local virtual environment holding the installed dependencies (git-ignored)

**Code**

```python
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException

app = FastAPI(title="AI Video Knowledge Extractor")

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

    return {
        "success": True,
        "filename": file.filename,
        "message": "Video uploaded successfully",
    }
```

**Concepts**

- **FastAPI**: a Python web framework for building APIs. You declare routes as plain Python functions with type-hinted parameters, and FastAPI handles request parsing, validation, and response serialization automatically, plus generates interactive API docs (Swagger UI at `/docs`) for free.
- **API endpoint**: a specific URL + HTTP method combination that the server understands and responds to. `POST /api/analyze` is one endpoint; `GET /api/health` is another. The frontend will eventually call these URLs instead of talking to the pipeline directly.
- **`POST`**: an HTTP method meaning "send data to the server to create/process something," as opposed to `GET` (retrieve data). We use `POST` here because the client is submitting a file for the server to act on, not just fetching something.
- **`UploadFile`**: a FastAPI/Starlette type representing an uploaded file. Unlike reading the raw file into memory as `bytes`, `UploadFile` streams the data from disk/network in chunks, which keeps memory usage low even for large video files. It exposes `.filename`, `.content_type`, and async methods like `.read()`.
- **`multipart/form-data`**: the standard HTTP encoding for submitting files (and mixed form fields) in a request body. Unlike JSON, it can carry raw binary data efficiently, split into named "parts" — here there's one part named `file` containing the video's bytes.
- **How FastAPI receives the video**: the client sends a `POST` request with a `multipart/form-data` body. FastAPI sees the `file: UploadFile = File(...)` parameter, matches it to the `file` part of the request body, and hands the handler an `UploadFile` object — no manual parsing needed.
- **How the temporary file is created**: `Path(file.filename).suffix.lower()` extracts the extension (e.g. `.mp4`) for validation. A new name is generated with `uuid.uuid4()` (so two uploads named `video.mp4` never collide or overwrite each other), and `await file.read()` pulls the file's bytes into memory, which are then written to `backend/uploads/<uuid>.mp4` in binary mode (`"wb"`).
- **How the JSON response is generated**: FastAPI automatically serializes whatever Python dict a route function returns into a JSON HTTP response — no explicit `json.dumps` or content-type header needed. Returning `{"success": True, "filename": ..., "message": ...}` becomes the JSON body shown in the requirements.

**Code walkthrough (key lines)**

- `UPLOAD_DIR.mkdir(exist_ok=True)` — ensures the `uploads/` folder exists on startup; `exist_ok=True` avoids an error if it's already there.
- `ALLOWED_CONTENT_TYPES` / `ALLOWED_EXTENSIONS` — a basic two-layer format check: the browser-reported MIME type (`file.content_type`) and the filename's extension both have to be in the allow-list, since either one alone can be spoofed or missing.
- `raise HTTPException(status_code=400, detail=...)` — FastAPI's way of returning a non-200 error response; this becomes `{"detail": "Unsupported video format: ..."}` with HTTP status 400.
- `temp_filename = f"{uuid.uuid4()}{extension}"` — generates a collision-proof filename while preserving the original extension (needed later so FFmpeg/Whisper know the container format).
- `with open(temp_path, "wb") as buffer: buffer.write(await file.read())` — opens the destination file in binary write mode and writes the uploaded bytes; the `with` block guarantees the file handle is closed even if writing fails.

**How to test**

```bash
cd backend
python3 -m venv venv          # first time only
./venv/bin/pip install -r requirements.txt   # first time only
./venv/bin/uvicorn main:app --port 8000 --reload
```

Then, in another terminal:

```bash
# Health check
curl -s http://localhost:8000/api/health
# → {"status":"ok"}

# Valid upload
curl -s -X POST http://localhost:8000/api/analyze \
  -F "file=@/path/to/example.mp4;type=video/mp4"
# → {"success":true,"filename":"example.mp4","message":"Video uploaded successfully"}

# Invalid format
curl -s -X POST http://localhost:8000/api/analyze \
  -F "file=@/path/to/notes.txt;type=text/plain"
# → {"detail":"Unsupported video format: notes.txt"} (HTTP 400)
```

You can also open `http://localhost:8000/docs` for FastAPI's auto-generated Swagger UI, which lets you upload a file and try the endpoint from the browser without `curl`.

Verified manually: health check, a valid `.mp4` upload (saved to `backend/uploads/` under a UUID filename), and a rejected `.txt` upload — all behaved as expected.

### Step 3 — Connect Frontend to Backend ✅

Wired the SvelteKit "Analyze Video" button to the FastAPI `/api/analyze` endpoint. Clicking it now uploads the selected file for real and displays the JSON response. Still no FFmpeg, Whisper, or Gemini.

**What changed**

- `backend/main.py` — added `CORSMiddleware`, allowing requests from `http://localhost:5173` (the Vite dev server origin).
- `frontend/src/routes/+page.svelte` — `handleAnalyze` now builds a `FormData`, `fetch()`s the backend, and tracks new UI states: `UPLOADING` (shows "Uploading video..."), `DONE` (shows the JSON result), `ERROR` (shows the error message).

**Code — the API call**

```ts
const API_URL = 'http://localhost:8000/api/analyze';

async function handleAnalyze() {
	if (!selectedFile) return;

	uiState = 'UPLOADING';
	errorMessage = null;

	const formData = new FormData();
	formData.append('file', selectedFile);

	try {
		const response = await fetch(API_URL, {
			method: 'POST',
			body: formData
		});

		const data = await response.json();

		if (!response.ok) {
			throw new Error(data.detail ?? 'Upload failed');
		}

		result = data as AnalyzeResponse;
		uiState = 'DONE';
	} catch (err) {
		errorMessage = err instanceof Error ? err.message : 'Something went wrong';
		uiState = 'ERROR';
	}
}
```

**Code — backend CORS**

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Concepts**

- **`FormData`**: a browser API for building a `multipart/form-data` request body in JavaScript. `new FormData()` creates an empty form; `formData.append('file', selectedFile)` adds the `File` object under the field name `file` — matching the `file: UploadFile = File(...)` parameter name FastAPI expects on the backend. Passing a `FormData` object as `fetch`'s `body` makes the browser encode it correctly and set the right `Content-Type` header (including the multipart boundary) automatically — you should never set that header by hand.
- **Why `multipart/form-data` is required**: raw binary file data (video bytes) can't be safely embedded in a JSON string. `multipart/form-data` splits the request body into distinct parts with their own headers, so a file's raw bytes can be sent as-is alongside any other form fields. Since the backend's endpoint (Step 2) already expects `UploadFile`/`File(...)`, the frontend must send the matching encoding — JSON wouldn't parse there.
- **How `fetch()` sends the request**: `fetch(API_URL, { method: 'POST', body: formData })` opens an HTTP connection to the backend, sends the method, headers, and the `FormData` body, and returns a `Promise<Response>`. `await fetch(...)` pauses `handleAnalyze` until the server responds (or the request fails, e.g. network error) — `await response.json()` then pauses again while the response body is read and parsed as JSON.
- **How the frontend communicates with FastAPI**: the browser (frontend, `localhost:5173`) and the Python process (backend, `localhost:8000`) are two separate servers. `fetch` makes a plain HTTP request from one to the other — same mechanism as `curl`, just triggered by JS in response to a click instead of a terminal command.
- **CORS (Cross-Origin Resource Sharing)**: a browser security mechanism that blocks a page from one origin (`http://localhost:5173`) from reading responses from a different origin (`http://localhost:8000`) unless the server explicitly allows it. This restriction only applies to browser-made requests — `curl` isn't subject to it, which is why Step 2's testing worked fine without CORS configured, but the browser would have silently blocked the frontend's `fetch` without `CORSMiddleware`. The browser first sends an invisible `OPTIONS` "preflight" request asking permission; FastAPI's `CORSMiddleware` answers it and adds `Access-Control-Allow-Origin` headers to the real response.
- **How the response travels back**: FastAPI serializes the returned dict to JSON and sends it as the HTTP response body (Step 2). The browser receives it as the resolved value of the `fetch` promise; `response.json()` parses the body text back into a JS object, which is then stored in the reactive `result` variable — causing Svelte to re-render the `{#if uiState === 'DONE'}` block showing it.

**Code walkthrough (key lines)**

- `formData.append('file', selectedFile)` — the field name `'file'` must exactly match the backend's parameter name (`file: UploadFile = File(...)`); FastAPI matches multipart parts by name, not position.
- `uiState = 'UPLOADING'` set *before* the `fetch` call — this is what makes "Uploading video..." appear immediately, since Svelte re-renders as soon as the reactive variable changes, without waiting for the network request.
- `if (!response.ok) { throw new Error(data.detail ?? 'Upload failed') }` — `fetch` does **not** reject its promise on HTTP error statuses (like the 400 from an invalid format) — only on network failure. `response.ok` is `false` for any non-2xx status, so this check is what turns the backend's `{"detail": "..."}` error body into a JS error, driving the `ERROR` state.
- `try { ... } catch (err) { ... }` — catches both the thrown error above and genuine network errors (e.g., backend not running), so the UI always ends up in a resolved state (`DONE` or `ERROR`) rather than stuck on `UPLOADING`.
- The button's `disabled` condition was widened to allow re-clicking after `DONE` or `ERROR` (e.g. to retry), while still staying disabled in `IDLE` (no file yet) and `UPLOADING` (request in flight).

**How to test the complete flow**

Terminal 1:
```bash
cd backend
./venv/bin/uvicorn main:app --port 8000 --reload
```

Terminal 2:
```bash
cd frontend
npm run dev -- --open
```

Then in the browser (`http://localhost:5173`):
1. Click "Choose Video", select a video file.
2. Click "Analyze Video" → "Uploading video..." appears briefly.
3. The JSON response is displayed, e.g.:
   ```json
   {
     "success": true,
     "filename": "example.mp4",
     "message": "Video uploaded successfully"
   }
   ```
4. Check `backend/uploads/` — a new UUID-named file should appear there.
5. To see the error path, stop the backend server and click "Analyze Video" again — an error message should be shown instead of a hang.

Verified: `npx svelte-check` (0 errors), both dev servers start cleanly, a CORS preflight (`OPTIONS`) and POST from origin `http://localhost:5173` both return `access-control-allow-origin: http://localhost:5173` with a successful JSON body.

### Step 4 — FFmpeg Audio Extraction ✅

Added a dedicated audio-extraction service and wired it into `/api/analyze`. The endpoint now saves the video, runs it through FFmpeg, and returns the extracted audio's filename. No Whisper or Gemini yet.

**What was built**

- `backend/services/audio_extractor.py` — a service module with one function, `extract_audio(video_path) -> Path`, plus an `AudioExtractionError` exception for failures.
- `backend/main.py` — `/api/analyze` now calls `extract_audio()` after saving the video, and returns its output filename; FFmpeg failures are caught and turned into an HTTP 500 with a clear message.

**Code — the service**

```python
import subprocess
from pathlib import Path


class AudioExtractionError(Exception):
    pass


def extract_audio(video_path: Path) -> Path:
    audio_path = video_path.with_suffix(".wav")

    command = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(audio_path),
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
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
```

**Code — wiring into the endpoint**

```python
try:
    audio_path = extract_audio(temp_path)
except AudioExtractionError as exc:
    raise HTTPException(status_code=500, detail=str(exc))

return {
    "success": True,
    "filename": file.filename,
    "message": "Audio extracted successfully",
    "audio_file": audio_path.name,
}
```

**Concepts**

- **FFmpeg**: a command-line tool (and library) for reading, converting, and writing audio/video in essentially any format. It's the de facto standard for media processing — most video tools use it under the hood.
- **Why we need it**: our uploaded videos are `.mp4`/`.mov`/etc., which bundle a video stream and an audio stream together in one container. Whisper only understands raw audio, not video containers, so something has to pull the audio out first — that's FFmpeg's job here.
- **Codec (basic level)**: short for "coder-decoder" — the algorithm used to compress/decompress audio or video data into a specific format. `.mp4` files are typically video encoded with `h264` and audio encoded with `aac`; our output uses `pcm_s16le`, an *uncompressed* codec, because Whisper wants raw samples, not a compressed format it would have to decode again.
- **Audio stream**: within a video container, the audio and video are stored as separate "streams" multiplexed together. `-vn` ("no video") tells FFmpeg to drop the video stream entirely and keep only the audio stream when writing the output.
- **Why extract audio before Whisper**: Whisper's model operates on raw audio waveforms sampled at 16kHz mono — it has no concept of video frames, containers, or codecs. Feeding it a `.wav` file that already matches its expected format (16kHz, mono, PCM) avoids Whisper (or an intermediate library) having to do its own conversion, and keeps this step's responsibility clean: video → audio, nothing else.
- **How Python starts FFmpeg**: `subprocess.run(command, capture_output=True, text=True)` launches FFmpeg as a separate OS process (it's a compiled binary, not a Python library) and waits for it to finish. `capture_output=True` collects its stdout/stderr instead of printing them to the terminal; `text=True` decodes them as strings instead of raw bytes. The function returns a `CompletedProcess` object with `.returncode`, `.stdout`, and `.stderr`.

**The FFmpeg command, explained**

```
ffmpeg -y -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav
```

- `-y` — overwrite the output file without prompting (needed since we run this non-interactively; FFmpeg would otherwise hang waiting for a terminal "yes/no" answer).
- `-i video.mp4` — the input file.
- `-vn` — "video none": strip the video stream, output audio only.
- `-acodec pcm_s16le` — encode the output audio as 16-bit signed little-endian PCM (uncompressed) — Whisper's expected input format.
- `-ar 16000` — resample to a 16,000 Hz sample rate (Whisper was trained on 16kHz audio; other rates work but this avoids any internal resampling).
- `-ac 1` — downmix to 1 audio channel (mono) — stereo carries no useful extra information for speech transcription and just doubles the data.
- `audio.wav` — the output path (same name as the video, `.wav` extension, via `video_path.with_suffix(".wav")`).

**Service code walkthrough**

- `video_path.with_suffix(".wav")` — reuses the video's UUID-based name but swaps the extension, keeping video/audio pairs easy to correlate on disk.
- `command = [...]` as a list, not a single string — `subprocess.run` receives the executable and its arguments as separate list items, which avoids shell-quoting issues and shell-injection risk entirely (no shell is invoked, so no escaping of filenames is needed).
- `if result.returncode != 0` — FFmpeg (like most CLI tools) returns a non-zero exit code on failure; this is the standard way to detect the command failed, since `subprocess.run` doesn't raise an exception by default.
- Trimming `stderr` to its last non-empty line — FFmpeg always prints a long build/version banner before any real error, so surfacing the whole thing would bury the actually useful message; the last line is reliably the specific failure reason (e.g. "Invalid data found when processing input").
- `if not audio_path.exists()` — a defensive check in case FFmpeg exits `0` but somehow didn't produce the file (rare, but cheap to guard against).

**How temporary files are handled**

Both the uploaded video and the extracted audio are written to `backend/uploads/`, sharing the same UUID base name (e.g. `abc123.mp4` → `abc123.wav`). Nothing is cleaned up automatically yet in this step — files accumulate in `uploads/` across requests. That's acceptable for now since the goal here is correctness of the extraction step; a later step can add cleanup (e.g. deleting the video/audio after the full pipeline finishes, or a scheduled sweep of old files) once the full pipeline exists and we know what "done" looks like.

**How to manually verify the audio file was created**

```bash
cd backend
./venv/bin/uvicorn main:app --port 8000 --reload
```

```bash
curl -s -X POST http://localhost:8000/api/analyze \
  -F "file=@/path/to/example.mp4;type=video/mp4"
# → {"success":true,"filename":"example.mp4","message":"Audio extracted successfully","audio_file":"<uuid>.wav"}
```

Then confirm the file physically exists and is a valid audio file:

```bash
ls backend/uploads/
# should show both <uuid>.mp4 and <uuid>.wav

ffprobe backend/uploads/<uuid>.wav
# should report: Stream #0:0: Audio: pcm_s16le ..., 16000 Hz, 1 channels, s16
```

You can also just play it: `ffplay backend/uploads/<uuid>.wav` (or open it in any media player) to confirm it contains the video's actual audio.

**Verified**: generated a real test video with FFmpeg (`testsrc` + `sine` tone), uploaded it through `/api/analyze`, and confirmed via `ffprobe` that the output `.wav` is exactly `pcm_s16le, 16000 Hz, 1 channels` as intended. Also confirmed the error path: uploading a corrupt/fake `.mp4` returns a clean HTTP 500 with FFmpeg's actual error message (not the noisy version banner).

### Step 5 — Whisper Speech-to-Text ✅

Added a transcription service using `openai-whisper` and wired it into `/api/analyze`. The endpoint now runs the full video → audio → transcript pipeline and returns the transcript in the JSON response (temporary — Step 6 will replace this raw passthrough once Gemini summarization is added). No Gemini yet.

**What was built**

- `backend/requirements.txt` — added `openai-whisper` (pulls in PyTorch as a dependency).
- `backend/services/transcriber.py` — a service module with `transcribe_audio(audio_path) -> str`, plus a `TranscriptionError` exception.
- `backend/main.py` — `/api/analyze` now calls `transcribe_audio()` after extracting audio, and returns the transcript text.

**Code — the service**

```python
from functools import lru_cache
from pathlib import Path

import whisper


class TranscriptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_model():
    # device="cpu" is explicit: auto-detection picks up any visible CUDA
    # device even if its compute capability isn't supported by the
    # installed torch build, which fails loudly at inference time.
    return whisper.load_model("tiny", device="cpu")


def transcribe_audio(audio_path: Path) -> str:
    try:
        model = _get_model()
        result = model.transcribe(str(audio_path))
    except Exception as exc:
        raise TranscriptionError(
            f"Whisper failed to transcribe {audio_path.name}: {exc}"
        )

    return result["text"].strip()
```

**Code — wiring into the endpoint**

```python
try:
    transcript = transcribe_audio(audio_path)
except TranscriptionError as exc:
    raise HTTPException(status_code=500, detail=str(exc))

return {
    "success": True,
    "filename": file.filename,
    "message": "Transcription completed successfully",
    "audio_file": audio_path.name,
    "transcript": transcript,
}
```

**Concepts**

- **Speech-to-text**: the general task of converting spoken audio into written text. It's the bridge between "a video says something" and "an LLM can read and reason about it" — everything downstream (summarization, key points) operates on text, not audio.
- **What Whisper is**: an open-source speech recognition model (originally released by OpenAI) trained on a huge, diverse dataset of audio paired with transcripts. It's not a rule-based system — it's a neural network that learned the mapping from raw audio waveforms to text, and it generalizes well across accents, background noise, and topics.
- **How Whisper processes audio**: it's an encoder-decoder transformer. The encoder converts the audio waveform (as a spectrogram) into an internal numerical representation; the decoder then generates text tokens one at a time based on that representation, similar to how an LLM generates text token-by-token — except conditioned on audio instead of a text prompt.
- **What a "model" means here**: a model is the trained neural network's parameters (weights) — essentially a large file of numbers learned during training, plus code to run inference with them. `whisper.load_model("tiny")` downloads (once, then caches locally) and loads the "tiny" variant — Whisper ships several sizes (`tiny`, `base`, `small`, `medium`, `large`) trading off speed vs. accuracy. We use `tiny` here for fast local CPU inference during development; a production deployment might use a larger model or a GPU.
- **What the Whisper output contains**: `model.transcribe()` returns a dict with more than just text — including `"text"` (the full transcript), `"segments"` (timestamped chunks with per-segment text, start/end times, and confidence-related fields), and `"language"` (detected spoken language). We only use `"text"` for now; `"segments"` could later support timestamped key points or subtitles.
- **How the transcript is extracted**: `result["text"].strip()` — pulls just the full transcript string out of Whisper's richer result dict, and strips leading/trailing whitespace Whisper sometimes includes.
- **Why transcription happens before Gemini**: Gemini (and LLMs generally) work on text, not audio or video — there's no way to hand Gemini the raw video and get a summary directly. Whisper's transcript is the necessary intermediate artifact that turns unstructured media into text Gemini can actually read and summarize.

**Service code walkthrough**

- `@lru_cache(maxsize=1)` on `_get_model()` — loading Whisper's weights from disk into memory is slow (multiple seconds), so this ensures it only happens once per server process, on the first request, and every subsequent request reuses the already-loaded model in memory.
- `device="cpu"` — explicit and necessary here: this machine has an older NVIDIA GPU (compute capability 5.0) that the installed PyTorch build doesn't include kernels for, so letting Whisper auto-select a device would crash at inference time with a CUDA error. Forcing CPU sidesteps that entirely; if you have a supported GPU, changing this to `"cuda"` would speed up transcription significantly.
- `model.transcribe(str(audio_path))` — Whisper takes a file path (or a raw waveform array) and runs the full encode → decode pipeline, returning the result dict described above.
- `except Exception as exc` — deliberately broad here, unlike the narrower FFmpeg error handling, because Whisper/PyTorch can fail in many different ways (corrupt audio, model loading issues, out-of-memory, unsupported hardware) and we want all of them surfaced as a clean `TranscriptionError` rather than an unhandled 500 with a raw stack trace.

**How the complete pipeline works now**

```text
POST /api/analyze (multipart/form-data)
    ↓
1. Validate format, save video to backend/uploads/<uuid>.mp4
    ↓
2. extract_audio(): FFmpeg → backend/uploads/<uuid>.wav (16kHz mono PCM)
    ↓
3. transcribe_audio(): Whisper (tiny, CPU) → transcript string
    ↓
4. Return { success, filename, message, audio_file, transcript } as JSON
```

Each step's failure is caught independently and turned into a specific HTTP error (400 for bad format, 500 for FFmpeg or Whisper failures), so a failure at any stage produces a clear message rather than a generic crash.

**How to test it with a short video**

```bash
cd backend
./venv/bin/uvicorn main:app --port 8000 --reload
```

```bash
curl -s -X POST http://localhost:8000/api/analyze \
  -F "file=@/path/to/short_clip.mp4;type=video/mp4"
```

Expected response shape:

```json
{
  "success": true,
  "filename": "short_clip.mp4",
  "message": "Transcription completed successfully",
  "audio_file": "<uuid>.wav",
  "transcript": "Whatever is spoken in the video, as text."
}
```

The first request after starting the server will be noticeably slower (Whisper downloads the `tiny` model, ~72MB, on first use, then loads it into memory); subsequent requests reuse the cached model and are much faster.

**Verified**: generated a short test video with real speech (a synthesized voice reading a known sentence) and confirmed the returned `transcript` matched the spoken sentence almost exactly. Also confirmed the second request completed in under a second, proving the model-caching (`lru_cache`) works as intended and the model isn't reloaded per-request.

### Step 6 — Gemini Summarization ✅

Added a Gemini service that takes Whisper's transcript and produces a `summary` plus `key_points`, wired into `/api/analyze`. Gemini only ever receives the transcript text — never the video or audio. This completes the full V1 pipeline: Video → FFmpeg → Whisper → Gemini → `{ transcript, summary, key_points }`.

**What was built**

- `backend/requirements.txt` — added `google-genai` (the Gemini API SDK) and `python-dotenv`.
- `backend/services/summarizer.py` — `summarize_transcript(transcript) -> dict`, plus a `SummarizationError` exception.
- `backend/.env` (git-ignored) — holds `GEMINI_API_KEY`, loaded at startup.
- `backend/.env.example` — a committed template showing the required variable name without a real value.
- `backend/main.py` — loads `.env` via `load_dotenv()`, calls `summarize_transcript()` after transcription, and returns `summary`/`key_points` alongside `transcript` (dropped the now-redundant `audio_file` from the response).

**Code — the service**

```python
import json
import os

from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.6-flash"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "key_points"],
}

PROMPT_TEMPLATE = """You are given the transcript of a video. Read it and produce:
- A concise summary of what the video is about.
- A list of the key points made in the video.

Base your answer only on the transcript text below. Do not invent details
that aren't in it.

Transcript:
\"\"\"
{transcript}
\"\"\"
"""


class SummarizationError(Exception):
    pass


def summarize_transcript(transcript: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SummarizationError("GEMINI_API_KEY environment variable is not set")

    client = genai.Client(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(transcript=transcript)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
            ),
        )
    except Exception as exc:
        raise SummarizationError(f"Gemini request failed: {exc}")

    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SummarizationError(f"Gemini returned invalid JSON: {exc}")
```

**Code — wiring into the endpoint**

```python
try:
    analysis = summarize_transcript(transcript)
except SummarizationError as exc:
    raise HTTPException(status_code=500, detail=str(exc))

return {
    "success": True,
    "filename": file.filename,
    "message": "Video analyzed successfully",
    "transcript": transcript,
    "summary": analysis["summary"],
    "key_points": analysis["key_points"],
}
```

**Concepts**

- **What an LLM is**: a large language model — a neural network trained on huge amounts of text that learns statistical patterns of language well enough to read, reason about, and generate coherent text. Gemini is Google's LLM family; we're using it purely for its text-understanding ability here, not any video/image capability.
- **What the Gemini API is**: a hosted HTTP API that lets any application send text (a "prompt") to a Gemini model running on Google's infrastructure and get generated text back. We never run the model ourselves — the `google-genai` SDK just wraps the HTTP calls in a convenient Python client.
- **How an API key works**: a secret string tied to a Google account/project that identifies and authorizes the caller. Every request to `client.models.generate_content(...)` includes it (handled internally by the SDK); Google uses it for billing, rate-limiting, and access control. Anyone holding a valid key can make requests and consume that account's quota — which is exactly why it must stay secret.
- **Why the key belongs only in the backend**: the backend (Python/FastAPI) runs on a server we control and never ships its source or environment to the browser. The frontend (SvelteKit) runs entirely in the user's browser — any value embedded in frontend code or a frontend `.env` (even ones prefixed for "public" use) is visible to anyone who opens dev tools or views page source. If the Gemini key were in the frontend, anyone could extract it and rack up API usage on our account. Keeping it in `backend/.env`, read only by server-side Python via `os.environ.get(...)`, means it never leaves our server.
- **What a prompt is**: the text instruction sent to an LLM describing what we want it to do. `PROMPT_TEMPLATE` here explicitly tells Gemini its task (summarize + extract key points), constrains it to the transcript only ("do not invent details"), and embeds the transcript itself — the model has no other context beyond what's in this string.
- **How the transcript is passed to Gemini**: `PROMPT_TEMPLATE.format(transcript=transcript)` interpolates Whisper's output text directly into the prompt string, which is then sent as `contents=prompt` in the API call — plain text in, plain text (JSON-shaped) out. No audio, video, or files are ever sent to Gemini.
- **What structured JSON output means**: normally an LLM just generates free-form text, which is fragile to parse (it might add extra commentary, use different formatting, etc.). Gemini's `response_mime_type="application/json"` combined with a `response_schema` constrains the model's output generation so that what comes back is guaranteed to be valid JSON matching the given shape (`summary: string`, `key_points: string[]`) — no manual regex-scraping or hoping the model "behaves."

**Gemini service code walkthrough**

- `RESPONSE_SCHEMA` — a JSON Schema describing exactly the shape from the requirements: an object with a `summary` string and a `key_points` array of strings, both required. This is passed straight to Gemini's `response_schema` config, not just documentation.
- `api_key = os.environ.get("GEMINI_API_KEY")` + the `if not api_key` check — fails fast with a clear message if the environment variable is missing, rather than letting the SDK raise a more confusing error later.
- `genai.Client(api_key=api_key)` — constructs the API client for this request. (For a busier app this could be created once at module load instead of per-call; kept simple here since correctness, not performance, is the goal of this step.)
- `response_mime_type="application/json"` + `response_schema=RESPONSE_SCHEMA` — the two config values that turn on structured output mode, described above.
- `except Exception as exc` around the API call — broad on purpose: network errors, invalid API keys, rate limits, and model errors are all real possibilities and should all become a clean `SummarizationError` rather than an unhandled exception.
- `json.loads(response.text)` — even with structured output, the SDK still hands back the JSON as a text string (`response.text`); we parse it into a real Python dict so `main.py` can pull `analysis["summary"]` and `analysis["key_points"]` out directly.
- The second `try/except` around `json.loads` — a defensive fallback in case the model ever returns malformed JSON despite the schema constraint (rare, but not impossible).

**The complete flow, end to end**

```text
POST /api/analyze (multipart/form-data, one video file)
    ↓
1. Validate format → save video to backend/uploads/<uuid>.mp4
    ↓
2. extract_audio(): FFmpeg → backend/uploads/<uuid>.wav (16kHz mono PCM)
    ↓
3. transcribe_audio(): Whisper (tiny, CPU) → transcript string
    ↓
4. summarize_transcript(): Gemini (text-only, transcript in → JSON out) → { summary, key_points }
    ↓
5. Return { success, filename, message, transcript, summary, key_points } as JSON
    ↓
SvelteKit displays the result (already wired up since Step 3)
```

Every stage fails independently and cleanly: unsupported format → 400, FFmpeg failure → 500, Whisper failure → 500, Gemini failure (including a missing API key) → 500 — each with a message naming exactly which stage failed.

**How to test the Gemini integration**

1. Get a free API key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. Create `backend/.env` (copy `backend/.env.example`) and set `GEMINI_API_KEY=<your key>`.
3. Start the backend:
   ```bash
   cd backend
   ./venv/bin/uvicorn main:app --port 8000 --reload
   ```
4. Send a video with real, substantive speech (a single short sentence will produce a fairly trivial summary — a short lecture-style clip demonstrates it better):
   ```bash
   curl -s -X POST http://localhost:8000/api/analyze \
     -F "file=@/path/to/clip.mp4;type=video/mp4"
   ```
5. Expected response shape:
   ```json
   {
     "success": true,
     "filename": "clip.mp4",
     "message": "Video analyzed successfully",
     "transcript": "...",
     "summary": "...",
     "key_points": ["...", "...", "..."]
   }
   ```
6. To test the failure path, temporarily rename/remove `GEMINI_API_KEY` from `.env`, restart the server, and confirm you get a clean `500` with `"detail": "GEMINI_API_KEY environment variable is not set"` instead of a crash.

**Verified**: tested live with a real Gemini API key against a ~30-second synthesized lecture about the water cycle. The returned `summary` and `key_points` accurately reflected the transcript's content (evaporation/condensation/precipitation), confirming both the API call and the structured-JSON parsing work correctly. Also confirmed the missing-key error path returns a clean message rather than a stack trace. Note: the model name required a bump mid-testing — Gemini's API returned a `404` for `gemini-2.5-flash` ("no longer available to new users"), so the service uses `gemini-3.6-flash` instead; if you hit a similar `404` in the future, check Gemini's current model list and update `MODEL_NAME` in `summarizer.py`.

### Step 7 — Connect the Complete Backend Pipeline ✅

The three services (FFmpeg, Whisper, Gemini) were already being called in sequence since Step 6 — this step tightened the orchestration in `/api/analyze`: trimmed the response to exactly the required shape, and added cleanup so temporary video/audio files don't accumulate on disk across requests. No new technology introduced.

**What changed in `backend/main.py`**

```python
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
```

Two concrete changes from Step 6:
- The response now returns exactly `{ success, summary, key_points, transcript }` — dropped `filename` and `message`, which weren't part of the required shape.
- The whole three-stage pipeline is wrapped in `try: ... finally: ...`, which deletes the uploaded video and the extracted audio file after the request completes — whether it succeeded or failed at any stage.

**Concepts**

- **How the services communicate**: directly, through plain Python function calls and return values — no message queue, no shared state, no network hop between them (they all run in-process). `extract_audio()` returns a `Path`, which is passed straight into `transcribe_audio()`; that returns a `str`, passed straight into `summarize_transcript()`. Each function's output type is exactly the next function's input type — that's the whole "interface" between them.
- **What the API route is responsible for**: orchestration only — validating the upload, calling the three services in the right order, translating each service's specific exception into the right HTTP error, shaping the final JSON response, and guaranteeing cleanup. It contains zero FFmpeg/Whisper/Gemini logic itself; all of that lives in `services/`. This is the "thin route, fat services" split — the route reads top-to-bottom as the pipeline diagram, with the actual work delegated out.
- **Why service separation is useful**: each service (`audio_extractor.py`, `transcriber.py`, `summarizer.py`) can be understood, tested, and changed in isolation — e.g. swapping Whisper's model size, or switching Gemini for another LLM, only touches one file and one function signature, not the route. It also means each stage's failure mode is distinct and independently handled (a `TranscriptionError` can't be confused with a `SummarizationError`), which is what makes the route's three separate `try/except` blocks possible and readable.
- **How the complete request flows through the backend**: described step-by-step below.
- **What happens if FFmpeg fails**: `extract_audio()` raises `AudioExtractionError` (e.g. corrupt video, unsupported codec). The route catches it and raises `HTTPException(500, detail=<ffmpeg's error line>)`. Whisper and Gemini are never called. The `finally` block still runs, deleting the saved video (there's no audio file to delete yet, since `audio_path` is still `None`).
- **What happens if Whisper fails**: `transcribe_audio()` raises `TranscriptionError` (e.g. corrupt audio, an unsupported/unloadable model, an out-of-memory error). The route catches it and raises `HTTPException(500, ...)`. Gemini is never called. The `finally` block deletes both the video and the audio file, since `audio_path` was already set by the (successful) FFmpeg step.
- **What happens if Gemini fails**: `summarize_transcript()` raises `SummarizationError` (e.g. missing/invalid API key, network failure, malformed JSON response). The route catches it and raises `HTTPException(500, ...)`. By this point FFmpeg and Whisper have already succeeded — their output isn't wasted computationally, but it's still not returned to the client, since there's no complete result without a summary. The `finally` block still deletes both temp files.

**The complete backend flow, step by step**

```text
1. Client sends POST /api/analyze with a video file (multipart/form-data)
2. Route validates the file extension + content type → 400 if unsupported
3. Route saves the video to backend/uploads/<uuid>.mp4
4. Route calls extract_audio(video_path)
   → FFmpeg runs as a subprocess, writes <uuid>.wav
   → on failure: 500, jump to step 8 (cleanup)
5. Route calls transcribe_audio(audio_path)
   → Whisper (tiny, CPU) loads (or reuses the cached model) and transcribes
   → on failure: 500, jump to step 8 (cleanup)
6. Route calls summarize_transcript(transcript)
   → Gemini receives only the transcript text, returns structured JSON
   → on failure: 500, jump to step 8 (cleanup)
7. Route returns { success: true, summary, key_points, transcript } as the HTTP response
8. finally: delete the video file and (if it was created) the audio file, regardless of
   whether step 4-7 succeeded or raised
```

Steps 4, 5, and 6 are each a single call into a separate service module — the route itself never touches FFmpeg, Whisper, or Gemini APIs directly.

**Verified**: re-tested all three failure modes plus the success path against a running server:
- Success (30s lecture video) → correct `{ success, summary, key_points, transcript }` shape, and `backend/uploads/` was empty (just `.gitkeep`) immediately after.
- FFmpeg failure (corrupt `.mp4`) → clean `500` with FFmpeg's error, `uploads/` empty afterward (video deleted, no audio was ever created).
- Edge case: a silent video (no speech) flowed through all three stages successfully — Whisper returned an empty transcript, and Gemini correctly responded with an empty `summary`/`key_points` rather than erroring — and `uploads/` was still cleaned up.

### Step 8 — Complete the SvelteKit UI ✅

Updated the frontend to match the final backend response shape and display the full result: summary, key points, and transcript. Renamed the UI states to match the spec (`UPLOADING`→`PROCESSING`, `DONE`→`SUCCESS`). This completes the V1 pipeline end-to-end, frontend included.

**What changed in `frontend/src/routes/+page.svelte`**

- `UiState` is now `'IDLE' | 'FILE_SELECTED' | 'PROCESSING' | 'SUCCESS' | 'ERROR'`.
- `AnalyzeResponse` now matches the backend exactly: `{ success, summary, key_points, transcript }` (previously had `filename`/`message`, which the backend no longer returns as of Step 7).
- A new `.results` section renders only in the `SUCCESS` state, showing Summary, Key Points (as a bullet list), and Transcript, each under its own heading with a divider — matching the requested layout.

**Code — state and the API call**

```ts
type UiState = 'IDLE' | 'FILE_SELECTED' | 'PROCESSING' | 'SUCCESS' | 'ERROR';

type AnalyzeResponse = {
	success: boolean;
	summary: string;
	key_points: string[];
	transcript: string;
};

let selectedFile: File | null = $state(null);
let uiState: UiState = $state('IDLE');
let result: AnalyzeResponse | null = $state(null);
let errorMessage: string | null = $state(null);

async function handleAnalyze() {
	if (!selectedFile) return;

	uiState = 'PROCESSING';
	errorMessage = null;

	const formData = new FormData();
	formData.append('file', selectedFile);

	try {
		const response = await fetch(API_URL, { method: 'POST', body: formData });
		const data = await response.json();

		if (!response.ok) {
			throw new Error(data.detail ?? 'Analysis failed');
		}

		result = data as AnalyzeResponse;
		uiState = 'SUCCESS';
	} catch (err) {
		errorMessage = err instanceof Error ? err.message : 'Something went wrong';
		uiState = 'ERROR';
	}
}
```

**Code — the result display**

```svelte
{#if uiState === 'SUCCESS' && result}
	<section class="results">
		<h2>Summary</h2>
		<hr />
		<p>{result.summary}</p>

		<h2>Key Points</h2>
		<hr />
		<ul>
			{#each result.key_points as point}
				<li>{point}</li>
			{/each}
		</ul>

		<h2>Transcript</h2>
		<hr />
		<p class="transcript">{result.transcript}</p>
	</section>
{/if}
```

**Concepts**

- **How the frontend calls the backend**: unchanged mechanism from Step 3 — `fetch(API_URL, { method: 'POST', body: formData })` sends the video as `multipart/form-data` to `POST /api/analyze` and awaits the JSON response. What's new is only the shape of the data coming back.
- **How the response is stored**: `result = data as AnalyzeResponse` assigns the parsed JSON into a `$state` variable. Because `result` is reactive, everything in the template that reads `result.summary`, `result.key_points`, or `result.transcript` automatically re-renders the moment this assignment happens — no manual DOM updates anywhere.
- **How Svelte updates the UI**: this app is driven entirely by `{#if}` blocks keyed on `uiState` — `IDLE`/`FILE_SELECTED` show the upload controls, `PROCESSING` shows the loading message, `ERROR` shows the error text, and `SUCCESS` reveals the `.results` section. Since `uiState` and `result` are both `$state`, Svelte's compiler has already wired up exactly which DOM nodes depend on which variables — reassigning either one is enough to trigger the correct, minimal re-render.
- **How loading state works**: `uiState = 'PROCESSING'` is set synchronously, before the `await fetch(...)` call. Since that assignment happens on the main thread before any network I/O starts, Svelte re-renders "Processing video..." immediately — the user doesn't wait for the network for the loading indicator to appear, only for the result.
- **How errors are displayed**: the `catch` block catches both explicit `throw new Error(...)` (a non-2xx response, e.g. the backend's 500 with a `detail` message) and unexpected failures (e.g. the backend not running, causing `fetch` itself to reject). Either way, `errorMessage` is set and `uiState` becomes `'ERROR'`, which the template shows as a red `<p class="error">`.

**Frontend code walkthrough (key lines)**

- `type AnalyzeResponse = { success: boolean; summary: string; key_points: string[]; transcript: string }` — a TypeScript type mirroring the backend's exact JSON shape (Step 7). If the backend's shape ever changes again, TypeScript will flag any code in this file that assumes the old shape.
- `{#each result.key_points as point}<li>{point}</li>{/each}` — Svelte's list-rendering syntax; iterates the `key_points` array and renders one `<li>` per string, producing the bulleted list.
- `class="transcript"` with `white-space: pre-wrap` in the `<style>` block — ensures the transcript (a single long string with no HTML line breaks) still wraps naturally and doesn't overflow the page, since `<p>` collapses whitespace by default.
- The disabled condition on the Analyze button (`uiState !== 'FILE_SELECTED' && uiState !== 'SUCCESS' && uiState !== 'ERROR'`) is unchanged from Step 3 — it's what allows re-clicking "Analyze Video" to retry after either a completed result or a failure.

**The complete application flow, beginning to end**

```text
1. User opens the SvelteKit app → uiState = IDLE, Analyze button disabled
2. User clicks "Choose Video", picks a file → uiState = FILE_SELECTED, Analyze enabled
3. User clicks "Analyze Video" → uiState = PROCESSING, "Processing video..." shown
4. Frontend builds FormData, sends POST /api/analyze to FastAPI
5. Backend: validates format → saves video → FFmpeg extracts audio →
   Whisper transcribes → Gemini summarizes → cleans up temp files →
   returns { success, summary, key_points, transcript }
6. Frontend receives the JSON response
     - on success: result is stored, uiState = SUCCESS → Summary, Key Points,
       and Transcript sections render
     - on failure (any stage): errorMessage is stored, uiState = ERROR →
       error message renders instead
7. User can pick a new file or click Analyze again to retry
```

**How to test**

Terminal 1:
```bash
cd backend
./venv/bin/uvicorn main:app --port 8000 --reload
```

Terminal 2:
```bash
cd frontend
npm run dev -- --open
```

In the browser: choose a video with real speech, click "Analyze Video", watch "Processing video..." appear, then confirm the Summary, Key Points (bulleted), and Transcript sections render with real content from the backend. To test the error path, stop the backend and click Analyze again — a red error message should appear instead of a hang.

**Verified**: `npx svelte-check` (0 errors) and `npm run build` both pass with the updated component. Confirmed via `curl` (sending the same `Origin: http://localhost:5173` header a real browser would) that the backend's response shape exactly matches the frontend's `AnalyzeResponse` type — `{ success, summary, key_points, transcript }` — with no field mismatches.
