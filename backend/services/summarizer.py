import json
import os

from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.5-flash-lite"

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
