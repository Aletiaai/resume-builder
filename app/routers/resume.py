"""Resume router — upload base resume and trigger generation."""

import asyncio
import logging
from io import BytesIO

from cryptography.fernet import Fernet
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agents import orchestrator
from app.models.schemas import APIResponse, GenerationRequest, GenerationStatusResponse
from app.routers.auth import get_current_user
from app.services.logging_service import LoggingService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resume", tags=["resume"])
_bearer = HTTPBearer()


def _decrypt_gemini_key(encrypted: str, fernet_key: str) -> str:
    """Decrypt the stored Gemini API key."""
    fernet = Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
    return fernet.decrypt(encrypted.encode()).decode()


def _check_generation_gate(user: dict) -> None:
    """Raise HTTPException if the user is not allowed to generate a resume."""
    tier = user["tier"]
    free_trial_used = user["free_trial_used"]

    if tier == "exhausted":
        raise HTTPException(
            status_code=403,
            detail="Tu período de prueba ha terminado. Suscríbete para continuar.",
        )
    if tier == "free_trial" and free_trial_used:
        raise HTTPException(
            status_code=403,
            detail="Ya usaste tu currículum de prueba. Suscríbete para generar más.",
        )
    if not user.get("gemini_api_key_encrypted"):
        raise HTTPException(
            status_code=403,
            detail="Debes guardar tu API key de Gemini antes de generar un currículum.",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=APIResponse)
