import json
import os

from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.1-flash-lite"

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
