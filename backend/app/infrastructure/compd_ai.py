"""The Gemini call behind CompD's "Generate with AI" (compD `server/app/services/question_ai.py`,
the Gemini path only), served by the dashboard itself (owner direction 2026-10-21).

WHAT CHANGED FROM compD, AND WHY:

* **The prompt says "for children aged 6-8"** where compD's said "for children with" a clinical
  label the project's wording rules ban (owner Q15).
* **At most three attempts, bounded.** `gemini-3.6-flash` often answers 503 "high demand" (seen
  live 2026-10-21: most calls; every full "flash" model did the same, while
  `gemini-3.5-flash-lite` answered every call in 1-2 s; `gemini-2.5-flash` is 404, "no longer
  available to new users"). So a busy answer (429/5xx), a retired model (404), a timeout or a
  network error moves on: compD's model, then `gemini-3.5-flash-lite`, then it once more after a
  short pause, 20 s each, and no new attempt once 40 s have gone by. Any other answer (a bad key, a
  bad request) is final at once. Still a fast, honest "not available" when all of them fail, which
  leaves "Create manually" open.
* **The key travels in the `x-goog-api-key` header, never the URL**, where a logged URL would
  carry it. It is never logged, returned or echoed.
* **A draft's topic is FORCED to the requested one**, and its difficulty to the requested one when
  the model's is not one of the three -- so no draft can fail the bank's CHECK on save.
* **The options rule is the bank's** (2-6, answer appended); a draft that breaks it is dropped,
  instead of compD's 5-cap truncation, which could cut off the answer it had just appended.

ONLY FOUR VALUES LEAVE THE DASHBOARD: topic, difficulty, count and the teacher's instructions. No
learner data of any kind is in the prompt. The instructions are the teacher's free text, sent as
typed; the page asks teachers not to put children's names there.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.domain.compd import CompdQuestionCreate

# compD's own model choice (`question_ai.py:16`, `questions.py:227`).
GEMINI_MODEL = "gemini-3.6-flash"
# Tried when compD's is busy: the one model that answered reliably in the live check.
FALLBACK_MODEL = "gemini-3.5-flash-lite"
ATTEMPT_MODELS = (GEMINI_MODEL, FALLBACK_MODEL, FALLBACK_MODEL)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SECONDS = 20.0
#: No new attempt starts after this long; bounds the teacher's wait.
DEADLINE_SECONDS = 40.0
#: The pause before the last attempt (the fallback again). Tests set it to 0.
RETRY_PAUSE_SECONDS = 1.5
#: Google's "busy, try again" answers, and 404 for a retired model. Anything else non-2xx is final.
NEXT_MODEL_STATUSES = frozenset({404, 429, 500, 502, 503, 504})
VALID_DIFFICULTIES = ("Easy", "Medium", "Hard")


class CompdAiUnavailable(RuntimeError):
    """No key, a timeout, a network error, a non-2xx answer or no generated text -- to the teacher
    all the same: the AI is not available right now. Which one it was is deliberately not passed
    on, because a provider's error body can echo the request."""


def build_prompt(topic: str, difficulty: str, count: int, instructions: str | None) -> str:
    """compD `_build_prompt`, with the one approved wording change. compD's JSON shape, including
    its `correct_answer` key, is kept: the parser below reads it."""

    extra = f"\nAdditional teacher instructions: {instructions.strip()}" if instructions else ""
    return (
        "Generate cognitive math questions for children aged 6-8.\n"
        f"Topic: {topic}\n"
        f"Difficulty: {difficulty}\n"
        f"Count: {count}\n"
        "Return only valid JSON with this shape:\n"
        '{"questions":[{"topic":"Addition","difficulty":"Easy","question_text":"2 + 3 = ?",'
        '"correct_answer":"5","options":["4","5","6","7"]}]}\n'
        "Rules: each options array must have 2 to 4 string options, must include correct_answer, "
        "and questions should be short, clear, and age-appropriate."
        f"{extra}"
    )


async def request_draft_text(
    *, api_key: str | None, prompt: str, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    """POSTs to Gemini over `ATTEMPT_MODELS` (see the module docstring); the first model's text, or
    `CompdAiUnavailable`. `transport` lets the tests stand in for Gemini without a network."""

    if not api_key:
        raise CompdAiUnavailable("no key configured")
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
    }
    started = time.monotonic()
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=transport) as client:
        for attempt, model in enumerate(ATTEMPT_MODELS):
            if attempt and time.monotonic() - started > DEADLINE_SECONDS:
                break
            if attempt == len(ATTEMPT_MODELS) - 1 and RETRY_PAUSE_SECONDS:
                await asyncio.sleep(RETRY_PAUSE_SECONDS)
            try:
                response = await client.post(
                    GEMINI_URL.format(model=model),
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                )
            except httpx.HTTPError as exc:  # a timeout or a network error: try the next one
                last_error = exc
                continue
            if response.status_code in NEXT_MODEL_STATUSES:
                last_error = httpx.HTTPStatusError(
                    f"next model: {response.status_code}", request=response.request, response=response
                )
                continue
            try:
                response.raise_for_status()
                return response.json()["candidates"][0]["content"]["parts"][0]["text"]
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                # A bad key, a bad request or no generated text: another attempt won't change it.
                raise CompdAiUnavailable(type(exc).__name__) from exc
    raise CompdAiUnavailable(type(last_error).__name__ if last_error else "deadline") from last_error


def parse_drafts(text: str, *, topic: str, difficulty: str, count: int) -> list[CompdQuestionCreate]:
    """compD `_parse_questions` + `_extract_json`. `[]` when nothing usable came back -- garbage
    and an empty list are one case to the caller."""

    try:
        payload = json.loads(_extract_json(text))
    except ValueError:
        return []
    items: Any = payload.get("questions", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    drafts: list[CompdQuestionCreate] = []
    for item in items[:count]:
        if not isinstance(item, dict):
            continue
        raw_options = item.get("options")
        options = (
            [str(value).strip() for value in raw_options if str(value).strip()]
            if isinstance(raw_options, list)
            else []
        )
        code = item.get("question_code")
        try:
            drafts.append(
                CompdQuestionCreate(
                    question_code=code.strip() if isinstance(code, str) and code.strip() else None,
                    topic=topic,  # forced: see the module docstring
                    difficulty=item.get("difficulty") if item.get("difficulty") in VALID_DIFFICULTIES else difficulty,
                    question_text=str(item.get("question_text", "")).strip(),
                    correct_answer=str(item.get("correct_answer", "")).strip(),
                    options=options,
                )
            )
        except ValidationError:
            # Blank text or answer, an over-long field, or options outside 2-6: dropped, as
            # compD dropped its own invalid items.
            continue
    return drafts


def _extract_json(text: str) -> str:
    """compD `_extract_json`: strip a code fence, else take the outermost `{...}` / `[...]`."""

    trimmed = text.strip()
    if trimmed.startswith("```"):
        trimmed = trimmed.strip("`").strip()
        if trimmed.lower().startswith("json"):
            trimmed = trimmed[4:].strip()
    if trimmed.startswith("{") or trimmed.startswith("["):
        return trimmed
    starts = [index for index in (trimmed.find("{"), trimmed.find("[")) if index >= 0]
    if not starts:
        raise ValueError("no JSON in the model's text")
    start = min(starts)
    end = max(trimmed.rfind("}"), trimmed.rfind("]"))
    if end <= start:
        raise ValueError("incomplete JSON in the model's text")
    return trimmed[start:end + 1]
