# this module provides functions to generate explanations and quizzes for a given topic using the Gemini API.

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

CODE_QUESTION_INSTRUCTIONS = """If the topic/example above involves code, syntax, or a command, include at
least one question that tests it directly — e.g. "what does this code
output", "what's wrong with this snippet", "which option correctly does X".
Reuse the actual code from the example (or a small variant of it) rather than
describing code in prose. Put any code in the "question" text and/or
"options" as a fenced block using triple backticks, e.g.:
```python
print(1 + 1)
```
preserving exact syntax and indentation. Only do this when the topic is
actually about code — don't force code into questions on non-code topics."""

QUIZ_PROMPT = """A learner is studying this topic from a video roadmap and wants to
test their understanding.

Topic: {heading}
Explanation: {content}
Example: {example}

Write exactly 5 multiple-choice quiz questions testing understanding of this
specific topic, covering different aspects of it (don't just rephrase the
same question). For each question, provide exactly 4 "options", set
"answer_index" to the 0-based index of the correct option, and give a short
"explanation" of why that answer is correct. Every question must be
answerable from the explanation/example above — don't require outside
knowledge.

""" + CODE_QUESTION_INSTRUCTIONS

OVERALL_QUIZ_PROMPT = """A learner has gone through an entire learning roadmap generated
from a video, covering the modules listed below. Test their overall
understanding across the WHOLE roadmap, not just one part of it.

Roadmap:
{roadmap_text}

Write exactly {count} multiple-choice quiz questions that together cover
every module above — spread the questions across all the modules
(proportionally to how many there are) rather than clustering them on the
first few. Don't ask more than one or two questions about any single module.
For each question, provide exactly 4 "options", set "answer_index" to the
0-based index of the correct option, and give a short "explanation" of why
that answer is correct. Every question must be answerable from the roadmap
content above — don't require outside knowledge.

""" + CODE_QUESTION_INSTRUCTIONS


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


def _generate_quiz(prompt: str) -> list[dict]:
    client = _get_client()

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


def quiz_topic(heading: str, content: str, example: str | None) -> list[dict]:
    prompt = QUIZ_PROMPT.format(heading=heading, content=content, example=example or "(none given)")
    # Gemini is asked for exactly 5, but structured output isn't a hard
    # guarantee — cap here so the quiz never runs longer than requested.
    return _generate_quiz(prompt)[:5]


def _flatten_roadmap(roadmap: list[dict]) -> str:
    """Render a roadmap tree as plain text (heading/content/example for every
    topic and child) so it can be dropped straight into a prompt."""
    lines = []
    for topic in roadmap:
        lines.append(f"- {topic.get('heading', '')}: {topic.get('content', '')}")
        if topic.get("example"):
            lines.append(f"  Example: {topic['example']}")
        for child in topic.get("children") or []:
            lines.append(f"  - {child.get('heading', '')}: {child.get('content', '')}")
            if child.get("example"):
                lines.append(f"    Example: {child['example']}")
    return "\n".join(lines)


def quiz_overall(roadmap: list[dict], count: int = 12) -> list[dict]:
    if not roadmap:
        raise TopicAssistantError("Roadmap is empty, nothing to quiz on")

    roadmap_text = _flatten_roadmap(roadmap)
    prompt = OVERALL_QUIZ_PROMPT.format(roadmap_text=roadmap_text, count=count)
    return _generate_quiz(prompt)