async def upload_resume(
    request: Request,
    file: UploadFile,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Accept a .docx base resume, upload to Supabase Storage."""
    user = await get_current_user(credentials, request)
    storage_svc: StorageService = request.app.state.storage_svc
    logging_svc: LoggingService = request.app.state.logging_svc

    if not file.filename.endswith(".docx"):
        return APIResponse(success=False, error="Solo se aceptan archivos .docx.")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:  # 10 MB max
        return APIResponse(success=False, error="El archivo es demasiado grande (máx. 10 MB).")

    filename = f"base-resume-{user['id']}.docx"
    file_path = await storage_svc.upload_resume(
        user_id=user["id"],
        file_bytes=file_bytes,
        filename=filename,
    )

    # Persist the path on the user record so it survives logout/login
    supabase = request.app.state.supabase
    supabase.table("users").update({"base_resume_path": file_path}).eq("id", user["id"]).execute()

    await logging_svc.log_user_event(
        user_id=user["id"],
        event_type="upload",
        metadata={"file_size": len(file_bytes), "file_path": file_path},
    )

    return APIResponse(success=True, data={"file_path": file_path})


@router.post("/generate", response_model=APIResponse)
async def generate_resume(
    body: GenerationRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Trigger resume generation. Returns generation_id immediately.

    The actual work runs as a background task. Poll /generation/{id} for status.
    """
    import os

    user = await get_current_user(credentials, request)
    supabase = request.app.state.supabase
    storage_svc: StorageService = request.app.state.storage_svc
    logging_svc: LoggingService = request.app.state.logging_svc

    _check_generation_gate(user)

    # Decrypt the Gemini API key
    fernet_key = os.environ["GEMINI_KEY_ENCRYPTION_KEY"]
    gemini_api_key = _decrypt_gemini_key(user["gemini_api_key_encrypted"], fernet_key)

    # Download the base resume text
    try:
        resume_bytes = await storage_svc.download_resume(body.base_resume_path)
        # For DOCX files, extract text using python-docx
        original_resume_text = _extract_docx_text(resume_bytes)
    except Exception as e:
        logger.error(f"Failed to download base resume: {e}")
        return APIResponse(success=False, error="No se pudo leer el currículum base.")

    # Create a generation record
    gen_result = supabase.table("generations").insert({
        "user_id": user["id"],
        "status": "processing",
        "job_description": body.job_description,
    }).execute()

    if not gen_result.data:
        return APIResponse(success=False, error="Error al iniciar la generación.")

    generation_id = gen_result.data[0]["id"]

    # Run orchestration as background task
    background_tasks.add_task(
        _run_orchestrator,
        user_id=user["id"],
        generation_id=generation_id,
        original_resume_text=original_resume_text,
        job_description=body.job_description,
        target_company=body.target_company,
        gemini_api_key=gemini_api_key,
        supabase_client=supabase,
        storage_svc=storage_svc,
        logging_svc=logging_svc,
    )

    return APIResponse(
        success=True,
        data={"generation_id": generation_id},
    )


@router.get("/generation/{generation_id}", response_model=APIResponse)
async def get_generation_status(
    generation_id: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Poll for generation status. Returns signed download URL when complete."""
    user = await get_current_user(credentials, request)
    supabase = request.app.state.supabase
    storage_svc: StorageService = request.app.state.storage_svc
    logging_svc: LoggingService = request.app.state.logging_svc

    result = supabase.table("generations").select("*").eq("id", generation_id).eq(
        "user_id", user["id"]
    ).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Generación no encontrada.")

    gen = result.data
    download_url = None

    if gen["status"] == "completed" and gen.get("output_file_path"):
        try:
            download_url = await storage_svc.get_signed_url(gen["output_file_path"])
        except Exception as e:
            logger.error(f"Failed to get signed URL: {e}")

        # Mark free trial as used the first time the completed file is served
        if user["tier"] == "free_trial" and not user.get("free_trial_used"):
            supabase.table("users").update({
                "free_trial_used": True,
            }).eq("id", user["id"]).execute()

        # Log download event (only once — could track this more precisely)
        await logging_svc.log_user_event(
            user_id=user["id"],
            event_type="download",
            metadata={"generation_id": generation_id},
        )

    raw_status = gen["status"]
    # Map internal failure status codes to a clean error_code for the frontend.
    _status_to_error = {
        "failed_quota": "quota_exhausted",
        "failed_key": "invalid_api_key",
        "failed_timeout": "timeout",
        "failed": "unknown",
    }
    error_code = _status_to_error.get(raw_status)
    # Normalize all failure variants to "failed" so the frontend only checks one value.
    normalized_status = "failed" if error_code else raw_status

    response = GenerationStatusResponse(
        generation_id=generation_id,
        status=normalized_status,
        download_url=download_url,
        has_flagged_sections=gen.get("has_flagged_sections", False),
        flagged_section_count=gen.get("flagged_section_count", 0),
        error_code=error_code,
    )
    return APIResponse(success=True, data=response.model_dump())


# ---------------------------------------------------------------------------
# Background task wrapper
# ---------------------------------------------------------------------------

_GENERATION_TIMEOUT_SECONDS = 300  # 5 minutes


async def _run_orchestrator(**kwargs) -> None:
    """Thin wrapper: adds timeout and logs unhandled exceptions."""
    generation_id = kwargs.get("generation_id")
    supabase = kwargs.get("supabase_client")
    try:
        await asyncio.wait_for(orchestrator.run(**kwargs), timeout=_GENERATION_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error(f"Generation {generation_id} timed out after {_GENERATION_TIMEOUT_SECONDS}s")
        if supabase and generation_id:
            try:
                supabase.table("generations").update(
                    {"status": "failed_timeout"}
                ).eq("id", generation_id).execute()
            except Exception:
                pass
    except Exception as exc:
        # Orchestrator already updated the DB status — just log here.
        logger.exception(f"Background orchestrator failed: {exc}")


# ---------------------------------------------------------------------------
# DOCX text extraction
# ---------------------------------------------------------------------------

def _extract_docx_text(file_bytes: bytes) -> str:
    """Extract plain text from a DOCX file for use as resume source."""
    from docx import Document as DocxDocument
    doc = DocxDocument(BytesIO(file_bytes))
    lines = [para.text for para in doc.paragraphs if para.text.strip()]
    return "\n".join(lines)
