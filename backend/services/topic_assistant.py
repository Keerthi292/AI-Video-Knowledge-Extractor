import json
import os

from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.5-flash-lite"

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["title", "detail"],
            },
        },
    },
    "required": ["points"],
}

EXPLAIN_PROMPT = """A learner is studying this topic from a video roadmap and wants a
deeper explanation than what's already shown.

Topic: {heading}
Existing explanation: {content}
Existing example: {example}

Break a deeper explanation of this topic into 4 to 6 distinct points — go
further than the existing explanation above: context, why it matters, common
misconceptions, nuance, or how it connects to related ideas. Do not just
reword the existing explanation.

For each point give:
- "title": a short (3-8 word) label for the point.
- "detail": 1-3 sentences expanding on it.
"""

QUIZ_QUESTION_PROPERTIES = {
    "question": {"type": "string"},
    "options": {
        "type": "array",
        "items": {"type": "string"},
    },
    "answer_index": {"type": "integer"},
    "explanation": {"type": "string"},
}

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": QUIZ_QUESTION_PROPERTIES,
                "required": ["question", "options", "answer_index", "explanation"],
            },
        },
    },
    "required": ["questions"],
}

QUIZ_PROMPT = """A learner is studying this topic from a video roadmap and wants to
test their understanding.

Topic: {heading}
Explanation: {content}
Example: {example}

Write 4 to 5 multiple-choice quiz questions testing understanding of this
specific topic, covering different aspects of it (don't just rephrase the
same question). For each question, provide exactly 4 "options", set
"answer_index" to the 0-based index of the correct option, and give a short
"explanation" of why that answer is correct. Every question must be
answerable from the explanation/example above — don't require outside
knowledge.
"""


class TopicAssistantError(Exception):
    pass


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise TopicAssistantError("GEMINI_API_KEY environment variable is not set")
    return genai.Client(api_key=api_key)


def explain_topic(heading: str, content: str, example: str | None) -> list[dict]:
    client = _get_client()
    prompt = EXPLAIN_PROMPT.format(heading=heading, content=content, example=example or "(none given)")

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EXPLAIN_SCHEMA,
            ),
        )
    except Exception as exc:
        raise TopicAssistantError(f"Gemini request failed: {exc}")

    try:
        explanation = json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise TopicAssistantError(f"Gemini returned invalid JSON: {exc}")

    points = explanation.get("points", [])
    if not points:
        raise TopicAssistantError("Gemini returned no explanation points")

    return points


def quiz_topic(heading: str, content: str, example: str | None) -> list[dict]:
    client = _get_client()
    prompt = QUIZ_PROMPT.format(heading=heading, content=content, example=example or "(none given)")

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QUIZ_SCHEMA,
            ),
        )
    except Exception as exc:
        raise TopicAssistantError(f"Gemini request failed: {exc}")

    try:
        quiz = json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise TopicAssistantError(f"Gemini returned invalid JSON: {exc}")

    questions = quiz.get("questions", [])
    if not questions:
        raise TopicAssistantError("Gemini returned no quiz questions")

    for q in questions:
        if len(q.get("options", [])) != 4 or not (0 <= q.get("answer_index", -1) < 4):
            raise TopicAssistantError("Gemini returned a malformed quiz question")

    return questions
