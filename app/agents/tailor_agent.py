"""Tailor Agent — generates the tailored resume draft.

Calls the resume-tailor skill via the Gemini Files API.
Parses the JSON response into a TailoredResume model.
"""

import json
import logging
import re

from app.models.schemas import TailoredResume, ExperienceEntry
from app.prompts import TAILOR_USER_PROMPT_TEMPLATE
from app.services import llm_service

logger = logging.getLogger(__name__)

SKILL_NAME = "resume-tailor"

# One automatic retry when the model returns malformed JSON.
# Without a valid resume there is nothing to deliver, so a single retry is
# preferable to failing immediately on what is often a transient formatting issue.
_MAX_PARSE_RETRIES = 1


def _clean_json(text: str) -> str:
    """Clean a raw LLM response to extract a parseable JSON object.

    Steps applied in order:
    1. Strip markdown code fences (```json ... ``` or ``` ... ```)
    2. Extract the outermost { ... } block to discard prose before/after
    3. Remove trailing commas before } or ] (common Gemini formatting mistake)
    """
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()
    obj_match = re.search(r'\{[\s\S]*\}', text)
    if obj_match:
        text = obj_match.group(0)
    # Fix trailing commas: e.g.  ["a", "b",] or {"k": "v",}
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


async def tailor(
    original_resume_text: str,
    job_description: str,
    gemini_api_key: str,
    contact_info: dict = None,
) -> tuple[TailoredResume, dict]:
    """Generate a tailored resume draft from the original resume and job description.

    Args:
        contact_info: Dict with keys city, phone, email, linkedin. Used verbatim
            for the resume header — the model must not infer or modify these values.

    Returns:
        Tuple of (TailoredResume, usage_metadata dict).
    """
    info = contact_info or {}
    user_prompt = TAILOR_USER_PROMPT_TEMPLATE.format(
        original_resume_text=original_resume_text,
        job_description=job_description,
        contact_first_name=info.get("first_name", ""),
        contact_last_name=info.get("last_name", ""),
        contact_city=info.get("city", ""),
        contact_phone=info.get("phone", ""),
        contact_email=info.get("email", ""),
        contact_linkedin=info.get("linkedin", "") or "",
    )

    data = None
    usage = {}
    last_exc = None
    last_raw = ""

    for attempt in range(_MAX_PARSE_RETRIES + 1):
        raw_text, usage = await llm_service.call(
            agent_name="tailor_agent",
            user_prompt=user_prompt,
            gemini_api_key=gemini_api_key,
            skill_name=SKILL_NAME,
        )
        json_str = _clean_json(raw_text)
        try:
            data = json.loads(json_str)
            break  # parsed successfully
        except json.JSONDecodeError as exc:
            last_exc = exc
            last_raw = raw_text
            if attempt < _MAX_PARSE_RETRIES:
                logger.warning(
                    f"[tailor_agent] Malformed JSON on attempt {attempt + 1} — retrying. "
                    f"Error: {exc} | First 200 chars: {raw_text[:200]!r}"
                )
            else:
                logger.error(
                    f"[tailor_agent] Failed to parse JSON after {_MAX_PARSE_RETRIES + 1} "
                    f"attempt(s): {exc} | First 500 chars: {last_raw[:500]!r}"
                )
                raise RuntimeError("El modelo devolvió una respuesta con formato inválido.") from exc

    # Parse experience entries
    experience = [
        ExperienceEntry(
            company=e["company"],
            title=e["title"],
            dates=e["dates"],
            bullets=e["bullets"],
        )
        for e in data.get("experience", [])
    ]

    resume = TailoredResume(
        language=data.get("language", "en"),
        candidate_name=data.get("candidate_name", ""),
        contact_line=data.get("contact_line", ""),
        summary=data.get("summary", ""),
        skills=data.get("skills", []),
        experience=experience,
        education=data.get("education", []),
        languages_line=data.get("languages_line", ""),
        target_company=data.get("target_company", ""),
    )

    logger.info(
        f"[tailor_agent] Resume tailored — language={resume.language} "
        f"company={resume.target_company}"
    )
    return resume, usage
