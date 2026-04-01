"""Unified LLM caller for the Gemini API.

Agents call llm_service.call(...) and never interact with the API client directly.
The raw (decrypted) API key is passed in — this service does not decrypt anything.
"""

import asyncio
import logging
import re
import time
from typing import Optional

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from app.services import skill_service

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"

_MAX_RETRIES = 3
# Matches "Please retry in 28.63s" from Gemini 429 error messages
_RETRY_DELAY_RE = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)

# Permissive safety settings — resume content should never trip filters,
# but we disable them to avoid false positives on job description content.
_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}


async def call(
    agent_name: str,
    user_prompt: str,
    gemini_api_key: str,
    skill_name: Optional[str] = None,
    language: Optional[str] = None,
) -> tuple[str, dict]:
    """Call the Gemini API and return (response_text, usage_metadata).

    Args:
        agent_name: Name of the calling agent (for logging purposes).
        user_prompt: The user-turn prompt string.
        gemini_api_key: Raw (decrypted) Gemini API key.
        skill_name: If provided, the skill SKILL.md body is injected directly into the prompt.
        language: 'en' or 'es'. Passed to skill_service to include language-specific references.

    Returns:
        Tuple of (response text, usage dict with tokens_input/tokens_output/latency_ms).

    Raises:
        Exception: Any Gemini API error propagates to the caller (orchestrator catches).
    """
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        safety_settings=_SAFETY_SETTINGS,
    )

    parts = []

    # Inject skill content directly into the prompt
    if skill_name:
        skill_body = skill_service.get_skill_content(skill_name, language=language)
        if skill_body:
            parts.append(f"<skill_content name=\"{skill_name}\">\n{skill_body}\n</skill_content>\n\n")
        else:
            logger.warning(
                f"[{agent_name}] Skill content unavailable for '{skill_name}'."
            )

    parts.append(user_prompt)

    start = time.time()
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = model.generate_content(parts)
            break
        except ResourceExhausted as e:
            if attempt == _MAX_RETRIES:
                raise
            match = _RETRY_DELAY_RE.search(str(e))
            delay = float(match.group(1)) if match else (30.0 * (2 ** attempt))
            logger.warning(
                f"[{agent_name}] 429 rate limited — retrying in {delay:.1f}s "
                f"(attempt {attempt + 1}/{_MAX_RETRIES})"
            )
            await asyncio.sleep(delay)
    latency_ms = int((time.time() - start) * 1000)

    # Extract text safely
    if not response.candidates:
        raise RuntimeError(
            f"[{agent_name}] Gemini returned no candidates. "
            f"Finish reason: {getattr(response, 'prompt_feedback', 'unknown')}"
        )
    text = response.candidates[0].content.parts[0].text

    usage = {
        "tokens_input": getattr(response.usage_metadata, "prompt_token_count", None),
        "tokens_output": getattr(response.usage_metadata, "candidates_token_count", None),
        "latency_ms": latency_ms,
    }

    logger.debug(f"[{agent_name}] latency={latency_ms}ms tokens_in={usage['tokens_input']}")
    return text, usage


async def test_api_key(api_key: str) -> bool:
    """Make a lightweight call to verify a Gemini API key is valid.

    Returns True if valid, False otherwise.
    """
    from app.prompts import GEMINI_KEY_TEST_PROMPT
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(GEMINI_KEY_TEST_PROMPT)
        return bool(response.text)
    except Exception as e:
        logger.info(f"Gemini key validation failed: {e}")
        return False
