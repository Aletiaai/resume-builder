"""Auth router — registration, login, session, and Gemini key management."""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.models.schemas import (
    APIResponse,
    GeminiKeyRequest,
    GeminiKeyResponse,
    LoginRequest,
    ProfileRequest,
    RegisterRequest,
    TokenResponse,
    UserProfile,
)
from app.services import llm_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_bearer = HTTPBearer()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


def _get_secret_key() -> str:
    return os.environ["SECRET_KEY"]


def _get_fernet() -> Fernet:
    key = os.environ["GEMINI_KEY_ENCRYPTION_KEY"]
    return Fernet(key.encode() if isinstance(key, str) else key)


def _create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        _get_secret_key(),
        algorithm=JWT_ALGORITHM,
    )


def _decode_token(token: str) -> str:
    """Decode JWT and return user_id. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[JWT_ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token inválido.")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    request: Request = None,
) -> dict:
    """Dependency: decode JWT and return the user row from DB."""
    user_id = _decode_token(credentials.credentials)
    supabase = request.app.state.supabase
    try:
        result = supabase.table("users").select("*").eq("id", user_id).single().execute()
    except Exception as exc:
        logger.error(f"get_current_user: DB query failed for user {user_id}: {exc}")
        raise HTTPException(status_code=503, detail="Error al verificar tu sesión. Intenta de nuevo.")
    if not result.data:
        raise HTTPException(status_code=401, detail="Usuario no encontrado.")
    return result.data


def _mask_key(key: str) -> str:
    """Return a masked version of the API key: AIza...XyZ."""
    if len(key) <= 8:
        return key[:4] + "..."
    return key[:4] + "..." + key[-3:]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=APIResponse)
async def register(body: RegisterRequest, request: Request):
    """Register a new user. Stores referral code from ?ref= query param."""
    supabase = request.app.state.supabase
    ref_code = request.query_params.get("aff")

    try:
        existing = supabase.table("users").select("id").eq("email", body.email).execute()
    except Exception as exc:
        logger.error(f"register: email check failed: {exc}")
        return APIResponse(success=False, error="Error al verificar el correo. Intenta de nuevo.")

    if existing.data:
        return APIResponse(success=False, error="Este correo ya está registrado.")

    password_hash = _hash_password(body.password)
    try:
        result = supabase.table("users").insert({
            "email": body.email,
            "password_hash": password_hash,
            "tier": "free_trial",
            "referral_code": ref_code,
        }).execute()
    except Exception as exc:
        logger.error(f"register: insert failed: {exc}")
        return APIResponse(success=False, error="Error al crear la cuenta. Intenta de nuevo.")

    if not result.data:
        return APIResponse(success=False, error="Error al crear la cuenta.")

    user_id = result.data[0]["id"]
    token = _create_token(user_id)
    return APIResponse(
        success=True,
        data=TokenResponse(access_token=token).model_dump(),
    )


@router.post("/login", response_model=APIResponse)
async def login(body: LoginRequest, request: Request):
    """Authenticate user and return JWT."""
    supabase = request.app.state.supabase

    try:
        result = supabase.table("users").select("*").eq("email", body.email).single().execute()
    except Exception as exc:
        logger.error(f"login: DB query failed: {exc}")
        return APIResponse(success=False, error="Error al iniciar sesión. Intenta de nuevo.")

    if not result.data:
        return APIResponse(success=False, error="Credenciales incorrectas.")

    user = result.data
    if not _verify_password(body.password, user["password_hash"]):
        return APIResponse(success=False, error="Credenciales incorrectas.")

    token = _create_token(user["id"])
    return APIResponse(
        success=True,
        data=TokenResponse(access_token=token).model_dump(),
    )


@router.get("/me", response_model=APIResponse)
async def get_me(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Return the current user's profile. Never returns the raw Gemini API key."""
    user = await get_current_user(credentials, request)
    has_key = bool(user.get("gemini_api_key_encrypted"))
    masked = None
    if has_key:
        try:
            fernet = _get_fernet()
            raw = fernet.decrypt(user["gemini_api_key_encrypted"].encode()).decode()
            masked = _mask_key(raw)
        except Exception:
            masked = "AIza...***"

    resume_first_name = user.get("resume_first_name")
    resume_last_name = user.get("resume_last_name")
    resume_city = user.get("resume_city")
    resume_phone = user.get("resume_phone")
    resume_email = user.get("resume_email")

    profile = UserProfile(
        id=user["id"],
        email=user["email"],
        tier=user["tier"],
        free_trial_used=user["free_trial_used"],
        has_gemini_key=has_key,
        gemini_key_masked=masked,
        base_resume_path=user.get("base_resume_path"),
        resume_first_name=resume_first_name,
        resume_last_name=resume_last_name,
        resume_city=resume_city,
        resume_phone=resume_phone,
        resume_email=resume_email,
        resume_linkedin=user.get("resume_linkedin"),
        has_profile=bool(
            resume_first_name and resume_last_name
            and resume_city and resume_phone and resume_email
        ),
    )
    return APIResponse(success=True, data=profile.model_dump())


