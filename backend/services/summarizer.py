import json
import os
import time

import httpx
from google import genai
from google.genai import types

from services.gemini_models import GeminiUnavailableError, call_with_fallback

MODEL_NAME = "gemini-3.5-flash-lite"

# The SDK has no default timeout, so a stuck request would hang the whole
# analysis. A long roadmap can legitimately take a couple of minutes.
REQUEST_TIMEOUT_MS = 240_000

TOPIC_PROPERTIES = {
    "heading": {"type": "string"},
    "content": {"type": "string"},
    "example": {"type": "string"},
    "related": {
        "type": "array",
        "items": {"type": "string"},
    },
    "resources": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["article", "video"]},
                "title": {"type": "string"},
            },
            "required": ["type", "title"],
        },
    },
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "intro": {"type": "string"},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
        },
        "roadmap": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    **TOPIC_PROPERTIES,
                    "children": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": TOPIC_PROPERTIES,
                            "required": ["heading", "content"],
                        },
                    },
                },
                "required": ["heading", "content"],
            },
        },
    },
    "required": ["intro", "key_points", "roadmap"],
}

PROMPT_TEMPLATE = """You are given the transcript of a video. Read it and produce a
structured breakdown, laid out as a learning roadmap (like the topic trees on
roadmap.sh) instead of one long summary:

- "intro": a short paragraph introducing what the video is about.
- "key_points": a bullet-point list (3-8 items) of the most important
  takeaways from the whole video, each a short standalone sentence someone
  could skim to get the gist without reading anything else.
- "roadmap": the video's topics laid out as a tree. Each top-level item is a
  main topic/step in the order the video builds them up (like the main
  vertical path on a roadmap.sh chart). If a main topic has closely related
  sub-points, side notes, or supporting details discussed alongside it, put
  those under its "children" as branch nodes (like roadmap.sh's side
  branches) instead of making them separate top-level topics. Not every topic
  needs children — only add them when the video actually treats something as
  a sub-point of a bigger topic, not just because a slot is available.

Each topic (top-level or child) has:
- "heading": short topic name.
- "content": a thorough, in-depth explanation of that topic, not a one-line
  summary. Cover what was said, how it was reasoned or justified, and any
  nuance, caveats, or steps the speaker walked through, in multiple sentences
  (a short paragraph). A reader should be able to understand that topic fully
  from your explanation without needing to watch the video.
- "example": the actual concrete example given in the transcript for that
  point, not a generic or theoretical one you made up. If the speaker shows
  or reads out code, quote that exact code (verbatim, preserving syntax). If
  they walk through a specific case, number, command, or scenario, quote or
  closely paraphrase that specific instance rather than describing it
  abstractly. Only omit "example" if the transcript truly gives no concrete
  instance for that topic.
- "related": a list of the exact "heading" strings of OTHER topics elsewhere
  in this same roadmap (top-level or child, anywhere in the tree) that are
  genuinely relevant background or follow-up for this one — e.g. this topic
  builds on that one, or that one goes deeper into something mentioned here.
  Every heading listed must be copied exactly as it appears elsewhere in your
  own output. Omit "related" (or leave it empty) if nothing else in the
  roadmap is genuinely related — don't force connections.

Base your answer only on the transcript text below. Do not invent details
that aren't in it.

{language_instruction}

Transcript:
\"\"\"
{transcript}
\"\"\"
"""


class SummarizationError(Exception):
    pass


def _timeout_ms(time_budget_seconds: float | None) -> int:
    if time_budget_seconds is None:
        return REQUEST_TIMEOUT_MS
    return max(1_000, min(REQUEST_TIMEOUT_MS, int(time_budget_seconds * 1000)))


def summarize_transcript(
    transcript: str, target_language: str | None = None, time_budget_seconds: float | None = None
) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SummarizationError("GEMINI_API_KEY environment variable is not set")

    client = genai.Client(api_key=api_key)
    language_instruction = (
        f"Write your entire response (intro, key_points, and every roadmap "
        f"field) in {target_language}, regardless of what language the "
        f"transcript is in."
        if target_language
        else ""
    )
    prompt = PROMPT_TEMPLATE.format(transcript=transcript, language_instruction=language_instruction)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                http_options=types.HttpOptions(timeout=_timeout_ms(time_budget_seconds)),
            ),
        )
    except httpx.TimeoutException:
        raise SummarizationError("The AI took too long to build the roadmap. Please try again.")
    except Exception as exc:
        raise SummarizationError(f"Gemini request failed: {exc}")

    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SummarizationError(f"Gemini returned invalid JSON: {exc}")


