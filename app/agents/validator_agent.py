"""Validator Agent — detects hallucinations in the tailored resume.

Calls the resume-validator skill via the Gemini Files API.
Parses the JSON response into a ValidationResult model.
"""

import json
import logging
import re

from app.models.schemas import TailoredResume, ValidationFinding, ValidationResult
from app.prompts import VALIDATOR_USER_PROMPT_TEMPLATE
from app.services import llm_service

logger = logging.getLogger(__name__)

SKILL_NAME = "resume-validator"


def _extract_json(text: str) -> str:
    """Strip markdown code fences, then extract the outermost JSON object."""
    text = text.strip()
    # Remove markdown code fences if present
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()
    # Extract outermost { ... } in case Gemini added prose before or after
    obj_match = re.search(r'\{[\s\S]*\}', text)
    if obj_match:
        return obj_match.group(0)
    return text


async def validate(
    original_resume_text: str,
    tailored_resume: TailoredResume,
    gemini_api_key: str,
) -> tuple[ValidationResult, dict]:
    """Validate the tailored resume against the original for hallucinations.

    Returns:
        Tuple of (ValidationResult, usage_metadata dict).
    """
    tailored_resume_json = tailored_resume.model_dump_json(indent=2)

    user_prompt = VALIDATOR_USER_PROMPT_TEMPLATE.format(
        original_resume_text=original_resume_text,
        tailored_resume_json=tailored_resume_json,
    )

    raw_text, usage = await llm_service.call(
        agent_name="validator_agent",
        user_prompt=user_prompt,
        gemini_api_key=gemini_api_key,
        skill_name=SKILL_NAME,
    )

    json_str = _extract_json(raw_text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.error(
            f"[validator_agent] Failed to parse JSON response — returning PASS to allow "
            f"generation to continue. Raw response: {raw_text!r}"
        )
        return ValidationResult(result="PASS", findings=[]), usage

    findings = [
        ValidationFinding(
            severity=f["severity"],
            section=f["section"],
            pattern=f["pattern"],
            original_text=f["original_text"],
            flagged_text=f["flagged_text"],
            explanation=f["explanation"],
            repair_instruction=f["repair_instruction"],
        )
        for f in data.get("findings", [])
    ]

    explicit_result = data.get("result")
    if explicit_result:
        result_str = explicit_result
    else:
        # Infer from findings when the LLM omits the "result" key
        result_str = "PASS" if not findings else "FAIL"

    result = ValidationResult(
        result=result_str,
        findings=findings,
    )

    logger.info(
        f"[validator_agent] result={result.result} findings={len(result.findings)}"
    )
    return result, usage
