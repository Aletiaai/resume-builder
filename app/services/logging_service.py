"""Centralized logging service — all DB log writes go through here.

Agents and routers never write to the DB directly.
Never logs: resume content, Gemini API keys, JWT tokens.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LoggingService:
    def __init__(self, supabase_client):
        self.db = supabase_client

    async def log_llm_call(
        self,
        user_id: Optional[str],
        agent_name: str,
        model_used: str,
        tier: str,
        system_prompt: str,
        input_prompt: str,
        output: Optional[str],
        tokens_input: Optional[int],
        tokens_output: Optional[int],
        latency_ms: Optional[int],
        error: Optional[str] = None,
    ) -> None:
        """Log every LLM call made by any agent to logs_llm_calls."""
        try:
            self.db.table("logs_llm_calls").insert({
                "user_id": user_id,
                "agent_name": agent_name,
                "model_used": model_used,
                "tier": tier,
                "system_prompt": system_prompt,
                "input_prompt": input_prompt,
                "output": output,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "latency_ms": latency_ms,
                "error": error,
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log LLM call: {e}")

    async def log_validation(
        self,
        user_id: Optional[str],
        generation_id: str,
        attempt_number: int,
        flagged_sections: Optional[list],
        passed: bool,
        final_outcome: Optional[str] = None,
    ) -> None:
        """Log every validation loop per resume generation to logs_validation."""
        try:
            self.db.table("logs_validation").insert({
                "user_id": user_id,
                "generation_id": generation_id,
                "attempt_number": attempt_number,
                "flagged_sections": flagged_sections,
                "pass": passed,
                "final_outcome": final_outcome,
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log validation: {e}")

    async def log_user_event(
        self,
        user_id: Optional[str],
        event_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log user actions to logs_user_events."""
        try:
            self.db.table("logs_user_events").insert({
                "user_id": user_id,
                "event_type": event_type,
                "metadata": metadata,
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log user event: {e}")

    async def log_billing(
        self,
        event_type: str,
        lemon_squeezy_payload: dict,
    ) -> Optional[str]:
        """Log incoming Lemon Squeezy webhook immediately on receipt.

        Returns the log row ID so the processing result can be updated later.
        """
        try:
            result = self.db.table("logs_billing").insert({
                "event_type": event_type,
                "lemon_squeezy_payload": lemon_squeezy_payload,
                "processing_result": "pending",
            }).execute()
            if result.data:
                return result.data[0]["id"]
        except Exception as e:
            logger.error(f"Failed to log billing event: {e}")
        return None

    async def update_billing_result(
        self,
        log_id: str,
        processing_result: str,
        error_detail: Optional[str] = None,
    ) -> None:
        """Update the processing result for a billing log row."""
        try:
            self.db.table("logs_billing").update({
                "processing_result": processing_result,
                "error_detail": error_detail,
            }).eq("id", log_id).execute()
        except Exception as e:
            logger.error(f"Failed to update billing result: {e}")
