"""Model fallback for Gemini video/audio calls, bounded by a deadline.

Tries models in order, but models that recently answered "busy" (503),
"quota exhausted" (429) or timed out are moved to the back of the line for a
while - on a busy day each of those failures takes ~30-40s to come back, so
retrying them first on every analysis wastes minutes."""

import logging
import time
from typing import Callable, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

# The "-latest" aliases track Google's current models; pinned versions get
# retired, so any failure just moves on to the next.
VIDEO_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",   
)

BUSY_COOLDOWN_SECONDS = 5 * 60
QUOTA_COOLDOWN_SECONDS = 30 * 60

# Never start an attempt with less time than this left - it couldn't finish.
MIN_ATTEMPT_SECONDS = 20
# Cap a single attempt so one stuck model can't eat the whole budget.
MAX_ATTEMPT_SECONDS = 150

_cooldown_until: dict[str, float] = {}


class GeminiUnavailableError(Exception):
    def __init__(self, message: str, quota_exhausted: bool):
        super().__init__(message)
        self.quota_exhausted = quota_exhausted


def _cooldown_for(exc: Exception) -> float | None:
    message = str(exc)
    if "RESOURCE_EXHAUSTED" in message or "429" in message:
        return QUOTA_COOLDOWN_SECONDS
    if "UNAVAILABLE" in message or "503" in message or isinstance(exc, httpx.TimeoutException):
        return BUSY_COOLDOWN_SECONDS
    return None


def ordered_models(models: tuple[str, ...] = VIDEO_MODELS) -> list[str]:
    now = time.monotonic()
    ready = [m for m in models if _cooldown_until.get(m, 0) <= now]
    cooling = sorted((m for m in models if m not in ready), key=lambda m: _cooldown_until[m])
    return ready + cooling


def call_with_fallback(
    call: Callable[[str, int], T],
    deadline: float,
    label: str,
    models: tuple[str, ...] = VIDEO_MODELS,
) -> T:
    """Run `call(model, timeout_ms)` on each model in turn until one succeeds
    or `deadline` (a time.monotonic() value) is too close."""
    errors: list[str] = []
    quota_errors = 0
    started = time.monotonic()

    for model in ordered_models(models):
        remaining = deadline - time.monotonic()
        if remaining < MIN_ATTEMPT_SECONDS:
            errors.append("out of time")
            break

        attempt_started = time.monotonic()
        try:
            result = call(model, int(min(MAX_ATTEMPT_SECONDS, remaining) * 1000))
        except Exception as exc:
            cooldown = _cooldown_for(exc)
            if cooldown:
                _cooldown_until[model] = time.monotonic() + cooldown
                if cooldown == QUOTA_COOLDOWN_SECONDS:
                    quota_errors += 1
            logger.warning(
                "%s with %s failed after %.1fs: %s", label, model, time.monotonic() - attempt_started, exc
            )
            errors.append(f"{model}: {exc}")
            continue

        _cooldown_until.pop(model, None)
        logger.info(
            "%s with %s took %.1fs (%.1fs total incl. %d failed attempt(s))",
            label, model, time.monotonic() - attempt_started, time.monotonic() - started, len(errors),
        )
        return result

    raise GeminiUnavailableError("; ".join(errors), quota_exhausted=quota_errors > 0 and quota_errors == len(errors))
