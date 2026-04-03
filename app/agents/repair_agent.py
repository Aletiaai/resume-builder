"""Repair Agent — rewrites flagged sections to remove hallucinations.

Calls the resume-tailor skill in repair mode, one LLM call per flagged section.
Batching by section keeps each prompt small and conserves the user's Gemini quota.
Returns an updated TailoredResume with only the flagged sections corrected.
"""

import json
import logging
import re

from collections import defaultdict
from typing import Optional

from app.models.schemas import (
    ExperienceEntry,
    TailoredResume,
    ValidationFinding,
)
from app.prompts import REPAIR_SECTION_PROMPT_TEMPLATE
from app.services import llm_service

logger = logging.getLogger(__name__)

SKILL_NAME = "resume-tailor"

# Maps section names (lowercase) to the TailoredResume field they correspond to.
# Sections not listed here are repaired by patching the whole resume (fallback).
_SECTION_FIELD_MAP = {
    "summary": "summary",
    "skills": "skills",
    "experience": "experience",
    "education": "education",
    "languages": "languages_line",
    "languages_line": "languages_line",
}


def _extract_json(text: str) -> str:
    """Strip any markdown code fences and return the raw JSON string."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        return match.group(1)
    return text


def _get_section_value(resume: TailoredResume, section: str):
    """Return the current value of the given section from the resume."""
    field = _SECTION_FIELD_MAP.get(section.lower())
    if field:
        return getattr(resume, field)
    return None


def _apply_section_patch(
    resume: TailoredResume,
    section: str,
    patched_value,
) -> TailoredResume:
    """Return a new TailoredResume with one section replaced by patched_value."""
    field = _SECTION_FIELD_MAP.get(section.lower())
    if not field:
        logger.warning(f"[repair_agent] Unknown section '{section}' — skipping patch.")
        return resume

    data = resume.model_dump()

    if field == "experience":
        if isinstance(patched_value, list):
            data["experience"] = patched_value
        else:
            logger.warning(f"[repair_agent] Expected list for experience, got {type(patched_value)} — skipping.")
    else:
        data[field] = patched_value

    experience = [
        ExperienceEntry(
            company=e["company"],
            title=e["title"],
            dates=e["dates"],
            bullets=e["bullets"],
        )
        for e in data.get("experience", [])
    ]

    return TailoredResume(
        language=data["language"],
        candidate_name=data["candidate_name"],
        contact_line=data["contact_line"],
        summary=data["summary"],
        skills=data["skills"],
        experience=experience,
        education=data["education"],
        languages_line=data["languages_line"],
        target_company=data["target_company"],
    )


async def repair(
    findings: list[ValidationFinding],
    original_resume_text: str,
    tailored_resume: TailoredResume,
    gemini_api_key: str,
    language: Optional[str] = None,
) -> tuple[TailoredResume, dict]:
    """Rewrite only the flagged sections in the tailored resume.

    One LLM call is made per distinct flagged section. Combined usage metadata
    is returned (summed tokens, summed latency).

    Returns:
        Tuple of (corrected TailoredResume, combined usage_metadata dict).
    """
    # Group findings by section (case-insensitive)
    by_section: dict[str, list[ValidationFinding]] = defaultdict(list)
    for finding in findings:
        by_section[finding.section.lower()].append(finding)

    combined_usage = {"tokens_input": 0, "tokens_output": 0, "latency_ms": 0}
    current_resume = tailored_resume

    for section, section_findings in by_section.items():
        section_value = _get_section_value(current_resume, section)
        if section_value is None:
            logger.warning(f"[repair_agent] Section '{section}' not found in resume model — skipping.")
            continue

        findings_json = json.dumps(
            [f.model_dump() for f in section_findings], indent=2, ensure_ascii=False
        )
        section_json = json.dumps(
            section_value, indent=2, ensure_ascii=False,
            default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o),
        )

        user_prompt = REPAIR_SECTION_PROMPT_TEMPLATE.format(
            section_name=section,
            original_resume_text=original_resume_text,
            section_json=section_json,
            findings_json=findings_json,
        )

        raw_text, usage = await llm_service.call(
            agent_name=f"repair_agent[{section}]",
            user_prompt=user_prompt,
            gemini_api_key=gemini_api_key,
            skill_name=SKILL_NAME,
            language=language,
        )

        # Accumulate usage
        combined_usage["tokens_input"] += usage.get("tokens_input") or 0
        combined_usage["tokens_output"] += usage.get("tokens_output") or 0
        combined_usage["latency_ms"] += usage.get("latency_ms") or 0

        json_str = _extract_json(raw_text)
        try:
            patched_value = json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.error(
                f"[repair_agent] Failed to parse response for section '{section}': {exc} | "
                f"First 500 chars: {raw_text[:500]!r}"
            )
            # Skip this section — leave the original value in place
            continue

        current_resume = _apply_section_patch(current_resume, section, patched_value)
        logger.info(
            f"[repair_agent] Repaired section '{section}' "
            f"({len(section_findings)} finding(s))."
        )

    logger.info(
        f"[repair_agent] Done — {len(by_section)} section(s) repaired, "
        f"{len(findings)} total finding(s)."
    )
    return current_resume, combined_usage