# --- One-call analysis: Gemini watches/listens to the media and writes the
# roadmap directly. Skips the separate verbatim-transcription call (a long,
# slow output that was only ever used as input to the roadmap). ---

MEDIA_PROMPT_TEMPLATE = (
    PROMPT_TEMPLATE.split('Transcript:\n"""', 1)[0]
    .replace("You are given the transcript of a video. Read it and produce a", "You are given a video (or its audio). Watch/listen to it and produce a")
    .replace("Base your answer only on the transcript text below.", "Base your answer only on what is said and shown in it.")
    .replace("the transcript", "the video")
    + """Also set "language" to the ISO 639-1 code of the main spoken language in
the video (e.g. "en", "hi"), regardless of the output language.
"""
)

MEDIA_RESPONSE_SCHEMA = {
    **RESPONSE_SCHEMA,
    "properties": {**RESPONSE_SCHEMA["properties"], "language": {"type": "string"}},
    "required": [*RESPONSE_SCHEMA["required"], "language"],
}

# Only the speech matters, so have Gemini sample YouTube frames rarely and at
# low resolution - far fewer tokens to process per minute of video.
YOUTUBE_FRAMES_PER_SECOND = 0.2
DEFAULT_MEDIA_TIME_BUDGET_SECONDS = 210


def summarize_media(
    file_uri: str,
    mime_type: str | None = None,
    youtube: bool = False,
    target_language: str | None = None,
    time_budget_seconds: float | None = None,
) -> dict:
    """Roadmap straight from a YouTube URL (`youtube=True`) or an uploaded
    Gemini file URI, in one call. Returns the same shape as
    summarize_transcript plus "language" (detected spoken language)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SummarizationError("GEMINI_API_KEY environment variable is not set")
    client = genai.Client(api_key=api_key)

    language_instruction = (
        f"Write your entire response (intro, key_points, and every roadmap "
        f"field) in {target_language}, regardless of what language the "
        f"video is in."
        if target_language
        else ""
    )
    prompt = MEDIA_PROMPT_TEMPLATE.format(language_instruction=language_instruction)

    plain_media = types.Part(file_data=types.FileData(file_uri=file_uri, mime_type=mime_type))
    if youtube:
        media = types.Part(
            file_data=types.FileData(file_uri=file_uri),
            video_metadata=types.VideoMetadata(fps=YOUTUBE_FRAMES_PER_SECOND),
        )
        resolution = types.MediaResolution.MEDIA_RESOLUTION_LOW
    else:
        media, resolution = plain_media, None

    def generate(model: str, timeout_ms: int, part: types.Part, media_resolution) -> dict:
        response = client.models.generate_content(
            model=model,
            contents=types.Content(parts=[part, types.Part(text=prompt)]),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MEDIA_RESPONSE_SCHEMA,
                media_resolution=media_resolution,
                http_options=types.HttpOptions(timeout=timeout_ms),
            ),
        )
        result = json.loads(response.text)
        if not isinstance(result.get("roadmap"), list):
            raise ValueError("Gemini returned no roadmap")
        return result

    def call(model: str, timeout_ms: int) -> dict:
        try:
            return generate(model, timeout_ms, media, resolution)
        except Exception as exc:
            if not youtube or "INVALID_ARGUMENT" not in str(exc):
                raise
            # This model doesn't accept the low-cost video settings.
            return generate(model, timeout_ms, plain_media, None)

    deadline = time.monotonic() + (time_budget_seconds or DEFAULT_MEDIA_TIME_BUDGET_SECONDS)
    try:
        result = call_with_fallback(call, deadline, "Video analysis")
    except GeminiUnavailableError as exc:
        if exc.quota_exhausted:
            raise SummarizationError(
                "GEMINI_QUOTA: The AI service's usage limit has been reached for now, so this video "
                "couldn't be analyzed. Please try again later (the limit resets daily)."
            )
        raise SummarizationError(
            "GEMINI_BUSY: The AI service is overloaded right now and couldn't analyze this video in time. "
            "Please try again in a few minutes."
        )

    result["language"] = (result.get("language") or "").strip().lower() or None
    return result
