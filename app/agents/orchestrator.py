"""Orchestrator — coordinates the full resume generation agent loop.

Flow:
  1. Tailor Agent → draft resume
  2. Validator Agent (up to 3 attempts):
     - PASS → proceed to DOCX
     - FAIL → Repair Agent → re-validate
  3. If still FAIL after 3 attempts → deliver with red highlights
  4. Generate DOCX → upload to storage → update DB

All LLM exceptions propagate up and are caught here.
Agents never write to the DB; logging goes through LoggingService.
"""

import logging
from typing import Optional

from app.agents import tailor_agent, validator_agent, repair_agent
from app.models.schemas import ValidationResult
from app.services import docx_service, storage_service
from app.services.llm_service import GeminiQuotaExhaustedError, GeminiDailyQuotaExhaustedError, GeminiInvalidKeyError
from app.services.logging_service import LoggingService

logger = logging.getLogger(__name__)

MAX_VALIDATION_ATTEMPTS = 3


async def run(
    user_id: str,
    generation_id: str,
    original_resume_text: str,
    job_description: str,
    gemini_api_key: str,
    supabase_client,
    storage_svc: storage_service.StorageService,
    logging_svc: LoggingService,
    target_company: str = "",
    contact_info: dict = None,
) -> dict:
    """Run the full resume generation pipeline.

    Returns a dict with keys:
        generation_id, download_url, has_flagged_sections, flagged_section_count
    """
    await logging_svc.log_user_event(
        user_id=user_id,
        event_type="generate_start",
        metadata={
            "generation_id": generation_id,
            "job_description_length": len(job_description),
        },
    )

    try:
        # ------------------------------------------------------------------
        # Step 1: Tailor Agent
        # ------------------------------------------------------------------
        tailored_resume, tailor_usage = await tailor_agent.tailor(
            original_resume_text=original_resume_text,
            job_description=job_description,
            gemini_api_key=gemini_api_key,
            contact_info=contact_info or {},
        )

        # Always override the candidate name with authoritative profile data.
        # Never trust the model's inference — it may read a different name from the base resume.
        _info = contact_info or {}
        first = _info.get("first_name", "").strip()
        last = _info.get("last_name", "").strip()
        if first or last:
            tailored_resume.candidate_name = f"{first} {last}".strip()

        # If the user supplied a company name, trust it over the model's extraction.
        # If neither the user nor the model produced one, keep empty — docx_service
        # will fall back to 'XX' in the filename.
        if target_company:
            tailored_resume.target_company = target_company

        await logging_svc.log_llm_call(
            user_id=user_id,
            agent_name="tailor_agent",
            model_used="gemini-1.5-flash",
            tier=_get_user_tier(supabase_client, user_id),
            system_prompt="(via skill file)",
            input_prompt=f"JD length: {len(job_description)} chars",
            output=None,
            tokens_input=tailor_usage.get("tokens_input"),
            tokens_output=tailor_usage.get("tokens_output"),
            latency_ms=tailor_usage.get("latency_ms"),
        )

        # ------------------------------------------------------------------
        # Step 2-4: Validation loop (max 3 attempts)
        # ------------------------------------------------------------------
        final_validation: Optional[ValidationResult] = None
        passed = False
        final_outcome = "pass"

        for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
            val_result, val_usage = await validator_agent.validate(
                original_resume_text=original_resume_text,
                tailored_resume=tailored_resume,
                gemini_api_key=gemini_api_key,
            )

            await logging_svc.log_llm_call(
                user_id=user_id,
                agent_name="validator_agent",
                model_used="gemini-1.5-flash",
                tier=_get_user_tier(supabase_client, user_id),
                system_prompt="(via skill file)",
                input_prompt=f"Attempt {attempt}",
                output=f"result={val_result.result} findings={len(val_result.findings)}",
                tokens_input=val_usage.get("tokens_input"),
                tokens_output=val_usage.get("tokens_output"),
                latency_ms=val_usage.get("latency_ms"),
            )

            is_last_attempt = attempt == MAX_VALIDATION_ATTEMPTS
            if val_result.result == "PASS":
                passed = True
                final_outcome = "pass"
                await logging_svc.log_validation(
                    user_id=user_id,
                    generation_id=generation_id,
                    attempt_number=attempt,
                    flagged_sections=[],
                    passed=True,
                    final_outcome="pass",
                )
                break

            # FAIL path
            await logging_svc.log_validation(
                user_id=user_id,
                generation_id=generation_id,
                attempt_number=attempt,
                flagged_sections=[f.model_dump() for f in val_result.findings],
                passed=False,
                final_outcome="delivered_with_flags" if is_last_attempt else None,
            )

            if is_last_attempt:
                final_validation = val_result
                final_outcome = "delivered_with_flags"
                logger.warning(
                    f"[orchestrator] Generation {generation_id}: max validation attempts "
                    f"reached, delivering with {len(val_result.findings)} flag(s)."
                )
                break

            # Repair and continue
            tailored_resume, repair_usage = await repair_agent.repair(
                findings=val_result.findings,
                original_resume_text=original_resume_text,
                tailored_resume=tailored_resume,
                gemini_api_key=gemini_api_key,
                language=tailored_resume.language,
            )

            await logging_svc.log_llm_call(
                user_id=user_id,
                agent_name="repair_agent",
                model_used="gemini-1.5-flash",
                tier=_get_user_tier(supabase_client, user_id),
                system_prompt="(via skill file)",
                input_prompt=f"Repairing {len(val_result.findings)} finding(s)",
                output=None,
                tokens_input=repair_usage.get("tokens_input"),
                tokens_output=repair_usage.get("tokens_output"),
                latency_ms=repair_usage.get("latency_ms"),
            )

            final_outcome = "repaired"

        # ------------------------------------------------------------------
        # Step 5: Build granular flagged findings for DOCX highlighting
        # ------------------------------------------------------------------
        # Each entry carries section + flagged_text so docx_service can
        # highlight individual bullets/titles rather than whole sections.
        flagged_findings: list[dict] = []
        if not passed and final_validation:
            flagged_findings = [
                {"section": f.section.lower(), "flagged_text": f.flagged_text}
                for f in final_validation.findings
            ]

        # Distinct section count for the UI banner ("N sección(es) marcadas").
        flagged_section_count = len({item["section"] for item in flagged_findings})

        # ------------------------------------------------------------------
        # Step 6: Generate DOCX
        # ------------------------------------------------------------------
        docx_bytes, filename = docx_service.generate_docx(
            tailored_resume=tailored_resume,
            flagged_findings=flagged_findings,
        )

        # ------------------------------------------------------------------
        # Step 7: Upload to Supabase Storage
        # ------------------------------------------------------------------
        file_path = await storage_svc.upload_resume(
            user_id=user_id,
            file_bytes=docx_bytes,
            filename=filename,
        )

        download_url = await storage_svc.get_signed_url(file_path)

        # ------------------------------------------------------------------
        # Step 8: Update generations table
        # ------------------------------------------------------------------
        has_flagged = len(flagged_findings) > 0
        supabase_client.table("generations").update({
            "status": "completed",
            "language_detected": tailored_resume.language,
            "output_file_path": file_path,
            "has_flagged_sections": has_flagged,
            "flagged_section_count": flagged_section_count,
        }).eq("id", generation_id).execute()

        await logging_svc.log_user_event(
            user_id=user_id,
            event_type="generate_complete",
            metadata={
                "generation_id": generation_id,
                "language": tailored_resume.language,
                "final_outcome": final_outcome,
                "flagged_section_count": flagged_section_count,
            },
        )

        return {
            "generation_id": generation_id,
            "download_url": download_url,
            "has_flagged_sections": has_flagged,
            "flagged_section_count": flagged_section_count,
        }

    except GeminiDailyQuotaExhaustedError as exc:
        logger.warning(f"[orchestrator] Daily quota exhausted for generation {generation_id}: {exc}")
        _mark_failed(supabase_client, generation_id, "failed_quota_daily")
        await logging_svc.log_user_event(
            user_id=user_id,
            event_type="generation_error",
            metadata={"generation_id": generation_id, "error": "quota_daily"},
        )
        raise

    except GeminiQuotaExhaustedError as exc:
        logger.warning(f"[orchestrator] Quota exhausted for generation {generation_id}: {exc}")
        _mark_failed(supabase_client, generation_id, "failed_quota")
        await logging_svc.log_user_event(
            user_id=user_id,
            event_type="generation_error",
            metadata={"generation_id": generation_id, "error": "quota_exhausted"},
        )
        raise

    except GeminiInvalidKeyError as exc:
        logger.warning(f"[orchestrator] Invalid API key for generation {generation_id}: {exc}")
        _mark_failed(supabase_client, generation_id, "failed_key")
        await logging_svc.log_user_event(
            user_id=user_id,
            event_type="generation_error",
            metadata={"generation_id": generation_id, "error": "invalid_api_key"},
        )
        raise

    except Exception as exc:
        logger.exception(f"[orchestrator] Unhandled error for generation {generation_id}: {exc}")
        _mark_failed(supabase_client, generation_id, "failed")
        await logging_svc.log_user_event(
            user_id=user_id,
            event_type="generation_error",
            metadata={"generation_id": generation_id, "error": str(exc)},
        )
        raise


def _mark_failed(supabase_client, generation_id: str, status: str) -> None:
    """Update the generation record with a failure status."""
    try:
        supabase_client.table("generations").update(
            {"status": status}
        ).eq("id", generation_id).execute()
    except Exception:
        pass


def _get_user_tier(supabase_client, user_id: str) -> str:
    """Fetch user tier for logging. Returns 'unknown' on failure."""
    try:
        result = supabase_client.table("users").select("tier").eq("id", user_id).single().execute()
        return result.data.get("tier", "unknown")
    except Exception:
        return "unknown"