@router.post("/gemini-key", response_model=APIResponse)
async def save_gemini_key(
    body: GeminiKeyRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Validate and save the user's Gemini API key (encrypted)."""
    user = await get_current_user(credentials, request)
    supabase = request.app.state.supabase
    logging_svc = request.app.state.logging_svc

    # Validate the key against the live Gemini API
    is_valid = await llm_service.test_api_key(body.api_key)
    if not is_valid:
        return APIResponse(
            success=False,
            error="Esta API key no es válida. Verifica que la copiaste correctamente.",
        )

    fernet = _get_fernet()
    encrypted = fernet.encrypt(body.api_key.encode()).decode()

    try:
        supabase.table("users").update({
            "gemini_api_key_encrypted": encrypted,
        }).eq("id", user["id"]).execute()
    except Exception as exc:
        logger.error(f"save_gemini_key: DB update failed for user {user['id']}: {exc}")
        return APIResponse(success=False, error="Error al guardar la API key. Intenta de nuevo.")

    await logging_svc.log_user_event(
        user_id=user["id"],
        event_type="gemini_key_saved",
        metadata={},
    )

    return APIResponse(
        success=True,
        data=GeminiKeyResponse(masked_key=_mask_key(body.api_key)).model_dump(),
    )


@router.post("/profile", response_model=APIResponse)
async def save_profile(
    body: ProfileRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Save the user's resume contact information."""
    user = await get_current_user(credentials, request)
    supabase = request.app.state.supabase

    try:
        supabase.table("users").update({
            "resume_first_name": body.first_name.strip(),
            "resume_last_name": body.last_name.strip(),
            "resume_city": body.city.strip(),
            "resume_phone": body.phone.strip(),
            "resume_email": str(body.resume_email).strip(),
            "resume_linkedin": body.linkedin_url.strip() if body.linkedin_url else None,
        }).eq("id", user["id"]).execute()
    except Exception as exc:
        logger.error(f"save_profile: DB update failed for user {user['id']}: {exc}")
        return APIResponse(success=False, error="Error al guardar el perfil. Intenta de nuevo.")

    return APIResponse(success=True, data={"saved": True})


@router.get("/gemini-key", response_model=APIResponse)
async def get_gemini_key_status(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """Return the masked Gemini API key (or null if not set)."""
    user = await get_current_user(credentials, request)
    has_key = bool(user.get("gemini_api_key_encrypted"))
    masked = None
    if has_key:
        try:
            fernet = _get_fernet()
            raw = fernet.decrypt(user["gemini_api_key_encrypted"].encode()).decode()
            masked = _mask_key(raw)
        except Exception:
            masked = "AIza...***"

    return APIResponse(
        success=True,
        data=GeminiKeyResponse(masked_key=masked).model_dump() if masked else None,
    )
