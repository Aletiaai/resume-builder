"""Pydantic models for all request/response shapes."""

from typing import Any, Optional
from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# Standard API envelope
# ---------------------------------------------------------------------------

class APIResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: str
    email: str
    tier: str
    free_trial_used: bool
    has_gemini_key: bool
    gemini_key_masked: Optional[str] = None
    base_resume_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Gemini API key
# ---------------------------------------------------------------------------

class GeminiKeyRequest(BaseModel):
    api_key: str

    @field_validator("api_key")
    @classmethod
    def must_start_with_aiza(cls, v: str) -> str:
        if not v.startswith("AIza"):
            raise ValueError("La API key de Gemini debe comenzar con 'AIza'.")
        return v.strip()


class GeminiKeyResponse(BaseModel):
    masked_key: str


# ---------------------------------------------------------------------------
# Resume generation
# ---------------------------------------------------------------------------

class GenerationRequest(BaseModel):
    job_description: str
    base_resume_path: str


class GenerationStatusResponse(BaseModel):
    generation_id: str
    status: str  # processing | completed | failed
    download_url: Optional[str] = None
    has_flagged_sections: bool = False
    flagged_section_count: int = 0


# ---------------------------------------------------------------------------
# Internal agent types
# ---------------------------------------------------------------------------

class ExperienceEntry(BaseModel):
    company: str
    title: str
    dates: str
    bullets: list[str]


class TailoredResume(BaseModel):
    language: str  # "en" | "es"
    candidate_name: str
    contact_line: str
    summary: str
    skills: list[str]
    experience: list[ExperienceEntry]
    education: list[str]
    languages_line: str
    target_company: str = ""


class ValidationFinding(BaseModel):
    severity: str  # CRITICAL | WARNING
    section: str
    pattern: str
    original_text: str
    flagged_text: str
    explanation: str
    repair_instruction: str


class ValidationResult(BaseModel):
    result: str  # PASS | FAIL
    findings: list[ValidationFinding] = []


class RepairRequest(BaseModel):
    findings: list[ValidationFinding]
    original_resume_text: str
    tailored_resume: TailoredResume
