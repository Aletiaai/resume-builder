"""Skill content loader for resume generation agents.

Reads skill files from disk and concatenates them into a single prompt string.
No Gemini Files API — content is injected directly into each LLM call.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent.parent / ".claude" / "skills"


def _get_skill_path(skill_name: str) -> Optional[Path]:
    """Return the SKILL.md path for a given skill name."""
    path = SKILLS_DIR / skill_name / "SKILL.md"
    return path if path.exists() else None


def get_skill_content(skill_name: str, language: Optional[str] = None) -> Optional[str]:
    """Read the SKILL.md body (frontmatter stripped) and relevant reference files, concatenated.

    Always appends references/section-rules.md.
    Only appends references/spanish-format.md when language == 'es'.
    Never appends references/formatting.md (implemented in docx_service.py).

    Args:
        skill_name: Name of the skill directory under SKILLS_DIR.
        language: 'en' or 'es'. Controls whether Spanish format rules are included.
    """
    path = _get_skill_path(skill_name)
    if path is None:
        logger.warning(f"Skill file not found on disk for: {skill_name}")
        return None

    text = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter (--- ... ---)
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].lstrip()

    references_dir = path.parent / "references"

    if references_dir.is_dir():
        ref_files = ["section-rules.md"]
        if language == "es":
            ref_files.append("spanish-format.md")

        for filename in ref_files:
            ref_path = references_dir / filename
            if ref_path.exists():
                ref_content = ref_path.read_text(encoding="utf-8")
                text += f"\n\n---\n<!-- references/{filename} -->\n\n{ref_content}"
                logger.debug(f"Appended reference file: {filename}")
            else:
                logger.warning(f"Reference file not found: {filename}")

    return text
