"""Repair Agent — rewrites flagged sections to remove hallucinations.

Calls the resume-tailor skill in repair mode.
Returns an updated TailoredResume with only the flagged sections corrected.
"""

import json
import logging
import re

from typing import Optional

from app.models.schemas import (
    ExperienceEntry,
    TailoredResume,
    ValidationFinding,
)
from app.prompts import REPAIR_USER_PROMPT_TEMPLATE
from app.services import llm_service

logger = logging.getLogger(__name__)

SKILL_NAME = "resume-tailor"


def _extract_json(text: str) -> str:
    """Strip any markdown code fences and return the raw JSON string."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text


async def repair(
    findings: list[ValidationFinding],
    original_resume_text: str,
    tailored_resume: TailoredResume,
    gemini_api_key: str,
    language: Optional[str] = None,
) -> tuple[TailoredResume, dict]:
    """Rewrite only the flagged sections in the tailored resume.

    Returns:
        Tuple of (corrected TailoredResume, usage_metadata dict).
    """
    findings_json = json.dumps(
        [f.model_dump() for f in findings], indent=2, ensure_ascii=False
    )

    user_prompt = REPAIR_USER_PROMPT_TEMPLATE.format(
        original_resume_text=original_resume_text,
        tailored_resume_json=tailored_resume.model_dump_json(indent=2),
        findings_json=findings_json,
    )

    raw_text, usage = await llm_service.call(
        agent_name="repair_agent",
        user_prompt=user_prompt,
        gemini_api_key=gemini_api_key,
        skill_name=SKILL_NAME,
        language=language,
    )

    json_str = _extract_json(raw_text)
    data = json.loads(json_str)

    experience = [
        ExperienceEntry(
            company=e["company"],
            title=e["title"],
            dates=e["dates"],
            bullets=e["bullets"],
        )
        for e in (data.get("experience") or tailored_resume.model_dump()["experience"])
    ]

    repaired = TailoredResume(
        language=data.get("language") or tailored_resume.language,
        candidate_name=data.get("candidate_name") or tailored_resume.candidate_name,
        contact_line=data.get("contact_line") or tailored_resume.contact_line,
        summary=data.get("summary") or tailored_resume.summary,
        skills=data.get("skills") or tailored_resume.skills,
        experience=experience,
        education=data.get("education") or tailored_resume.education,
        languages_line=data.get("languages_line") or tailored_resume.languages_line,
        target_company=data.get("target_company") or tailored_resume.target_company,
    )

    logger.info(f"[repair_agent] Repaired {len(findings)} finding(s).")
    return repaired, usage
