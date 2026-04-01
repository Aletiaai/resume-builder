"""Billing router — Lemon Squeezy webhook handler and subscription gate."""

import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])


def _verify_lemon_squeezy_signature(payload: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature from Lemon Squeezy."""
    secret = os.environ.get("LEMON_SQUEEZY_WEBHOOK_SECRET", "").strip()
    expected = hmac.new(
        key=secret.encode(),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


@router.post("/webhook")
async def lemon_squeezy_webhook(request: Request):
    """Handle Lemon Squeezy webhook events.

    Logs every webhook immediately on receipt, then processes it.
    """
    supabase = request.app.state.supabase
    logging_svc = request.app.state.logging_svc

    raw_body = await request.body()
    signature = request.headers.get("X-Signature", "")
    logger.debug(f"Webhook raw body length: {len(raw_body)}, signature header: {signature!r}")

    # Verify webhook signature
    if not _verify_lemon_squeezy_signature(raw_body, signature):
        logger.warning("Lemon Squeezy webhook signature verification failed.")
        return Response(status_code=401, content="Signature invalid")

    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=400, content="Invalid JSON")

    event_type = payload.get("meta", {}).get("event_name", "unknown")

    # Log webhook immediately before processing
    log_id = await logging_svc.log_billing(
        event_type=event_type,
        lemon_squeezy_payload=payload,
    )

    try:
        await _process_webhook(event_type, payload, supabase)
        await logging_svc.update_billing_result(log_id, "success")
    except Exception as exc:
        logger.exception(f"Webhook processing failed for event '{event_type}': {exc}")
        if log_id:
            await logging_svc.update_billing_result(
                log_id, "error", error_detail=str(exc)
            )
        return Response(status_code=500, content="Processing error")

    return Response(status_code=200, content="OK")


async def _process_webhook(event_type: str, payload: dict, supabase) -> None:
    """Process a Lemon Squeezy webhook event."""
    data = payload.get("data", {})
    attributes = data.get("attributes", {})

    # Extract customer email to find our user
    customer_email = attributes.get("user_email") or attributes.get("email")
    ls_customer_id = str(data.get("id", ""))

    if event_type == "subscription_created":
        await _handle_subscription_created(
            supabase, customer_email, ls_customer_id
        )

    elif event_type == "subscription_cancelled":
        await _handle_subscription_cancelled(
            supabase, customer_email, ls_customer_id
        )

    elif event_type == "subscription_payment_failed":
        await _handle_payment_failed(
            supabase, customer_email, ls_customer_id
        )

    else:
        logger.info(f"Unhandled Lemon Squeezy event: {event_type}")


async def _handle_subscription_created(
    supabase, customer_email: str, ls_customer_id: str
) -> None:
    """Activate basic tier for the subscribing user."""
    if not customer_email:
        logger.warning("subscription_created: no customer email in payload")
        return

    result = supabase.table("users").update({
        "tier": "basic",
        "lemon_squeezy_customer_id": ls_customer_id,
    }).eq("email", customer_email).execute()

    if result.data:
        logger.info(f"Activated basic tier for {customer_email}")
    else:
        logger.warning(f"subscription_created: user not found for email {customer_email}")


async def _handle_subscription_cancelled(
    supabase, customer_email: str, ls_customer_id: str
) -> None:
    """Downgrade user to exhausted state (no more generations)."""
    if not customer_email:
        logger.warning("subscription_cancelled: no customer email in payload")
        return

    supabase.table("users").update({
        "tier": "exhausted",
    }).eq("email", customer_email).execute()

    logger.info(f"Downgraded to exhausted for {customer_email}")


async def _handle_payment_failed(
    supabase, customer_email: str, ls_customer_id: str
) -> None:
    """Flag account — block generation until payment resolved."""
    if not customer_email:
        return

    supabase.table("users").update({
        "tier": "exhausted",
    }).eq("email", customer_email).execute()

    logger.warning(f"Payment failed — blocked generation for {customer_email}")
