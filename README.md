# CV Builder by Aletia

A web application that generates tailored, ATS-optimized resumes for job seekers. Users upload their base resume once, then paste a job description every time they need a new tailored version. A multi-agent validation loop catches hallucinations before delivery. The UI is fully in Spanish; resume output supports both Spanish and English.

Product of [Aletia](https://aletia.tech) — deployed at [cv.aletia.tech](https://cv.aletia.tech).

---

## Table of Contents

- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Local setup](#local-setup)
- [Supabase setup](#supabase-setup)
- [Environment variables](#environment-variables)
- [Running locally](#running-locally)
- [Running with Docker](#running-with-docker)
- [API reference](#api-reference)
- [Agent architecture](#agent-architecture)
- [Subscription model](#subscription-model)
- [Deployment to Cloud Run](#deployment-to-cloud-run)
- [Logging](#logging)
- [Useful debug queries](#useful-debug-queries)

---

## How it works

1. User registers and provides their own Gemini API key (free — Gemini free tier is enough for several resumes per day)
2. User uploads their base resume once as a `.docx` file
3. User pastes a job description
4. Three AI agents run in sequence:
   - **Tailor Agent** — rewrites the resume to match the job description
   - **Validator Agent** — checks every claim against the original resume to detect hallucinations
   - **Repair Agent** — rewrites flagged sections, then re-validates (up to 3 attempts)
5. A formatted `.docx` is delivered for download. Sections that could not be verified after 3 attempts are highlighted in red with an explanatory comment.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI |
| Frontend | Vanilla HTML / CSS / JS (no framework) — Aletia design system (DM Sans, `#1C1649` / `#DB3D44`) |
| Database & Storage | Supabase (Postgres + Storage) |
| Document generation | python-docx |
| LLM | Google Gemini 2.5 Flash (user-provided API key) |
| Payments & Affiliates | Lemon Squeezy |
| Deployment | Docker + Google Cloud Run |

---

## Project structure

```
resume-builder/
├── .claude/
│   └── skills/
│       ├── resume-tailor/
│       │   ├── SKILL.md                ← resume writing methodology (READ ONLY)
│       │   └── references/
│       │       ├── section-rules.md    ← always injected into prompt
│       │       ├── spanish-format.md   ← injected only when language == 'es'
│       │       └── formatting.md       ← NOT injected; implemented in docx_service.py
│       └── resume-validator/
│           └── SKILL.md                ← hallucination detection rules (READ ONLY)
├── app/
│   ├── main.py                         ← FastAPI entry point, logging, lifespan
│   ├── prompts.py                      ← centralized prompt templates
│   ├── models/
│   │   └── schemas.py                  ← all Pydantic models
│   ├── agents/
│   │   ├── orchestrator.py             ← coordinates the full agent loop
│   │   ├── tailor_agent.py             ← generates tailored resume draft
│   │   ├── validator_agent.py          ← detects hallucinations
│   │   └── repair_agent.py             ← rewrites flagged sections
│   ├── routers/
│   │   ├── auth.py                     ← register, login, Gemini key management
│   │   ├── resume.py                   ← upload, generate, poll status
│   │   └── billing.py                  ← Lemon Squeezy webhook handler
│   └── services/
│       ├── logging_service.py          ← all DB log writes
│       ├── storage_service.py          ← Supabase Storage
│       ├── skill_service.py            ← reads skill files from disk, concatenates for prompt injection
│       ├── llm_service.py              ← unified Gemini caller
│       └── docx_service.py             ← DOCX generation
├── frontend/
│   ├── index.html                      ← landing page (Spanish)
│   ├── app.html                        ← authenticated app (Spanish)
│   ├── favicon.ico
│   └── static/
│       ├── app.js
│       └── style.css                   ← Aletia design system (DM Sans, dark navy theme)
├── logs/                               ← rotating log files (git-ignored)
├── .github/
│   └── workflows/
│       └── deploy.yml                 ← CI/CD: auto-deploy to Cloud Run on push to main
├── .gitignore
├── .dockerignore
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Prerequisites

- Python 3.12 (3.13 also works; 3.14 is not yet supported by pydantic-core as of March 29th 2026)
- A [Supabase](https://supabase.com) project
- A [Lemon Squeezy](https://lemonsqueezy.com) account (for billing)
- Docker (optional, for containerized local dev or deployment)

---

## Local setup

```bash
# Clone and enter the project
git clone <repo-url>
cd resume-builder

# Create a virtual environment with Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env template and fill in values
cp .env.example .env
```

---

## Supabase setup

Run the following DDL in your Supabase SQL Editor (**Dashboard → SQL Editor**):

```sql
-- USERS
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'free_trial' CHECK (tier IN ('free_trial','basic','exhausted')),
    gemini_api_key_encrypted TEXT,
    free_trial_used BOOLEAN NOT NULL DEFAULT FALSE,
    base_resume_path TEXT,
    referral_code TEXT,
    lemon_squeezy_customer_id TEXT,
    -- Resume header / profile fields
    resume_first_name TEXT,
    resume_last_name TEXT,
    resume_city TEXT,
    resume_phone TEXT,
    resume_email TEXT,
    resume_linkedin TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_ls ON users(lemon_squeezy_customer_id);

-- GENERATIONS
CREATE TABLE generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- status values: processing | completed | failed | failed_quota | failed_key | failed_timeout
    status TEXT NOT NULL DEFAULT 'processing',
    job_description TEXT NOT NULL,
    language_detected TEXT CHECK (language_detected IN ('en','es')),
    output_file_path TEXT,
    has_flagged_sections BOOLEAN NOT NULL DEFAULT FALSE,
    flagged_section_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_generations_user ON generations(user_id);

-- LOG TABLES
CREATE TABLE logs_llm_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    agent_name TEXT NOT NULL, model_used TEXT NOT NULL, tier TEXT NOT NULL,
    system_prompt TEXT, input_prompt TEXT, output TEXT,
    tokens_input INTEGER, tokens_output INTEGER, latency_ms INTEGER, error TEXT
);
CREATE INDEX idx_llm_created ON logs_llm_calls(created_at);

CREATE TABLE logs_validation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    generation_id UUID REFERENCES generations(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    flagged_sections JSONB, pass BOOLEAN NOT NULL,
    final_outcome TEXT CHECK (final_outcome IN ('pass','repaired','delivered_with_flags'))
);

CREATE TABLE logs_user_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL, metadata JSONB
);

CREATE TABLE logs_billing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT, lemon_squeezy_payload JSONB,
    processing_result TEXT DEFAULT 'pending' CHECK (processing_result IN ('success','error','pending')),
    error_detail TEXT
);

-- Row-level security (service key bypasses automatically)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE generations ENABLE ROW LEVEL SECURITY;
ALTER TABLE logs_llm_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE logs_validation ENABLE ROW LEVEL SECURITY;
ALTER TABLE logs_user_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE logs_billing ENABLE ROW LEVEL SECURITY;
```

**Existing database migration** — if the `users` table already exists, run this to add the profile columns:

```sql
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS resume_first_name TEXT,
  ADD COLUMN IF NOT EXISTS resume_last_name TEXT,
  ADD COLUMN IF NOT EXISTS resume_city TEXT,
  ADD COLUMN IF NOT EXISTS resume_phone TEXT,
  ADD COLUMN IF NOT EXISTS resume_email TEXT,
  ADD COLUMN IF NOT EXISTS resume_linkedin TEXT;
```

Then in the **Supabase Dashboard → Storage**:
- Create a bucket named `resumes`
- Set it to **Private**

Optionally, enable the `pg_cron` extension and schedule automatic cleanup of LLM call logs (they grow large — 30-day retention is recommended):

```sql
SELECT cron.schedule(
  'delete-old-llm-logs',
  '0 3 * * *',
  $$DELETE FROM logs_llm_calls WHERE created_at < NOW() - INTERVAL '30 days'$$
);
```

---

## Environment variables

Copy `.env.example` to `.env` and fill in all values:

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (bypasses RLS) |
| `LEMON_SQUEEZY_WEBHOOK_SECRET` | Signing secret from your Lemon Squeezy webhook settings |
| `LEMON_SQUEEZY_API_KEY` | Lemon Squeezy API key |
| `SECRET_KEY` | Random secret for signing JWTs |
| `GEMINI_KEY_ENCRYPTION_KEY` | Fernet key for encrypting user Gemini API keys |
| `ENVIRONMENT` | `development` or `production` |
| `APP_DOMAIN` | *(Production only)* Your app domain for CORS, e.g. `https://curriculo.ai` |

**Generating keys:**

```bash
# JWT secret
python3 -c "import secrets; print(secrets.token_hex(32))"

# Fernet key (for GEMINI_KEY_ENCRYPTION_KEY)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Running locally

```bash
# Activate venv
source .venv/bin/activate

# Start with hot reload
uvicorn app.main:app --reload

# App runs at http://localhost:8000
# Auto-generated API docs at http://localhost:8000/docs
```

---

## Running with Docker

```bash
# Build and start (mounts app/ and frontend/ for hot reload)
docker-compose up

# Rebuild after dependency changes
docker-compose up --build
```

The `docker-compose.yml` is for local development only. The `Dockerfile` is production-ready.

---

## API reference

All endpoints return a standard envelope:

```json
{ "success": true, "data": { ... }, "error": null }
```

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Register a new user. Accepts `?aff=<code>` for affiliate tracking. |
| `POST` | `/auth/login` | Authenticate and receive a JWT. |
| `GET` | `/auth/me` | Return the current user's profile. |
| `POST` | `/auth/gemini-key` | Validate and save a Gemini API key (encrypted). |
| `GET` | `/auth/gemini-key` | Return the masked key (e.g. `AIza...XyZ`). |
| `POST` | `/auth/profile` | Save resume contact info (`city`, `phone`, `resume_email`, `linkedin_url`). Required before first generation. |

### Resume

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/resume/upload` | Upload a `.docx` base resume to Supabase Storage. |
| `POST` | `/resume/generate` | Start resume generation. Returns `generation_id` immediately; work runs in background. Optional `target_company` field in body pre-fills the company name for the output filename. |
| `GET` | `/resume/generation/{id}` | Poll for generation status. Returns signed download URL when complete. On failure, includes `error_code`: `quota_exhausted` \| `invalid_api_key` \| `timeout` \| `unknown`. |

### Billing

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/billing/webhook` | Lemon Squeezy webhook receiver. Verifies HMAC-SHA256 signature. |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check for Cloud Run. Returns `{"status": "ok"}`. |

---

## Agent architecture

Resume generation runs through a three-agent pipeline coordinated by `orchestrator.py`:

```
POST /resume/generate
        │
        ▼
  [Background Task]
        │
        ▼
┌─────────────────┐
│  Tailor Agent   │  ← resume-tailor skill (injected directly into prompt)
│                 │    Input:  original resume text + job description
│                 │    Output: TailoredResume JSON
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Validator Agent │  ← resume-validator skill (injected directly into prompt)
│                 │    Input:  original resume + tailored resume JSON
│                 │    Output: PASS or FAIL with findings list
└────────┬────────┘
         │
    PASS │ FAIL (attempt < 3)
         │       │
         │       ▼
         │  ┌─────────────────┐
         │  │  Repair Agent   │  ← resume-tailor skill (repair mode)
         │  │                 │    Rewrites only flagged sections
         │  └────────┬────────┘
         │           │
         │           └──→ back to Validator Agent
         │
    FAIL (attempt 3)
         │
         ▼  (flagged sections highlighted red in DOCX)
         │
         ▼
┌─────────────────┐
│  DOCX Service   │  Formats document per resume-tailor spec
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Supabase Storage│  Stores .docx, returns signed URL
└─────────────────┘
```

**Skill files** are read from disk and injected directly into the prompt on every call — no Gemini Files API, no caching, no expiry. `skill_service.get_skill_content()` concatenates `SKILL.md` + `references/section-rules.md` (always) + `references/spanish-format.md` (Spanish only). `references/formatting.md` is not injected — it is implemented in code in `docx_service.py`.

**Rate limit handling:** `llm_service.call()` retries up to 3 times on 429, waiting the delay suggested in the Gemini error message before each retry. After all retries are exhausted, raises `GeminiQuotaExhaustedError`.

**API key errors:** `InvalidArgument`, `PermissionDenied`, and `Unauthenticated` from the Google API are caught immediately (no retry) and raise `GeminiInvalidKeyError`.

**Error classification in the orchestrator:** typed exceptions set specific status codes on the generation record (`failed_quota`, `failed_key`, `failed_timeout`, `failed`). The polling endpoint maps these to an `error_code` field and returns `status: "failed"` in all failure cases so the frontend only checks one value.

**Generation timeout:** the background task wrapper enforces a 5-minute (`300s`) hard timeout using `asyncio.wait_for`. Timeout sets status to `failed_timeout`.

**Frontend error messages** (Spanish, shown in-place):
| `error_code` | Message shown |
|---|---|
| `quota_exhausted` | Daily limit reached, resets at midnight Pacific |
| `invalid_api_key` | Key invalid/revoked + link to settings screen |
| `timeout` | Took too long, try again |
| `unknown` | Generic fallback |

**Validation failure handling:** if a section fails all 3 validation attempts, it is highlighted in red in the DOCX and a Spanish comment is added: *"No pudimos verificar este contenido en tu currículum original. Revísalo antes de enviarlo."* The user is shown a warning banner in the UI listing the number of flagged sections.

---

## Subscription model

| Tier | Condition | Limit |
|------|-----------|-------|
| `free_trial` | Default on registration | 1 resume lifetime |
| `basic` | Active Lemon Squeezy subscription | Unlimited |
| `exhausted` | Free trial used, or subscription cancelled/payment failed | Blocked |

Every user — including free trial — must provide their own Gemini API key before generating any resume. The platform pays nothing for LLM calls.

**Affiliate tracking:** append `?aff=<influencer_code>` to any page URL. The code is captured in `localStorage` on load and passed to `/auth/register` at signup, then stored in the `referral_code` column. Lemon Squeezy attributes commissions automatically.

**Lemon Squeezy webhook events handled:**

| Event | Action |
|-------|--------|
| `subscription_created` | Set user tier to `basic` |
| `subscription_cancelled` | Set user tier to `exhausted` |
| `subscription_payment_failed` | Set user tier to `exhausted` |

---

## Deployment to Cloud Run

Deployment is automated via GitHub Actions. Every push to `main` triggers `.github/workflows/deploy.yml`, which authenticates to GCP and runs:

```bash
gcloud run deploy resume-builder \
  --source . \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --project=resume-builder-aletia
```

`--source .` uses Cloud Build to build the container image — no manual `docker build/push` required.

**GitHub secret required:** `GCP_SA_KEY` — a base64-encoded GCP service account key JSON. The service account needs: `roles/run.admin`, `roles/cloudbuild.builds.editor`, `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser`.

**Required GCP APIs:** Cloud Run, Cloud Build, Artifact Registry.

**Important:** the app runs with `--workers 1`. Cloud Run scales via instances, not workers. The service scales to zero when idle — no cost during low-traffic periods. MVP traffic is expected to fall within the GCP free tier (2M requests/month, 360K GB-seconds compute).

---

## Logging

Two layers run in parallel:

**1. Supabase log tables** (queryable, structured):

| Table | What's logged | Retention |
|-------|--------------|-----------|
| `logs_llm_calls` | Every Gemini API call — agent name, model, tokens, latency, errors | 30 days |
| `logs_validation` | Every validation loop — attempt number, findings, outcome | Permanent |
| `logs_user_events` | User actions — upload, generate, download, gemini_key_saved | Permanent |
| `logs_billing` | Every Lemon Squeezy webhook — payload, processing result | Permanent |

**2. Local rotating file log** — `logs/app.log`:
- Format: `[timestamp] [level] [module] message`
- Max 10 MB per file, 5 rotations
- Level: `DEBUG` in development, `INFO` in production
- Captures crashes before any DB write is possible

**What is never logged:** raw resume content, Gemini API keys, JWT tokens.

---

## Useful debug queries

Run these in the **Supabase SQL Editor**:

```sql
-- All failed validation loops this week
SELECT * FROM logs_validation
WHERE pass = false AND created_at > now() - INTERVAL '7 days'
ORDER BY created_at DESC;

-- All LLM calls for a specific user
SELECT agent_name, model_used, latency_ms, error
FROM logs_llm_calls
WHERE user_id = '<user-id>'
ORDER BY created_at ASC;

-- Billing webhooks that failed to process
SELECT * FROM logs_billing
WHERE processing_result = 'error'
ORDER BY created_at DESC;

-- Resume generation funnel this month
SELECT
  COUNT(*) FILTER (WHERE event_type = 'generate_start') AS started,
  COUNT(*) FILTER (WHERE event_type = 'generate_complete') AS completed,
  COUNT(*) FILTER (WHERE event_type = 'generation_error') AS failed,
  COUNT(*) FILTER (WHERE event_type = 'download') AS downloaded
FROM logs_user_events
WHERE created_at > date_trunc('month', now());

-- Average validation attempts per generation
SELECT
  AVG(attempt_number) AS avg_attempts,
  COUNT(*) FILTER (WHERE final_outcome = 'pass') AS clean_passes,
  COUNT(*) FILTER (WHERE final_outcome = 'repaired') AS repaired,
  COUNT(*) FILTER (WHERE final_outcome = 'delivered_with_flags') AS flagged_deliveries
FROM logs_validation
WHERE final_outcome IS NOT NULL;
```

---

## Development commands

```bash
# Run all tests
pytest

# Run a single test
pytest tests/path/to/test_file.py::test_function_name -v

# Lint
ruff check app/

# Auto-fix lint issues
ruff check app/ --fix

# Generate a Fernet key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## What is not in the MVP

The following are explicitly out of scope and should not be built unless requested:

- In-app resume editor (users edit flagged sections in Word or Google Docs)
- Resume parsing from PDF (DOCX upload only)
- Email notifications
- Admin dashboard UI (use Supabase dashboard directly)
- Multiple resume templates
- LinkedIn import
- English UI (Spanish only)
