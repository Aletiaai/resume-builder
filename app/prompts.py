"""Centralized prompt templates for all agents.

System prompts are assembled at runtime by llm_service.py using skill file URIs.
This file contains only the user-turn prompt templates.
"""

# ---------------------------------------------------------------------------
# Tailor Agent
# ---------------------------------------------------------------------------

TAILOR_USER_PROMPT_TEMPLATE = """
You are activating the resume-tailor skill. Follow its instructions exactly.

## Original Resume (source of truth)
{original_resume_text}

## Target Job Description
{job_description}

## Output Instructions
Respond with a single JSON object matching this exact schema — no prose before or after:

{{
  "language": "en" | "es",
  "candidate_name": "Full Name",
  "contact_line": "City, ZIP | +CountryCode Phone | email | LinkedIn URL",
  "summary": "4-6 sentence prose summary",
  "skills": ["skill1", "skill2", ...],
  "experience": [
    {{
      "company": "Company Name",
      "title": "Job Title",
      "dates": "Mon YYYY – Mon YYYY",
      "bullets": ["bullet 1", "bullet 2", ...]
    }}
  ],
  "education": ["Degree | Institution | Date", ...],
  "languages_line": "Language (Level) | Language (Level)",
  "target_company": "Company name extracted from job description"
}}

Detect the language of the job description and generate the entire resume in that language.
Follow all section rules and formatting guidelines from the skill file.
"""

# ---------------------------------------------------------------------------
# Validator Agent
# ---------------------------------------------------------------------------

VALIDATOR_USER_PROMPT_TEMPLATE = """
You are activating the resume-validator skill. Follow its instructions exactly.

## Original Resume (source of truth)
{original_resume_text}

## Tailored Resume (to validate)
{tailored_resume_json}

Respond with a single JSON object matching the output format defined in the skill.
No prose before or after the JSON.
"""

# ---------------------------------------------------------------------------
# Repair Agent
# ---------------------------------------------------------------------------

REPAIR_USER_PROMPT_TEMPLATE = """
You are activating the resume-tailor skill in repair mode.

## Task
Rewrite ONLY the flagged sections listed below. Leave all other sections unchanged.
Ground every correction strictly in the original resume text.

## Original Resume (source of truth)
{original_resume_text}

## Current Tailored Resume (full document)
{tailored_resume_json}

## Flagged Findings to Repair
{findings_json}

## Output Instructions
Return the complete corrected resume as a JSON object with the same schema as the tailored resume.
Only change the flagged content — preserve everything else exactly.
No prose before or after the JSON.
"""

# ---------------------------------------------------------------------------
# Gemini API key validation (lightweight test prompt)
# ---------------------------------------------------------------------------

GEMINI_KEY_TEST_PROMPT = "Responde solo con la palabra: OK"
