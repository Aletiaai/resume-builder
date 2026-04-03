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


def _extract_json(text: str) -> str:
    """Strip any markdown code fences and return the raw JSON string."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
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
        contact_city=info.get("city", ""),
        contact_phone=info.get("phone", ""),
        contact_email=info.get("email", ""),
        contact_linkedin=info.get("linkedin", "") or "",
    )

    raw_text, usage = await llm_service.call(
        agent_name="tailor_agent",
        user_prompt=user_prompt,
        gemini_api_key=gemini_api_key,
        skill_name=SKILL_NAME,
    )

    json_str = _extract_json(raw_text)
    data = json.loads(json_str)

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
