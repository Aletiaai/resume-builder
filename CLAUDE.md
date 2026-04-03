
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Project Is

**CV Builder by Aletia** — a web application that generates tailored, ATS-optimized resumes for job seekers. Users upload their base resume once, then paste a job description every time they need a new tailored version. The app applies a proprietary resume methodology (defined in the skill files under `.claude/skills/`) to produce consistent, high-quality output. A multi-agent validation loop catches hallucinations before delivery.

Deployed at [cv.aletia.tech](https://cv.aletia.tech). Product of Aletia (Descifrador de Talento SAPI de CV).

The app is distributed through influencer affiliate channels. Lemon Squeezy handles subscriptions and automatic affiliate payouts. The UI is fully in Spanish. The resume generation engine supports both Spanish and English output.

---

## Tech Stack

- **Backend**: Python, FastAPI
- **Frontend**: Minimal HTML/CSS/JS (no heavy framework — keep it simple and fast). Uses the Aletia design system: DM Sans font (Google Fonts), `#1C1649` navy background, `#DB3D44` red accent, `#9B97C2` muted text, `rgba(255,255,255,0.05)` card surfaces. Dark theme throughout.
- **Database & Storage**: Supabase (Postgres for user data, Supabase Storage for resume files)
- **Document generation**: python-docx (DOCX output only — formatting specs are defined in the resume-tailor SKILL.md, do not redefine them here)
- **Payments & Affiliates**: Lemon Squeezy (webhooks for subscription events)
- **LLM APIs**: Google Gemini API only — every user provides their own Gemini API key, including during the free trial. The platform pays nothing for LLM calls.
- **Deployment**: Docker + Google Cloud Run. Cloud Run scales to zero when idle, keeping costs at zero during low-traffic periods. MVP traffic is expected to fall within GCP free tier limits.

---

## Project Structure

```
resume-builder/
├── CLAUDE.md                          ← this file
├── .claude/
│   └── skills/
│       ├── resume-tailor/
│       │   ├── SKILL.md               ← resume writing methodology (READ ONLY — never modify)
│       │   └── references/
│       │       ├── section-rules.md   ← bullet & section writing rules (always injected)
│       │       ├── spanish-format.md  ← Spanish-specific rules (injected when language == 'es')
│       │       └── formatting.md      ← DOCX spec (NOT injected — implemented in docx_service.py)
│       └── resume-validator/
│           └── SKILL.md               ← hallucination detection rules (READ ONLY — never modify)
├── app/
│   ├── main.py                        ← FastAPI app entry point
│   ├── routers/
│   │   ├── auth.py                    ← user registration, login, session
│   │   ├── resume.py                  ← upload base resume, trigger generation
│   │   └── billing.py                 ← Lemon Squeezy webhook handler, subscription gate
│   ├── agents/
│   │   ├── orchestrator.py            ← coordinates the full agent loop
│   │   ├── tailor_agent.py            ← Agent 1: generates tailored resume draft
│   │   ├── validator_agent.py         ← Agent 2: detects hallucinations
│   │   └── repair_agent.py            ← Agent 3: rewrites flagged sections
│   ├── services/
│   │   ├── storage_service.py         ← Supabase file upload/download
│   │   ├── docx_service.py            ← DOCX generation, red highlights, Word comments
│   │   ├── llm_service.py             ← unified Gemini caller with retry logic
│   │   ├── skill_service.py           ← reads skill files from disk, concatenates for injection
│   │   └── logging_service.py         ← all DB log writes (never call Supabase from agents directly)
│   ├── models/
│   │   └── schemas.py                 ← Pydantic models for all request/response shapes
│   └── prompts.py                     ← centralized prompt templates
├── frontend/
│   ├── index.html                     ← landing page (in Spanish)
│   ├── app.html                       ← main user interface (in Spanish)
│   ├── favicon.ico
│   └── static/
│       ├── style.css                  ← Aletia design system (DM Sans, dark theme)
│       └── app.js
├── .github/
│   └── workflows/
│       └── deploy.yml                 ← CI/CD: deploys to Cloud Run on push to main
├── .gitignore
├── .dockerignore
├── .env.example                       ← all required env vars documented here, no secrets
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Development Commands

```bash
# Local development (requires .env populated from .env.example)
docker-compose up

# Run FastAPI without Docker
pip install -r requirements.txt
uvicorn app.main:app --reload

# Run all tests
pytest

# Run a single test
pytest tests/path/to/test_file.py::test_function_name -v

# Lint
ruff check app/

# Generate a Fernet key for GEMINI_KEY_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Skill Files — Critical Constraint

The files inside `.claude/skills/` contain the proprietary resume methodology. This is the core IP of this product.

**Claude Code must never modify, rewrite, or delete these files under any circumstance.**

Claude Code should read these files to understand what the agents are supposed to do, but must treat them as immutable inputs. They define the resume writing rules, bullet point structure, section formatting, DOCX formatting specs, and hallucination detection criteria.

---

## How Skill Files Are Used at Runtime

Skill files are **read from disk and injected directly into the prompt** on every call — no Gemini Files API, no file URIs, no expiry tracking.

`skill_service.get_skill_content(skill_name, language)` builds the injected content:
1. Reads `SKILL.md`, strips YAML frontmatter
2. Always appends `references/section-rules.md` (if the skill has a `references/` folder)
3. Appends `references/spanish-format.md` only when `language == "es"`
4. Never appends `references/formatting.md` — that spec is implemented directly in `docx_service.py`

The assembled text is wrapped in a `<skill_content>` tag and prepended to the user prompt in `llm_service.call()`.

The user's base resume is **not** part of the skill content — it is passed at runtime via the prompt template (`TAILOR_USER_PROMPT_TEMPLATE`) as `original_resume_text`.

`llm_service.py` handles all Gemini calls. Agents call `llm_service.call(agent_name, user_prompt, gemini_api_key, skill_name, language)` and never interact with the API client directly.

**Rate limit handling:** `llm_service.call()` automatically retries up to 3 times on a 429 response. It parses the suggested retry delay from the error message (`"Please retry in Xs"`) and waits that duration before retrying. Falls back to exponential backoff (30s → 60s → 120s) if the delay can't be parsed. After all retries are exhausted, raises `GeminiQuotaExhaustedError`.

**Typed LLM exceptions** — `llm_service.py` defines two custom exception classes that propagate to the orchestrator:
- `GeminiQuotaExhaustedError` — raised when `ResourceExhausted` survives all retries (daily quota reached)
- `GeminiInvalidKeyError` — raised immediately on `InvalidArgument`, `PermissionDenied`, or `Unauthenticated` (bad or revoked key)

The orchestrator catches each type and stores a specific status on the generation record: `failed_quota`, `failed_key`, `failed_timeout` (5-minute hard timeout enforced by `asyncio.wait_for` in the background task wrapper), or `failed` (generic). The polling endpoint maps these to an `error_code` field in the response so the frontend can show the right Spanish message. Never catch these exceptions in agents — let them propagate to the orchestrator.

---

## Two-Tier Subscription Model

| Tier | Who pays for API | Model | Limit |
|------|-----------------|-------|-------|
| Free trial | User provides their own Gemini API key | Gemini 2.5 Flash | 1 resume lifetime, enforced server-side |
| Basic (paid) | User provides their own Gemini API key | Gemini 2.5 Flash | Unlimited within Gemini free tier |

The platform pays nothing for LLM calls. Every user — including free trial users — must provide their own Gemini API key before generating any resume.

Free trial limit must be enforced in the backend (database counter on the user record), never in the frontend.

`free_trial_used` is set to `True` when the completed file is first served to the user (in `GET /resume/generation/{id}` when `status == "completed"`), not when generation is requested. This ensures a failed generation does not consume the trial.

After the free trial resume is downloaded, the user sees a paywall screen prompting them to subscribe.

---

## Gemini API Key Onboarding Flow

This is a critical UX flow. When a user subscribes (basic tier), they must provide their own Gemini API key. The app must guide them through this — do not just show an empty input field.

**Where it appears:** Immediately after account registration — before the user can generate any resume, including the free trial. Also accessible from account settings at any time.

**The UI must display these steps in Spanish:**

1. "Ve a Google AI Studio: aistudio.google.com"
2. "Inicia sesión con tu cuenta de Google"
3. "Haz clic en 'Get API Key' → 'Create API key'"
4. "Copia tu API key y pégala aquí:"
   [input field]
5. "Guarda tu API key" [button]

Include a note below the button: "Tu API key se almacena de forma segura y nunca se comparte. La capa gratuita de Gemini es suficiente para generar varios currículums al día."

**Storage:** The Gemini API key is stored encrypted in the Supabase `users` table. Use Fernet symmetric encryption (`cryptography` library). The encryption key lives in environment variables. The raw key is never returned to the frontend after saving — only a masked version (e.g. `AIza...XyZ`) is shown to confirm it is saved.

**Validation:** On save, make a lightweight test call to the Gemini API to confirm the key is valid before storing it. If invalid, show: "Esta API key no es válida. Verifica que la copiaste correctamente."

---

## Agent Architecture & Orchestration Loop

All resume generation goes through `orchestrator.py`. The flow is:

```
1. Tailor Agent
   - Input: original resume (text) + job description
   - Skill used: resume-tailor SKILL.md (injected directly into the prompt)
   - Language: detects language of the job description and generates resume in the same language
   - Output: tailored resume as structured JSON (sections: summary, experience, skills, education)

2. Validator Agent
   - Input: original resume (text) + tailored resume JSON
   - Skill used: resume-validator SKILL.md
   - Language: operates in the same language as the resume being validated
   - Task: check every claim in the tailored resume against the original
   - Flags: added words, combined bullet points, inferred skills, fabricated metrics,
            amplified language (e.g. "AI automation" when original says "automation"),
            inferred soft skills, reworded achievements that change meaning
   - Output: PASS or list of flagged items with section name, original text, and flagged text

3. If PASS → proceed to DOCX generation

4. If FAIL → Repair Agent
   - Input: flagged items + relevant section from resume-tailor SKILL.md + original source text
   - Task: rewrite only the flagged section(s), grounded strictly in the original resume
   - Output: corrected section(s)
   - Loop back to Validator Agent

5. Maximum validation attempts: 3
   - After 3 failed loops, stop and deliver the document
   - Sections that failed validation after 3 attempts: highlighted in red in the DOCX
   - A Word comment is added to each highlighted section (in Spanish):
     "No pudimos verificar este contenido en tu currículum original. Revísalo antes de enviarlo."
   - A banner shown in the UI (in Spanish):
     "No pudimos verificar [n] sección(es) de tu currículum. Están marcadas en rojo en el 
      documento. Revísalas antes de enviarlo al reclutador."
```

The orchestrator logs each validation attempt and result to `logs_validation` via `logging_service.py`.

**Validator result inference:** if the LLM response is valid JSON but omits the `"result"` key, the result is inferred from findings: empty findings → `PASS`, non-empty → `FAIL`. Never default to `FAIL` unconditionally (that was a bug that caused perpetual repair loops).

**Repair agent experience fallback:** the `experience` field uses `data.get("experience") or fallback`, consistent with all other fields. This ensures that if the LLM returns `null` or `[]` for experience, the original experience is preserved rather than silently using an empty list.

---

## DOCX Output Spec

All resumes are delivered as `.docx` files generated by `python-docx`.

**Formatting:** Follow the specs defined in the resume-tailor SKILL.md exactly. Do not define fonts, margins, or sizing here — the SKILL.md is the single source of truth for all formatting decisions.

**Validation failure highlighting:**
- Failed sections: `WD_COLOR_INDEX.RED` background highlight
- Word comment on each highlighted section explaining what was flagged (in Spanish)
- Filename format: `curriculum_[empresa]_[fecha].docx`

---

## Billing & Subscription Gate

Lemon Squeezy sends webhooks to `/billing/webhook` on subscription events.

- `subscription_created` → activate basic tier in database (user already has Gemini key from signup)
- `subscription_cancelled` → downgrade user to free trial exhausted state (no more generations)
- `subscription_payment_failed` → flag account, block generation until resolved

Every resume generation request must check subscription status server-side before proceeding. Never trust the frontend to enforce this.

Affiliate links follow the pattern: `https://yourapp.com/?aff=[influencer_code]`
The `?aff=` parameter is captured in `localStorage` on page load (so it survives navigation to `/app.html`) and passed as `?aff=` to `POST /auth/register`. The backend stores it in the `referral_code` column. `localStorage` is cleared after successful registration.

---

## Language Support

- **UI**: fully in Spanish — all labels, buttons, messages, error text, and onboarding instructions
- **Resume generation**: the tailor agent detects the language of the job description and generates the resume in that language (Spanish or English). This behavior is defined in the resume-tailor SKILL.md — do not reimplement it in code.
- **Validation**: the validator agent always operates in the same language as the resume being validated
- **i18n approach**: use a simple Python dict for UI strings — no external i18n library needed for MVP

---

## Privacy & Data Handling

- User base resumes are stored in Supabase Storage, scoped per user (no cross-user access)
- Gemini API keys are stored encrypted (Fernet) in the database, never appear in logs or API responses
- The platform has admin access to all stored resumes for quality monitoring and support — this must be disclosed in the privacy policy page
- No resume content is used for model training — do not send data to any fine-tuning endpoint

---

## Environment Variables (document all in .env.example)

```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
LEMON_SQUEEZY_WEBHOOK_SECRET=
LEMON_SQUEEZY_API_KEY=
SECRET_KEY=                        # for JWT session tokens
GEMINI_KEY_ENCRYPTION_KEY=         # Fernet key for encrypting user Gemini API keys
ENVIRONMENT=development            # development | production
```

---

## Deployment — Google Cloud Run

- Containerized with Docker; deployed to Google Cloud Run via `--source .` (Cloud Build builds the image)
- **CI/CD:** `.github/workflows/deploy.yml` triggers on every push to `main`. Authenticates with GCP using the `GCP_SA_KEY` GitHub secret (base64-encoded service account key) and runs `gcloud run deploy resume-builder --source . --region=us-central1 --platform=managed --allow-unauthenticated --project=resume-builder-aletia`
- Scales to zero when idle — no cost during low-traffic periods
- MVP traffic expected to stay within GCP free tier (2M requests/month, 360K GB-seconds compute)
- `docker-compose.yml` is for local development only
- The service account behind `GCP_SA_KEY` needs: `roles/run.admin`, `roles/cloudbuild.builds.editor`, `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser`

---

## What Not to Build (MVP Scope)

Do not build these unless explicitly asked:

- In-app resume editor (users edit flagged sections in Word or Google Docs)
- Resume parsing from PDF (accept DOCX upload only for MVP)
- Email notifications
- Admin dashboard UI (use Supabase dashboard directly)
- Multiple resume templates
- LinkedIn import
- English UI version (Spanish only for MVP)

---

## Logging Strategy

Logging uses two layers: structured logs in Supabase (queryable, free tier) and Python's built-in `logging` module writing to local files (captures crashes before any DB write is possible).

All logging logic lives in `app/services/logging_service.py`. Agents and routers never write to the DB directly — they call `logging_service` functions.

### Supabase Log Tables

**`logs_llm_calls`** — every LLM call made by any agent
```
id, created_at, user_id, agent_name, model_used, tier,
system_prompt, input_prompt, output, tokens_input,
tokens_output, latency_ms, error (null if success)
```
Retention: 30 days (add a Supabase scheduled function to delete rows older than 30 days).
Reason: LLM call logs are large — full prompt + output for every call will grow fast.

**`logs_validation`** — every validation loop per resume generation
```
id, created_at, user_id, generation_id, attempt_number,
flagged_sections (JSON array), pass (bool),
final_outcome (pass | repaired | delivered_with_flags)
```
Retention: permanent. This is the primary quality monitoring dataset.

**`logs_user_events`** — user actions
```
id, created_at, user_id, event_type (upload | generate | download | gemini_key_saved),
metadata (JSON — e.g. job_description length, file size, tier used, language detected)
```
Retention: permanent.

**`logs_billing`** — every Lemon Squeezy webhook received
```
id, created_at, event_type, lemon_squeezy_payload (JSON),
processing_result (success | error), error_detail
```
Retention: permanent.

### Local File Logging

Use Python's `logging` module configured in `app/main.py` at startup.
- Log level: `DEBUG` in development, `INFO` in production
- Output: rotating file handler → `logs/app.log` (max 10MB, keep 5 rotations)
- Always log: uncaught exceptions, startup/shutdown events, any error before DB is available
- Format: `[timestamp] [level] [module] message`

### What to Log at Each Layer

**Orchestrator (`orchestrator.py`):**
- Log to `logs_user_events` when generation starts and completes
- Log to `logs_validation` after each validator agent response
- Log to `logs_llm_calls` after every agent call (tailor, validator, repair)
- On unhandled exception: log to local file + `logs_user_events` with event_type `generation_error`

**Billing router (`billing.py`):**
- Log every incoming webhook to `logs_billing` immediately on receipt, before processing
- Log the processing result as an update to the same row

**Never log:**
- Raw resume content in any log table (privacy)
- Gemini API keys in any log table or local file
- JWT tokens or passwords

### Useful Debug Queries (Supabase SQL Editor)

```sql
-- All failed validation loops this week
SELECT * FROM logs_validation
WHERE pass = false AND created_at > now() - interval '7 days'
ORDER BY created_at DESC;

-- All LLM calls for a specific generation
SELECT agent_name, model_used, latency_ms, error
FROM logs_llm_calls
WHERE user_id = '[user_id]'
ORDER BY created_at ASC;

-- Billing events that failed to process
SELECT * FROM logs_billing
WHERE processing_result = 'error'
ORDER BY created_at DESC;
```

---

## Profile Completion & Contact Information

Users must complete a profile step before their first generation. The profile collects the contact information used verbatim in the resume header. This appears after Gemini key setup and before the upload screen.

**Screen order:** auth → gemini key → **profile** → upload → generate

**Fields collected (`users` table columns):**
- `resume_city` — city and country (e.g. "Ciudad de México, México") — required
- `resume_phone` — phone with country code (e.g. "+52 55 1234 5678") — required
- `resume_email` — email for the resume header; pre-filled with account email — required
- `resume_linkedin` — LinkedIn profile URL — optional

**Gate:** `_check_generation_gate` in `resume.py` blocks generation if any required field is missing, returning HTTP 403. The frontend redirects to `screen-profile`.

**Contact info in the tailor agent:** `resume.py` extracts the 4 fields from the user record and passes them as `contact_info` to the orchestrator → tailor agent. The `TAILOR_USER_PROMPT_TEMPLATE` injects them as authoritative values and explicitly instructs the model to copy them verbatim into `contact_line` — never infer from the original resume.

**Validator bypass:** `VALIDATOR_USER_PROMPT_TEMPLATE` includes an explicit instruction not to validate or flag the `contact_line` field, since it comes from verified profile data rather than the uploaded resume.

**`has_profile` flag:** computed in `GET /auth/me` as `bool(city and phone and resume_email)`. The frontend uses this to decide whether to show `screen-profile` during bootstrap.

---

## Future Improvements

**LinkedIn URL as validator cross-reference:** The user's LinkedIn URL is collected during profile completion and stored in `users.resume_linkedin`. A future improvement is to use this URL to cross-reference the user's real job titles, companies, and dates against what the tailor agent generates — adding an additional validation layer beyond comparing against the uploaded base resume. This would require fetching and parsing the LinkedIn profile at generation time, which has rate limiting and authentication considerations to solve first.

**Call budget per generation:** Consider capping the total number of Gemini API calls per resume generation to protect users on the free Gemini tier from quota exhaustion. Suggested cap: 8 calls total (1 tailor + 1 validator + up to 2 repair batches + 1 final validator + buffer). Track call count in the orchestrator and skip remaining repair/validation loops when the budget is reached, delivering with flags instead.

---

## Code Conventions

- All endpoints return JSON with consistent shape: `{ success: bool, data: any, error: str | null }`
- Use Pydantic models for all request/response validation — no raw dicts in route handlers
- All agent calls are async
- Errors are caught at the orchestrator level — agents raise exceptions, orchestrator handles them
- Write docstrings on all public functions
- No hardcoded strings in agent prompts — system prompts come from skill files only
- Generation `status` field values: `processing` | `completed` | `failed` | `failed_quota` | `failed_quota_daily` | `failed_key` | `failed_timeout`. The polling endpoint normalises all `failed_*` variants to `status: "failed"` before sending to the frontend, and adds a separate `error_code` field (`quota_exhausted` | `quota_daily` | `invalid_api_key` | `timeout` | `unknown`).
- Frontend error messages are always in Spanish. Use `showErrorHTML()` (not `showError()`) when the message includes a link.