# Section Writing Rules

---

## 1. HEADER

**English label:** *(no label — just the content)*
**Spanish label:** *(no label — just the content)*

### Format:
- Line 1: **Full Name** — 16pt, bold, centered
- Line 2: City, ZIP | +CountryCode PhoneNumber | email | LinkedIn URL — 9pt, centered, single line

### Rules:
- Always include country code in phone number (e.g., +(52) 5611652690)
- Use the pipe character `|` as separator between contact elements
- LinkedIn URL must be the full URL (https://www.linkedin.com/in/...)
- Do NOT add a label or title above the header

### Example:
```
Marco García
Mexico City, C.P. 11820 | +(52) 5611652690 | marko.garcia@gmail.com | https://www.linkedin.com/in/marcogmtz/
```

---

## 2. SUMMARY

**English label:** `SUMMARY`
**Spanish label:** → see spanish-format.md

### Structure (3 parts):

**Part 1 — Career Summary (1 sentence):**
Formula: `[Adjective] [Job Title] with X+ years of experience [Value Proposition with Metrics]`

Example:
> "Innovative CSM with 7+ years of experience driving 7-figure growth for health-focused SaaS companies."

- Adjective must be strong and relevant to the target role
- Value proposition should include a measurable outcome or metric
- Years of experience must match the user's actual background

**Part 2 — Case Studies (2–3 sentences):**
- Pick 2–3 of the most relevant achievements from the user's experience
- Each sentence = one concrete project or result
- Must be directly relevant to the target job description
- Include specific metrics where possible

**Part 3 — Extracurricular Value (1 sentence):**
- Showcase something that stretches beyond core work: certifications, languages, volunteering, awards
- Make it relevant to the company culture and role

### Rules:
- Total summary: 4–6 sentences
- Written in third person implied (no "I" pronoun)
- Mirror keywords from the job description naturally
- Do NOT use bullet points in the summary — flowing prose only
- Summary must appear at the very top (after header) — it is the most valuable real estate

---

## 3. KEY SKILLS

**English label:** `KEY SKILLS`
**Spanish label:** → see spanish-format.md

### Rules:
- Select skills **relevant to the target job description**
- Analyze the user's work experience and add any relevant skills missing from their original resume
- Organize in categories when the role requires multiple domains (e.g., AI tools, Cloud, Platforms)
- If the role is focused on a single domain, a flat pipe-separated list is acceptable
- Each category label is **bold**, followed by a colon, then pipe-separated values
- Do NOT include every skill the user has ever used — only what's relevant to this specific role
- Skills must be consistent with what appears in the work experience section

### Example (categorized):
```
Conversational AI | LLMs | RAG Architecture | NLU/ASR Concepts | Demo Design & Delivery
Pre-Sales & Solution Engineering | API Integrations | Python | GCP | Docker
```

### Example (categorized with labels):
```
**Agentes y Automatización**: LangChain, LangGraph, OpenAI API, Claude API
**Infraestructura Cloud**: GCP (Cloud Run), AWS (Fargate, DynamoDB), Docker
```

---

## 4. RELEVANT WORK EXPERIENCE

**English label:** `RELEVANT WORK EXPERIENCE`
**Spanish label:** → see spanish-format.md

### Job Entry Format:
- Line 1: **Company Name | Job Title** (bold, 10pt) — dates right-aligned on same line using tab stop
- Dates format: `Mon YYYY – Mon YYYY` or `Mon YYYY – Current` (English) / `Mes AAAA – Actual` (Spanish)
- Bullet points follow immediately below — no blank line between title and bullets

### Bullet Point Rules:

**Formula (English):** 12–20 words total
**Formula (Spanish):** 18–25 words total

Each bullet must combine:
- **Skills/Technologies** (~7 words): hard & soft skills relevant to the role
- **Quantifiable Impact** (~3 words): specific numbers or percentages
- **Action Verbs** (~3 words): strong, results-oriented language
- **Context/Outcome** (~7 words): business impact and relevance

**3-Question Test — apply to EVERY bullet:**
1. Does this bullet include relevant keywords and skills?
2. Does this bullet include measurable/tangible results or outcomes?
3. If a hiring manager read this bullet, could they differentiate this candidate's value from the next 10 resumes?

→ If YES to all 3: keep the bullet
→ If NO to any 1: revise or remove it

**Bullet selection rules:**
- NOT all bullets from the original resume will be included — only those relevant to the target job description
- Minimum 2 bullets per role, maximum 5 bullets per role
- Roles are listed in **reverse chronological order** (most recent first)

**Strong bullet example:**
> "Designed and deployed RAG-based conversational tool on GCP, reducing LLM output errors by 79% in production."

Breaking it down:
- `{Designed and deployed}` — Action verbs
- `(RAG-based conversational tool on GCP)` — Industry terms / technologies
- `{reducing}` — Action verb
- `[79%]` — Measurable metric
- `(LLM output errors in production)` — Context/outcome

**What to avoid:**
- Vague statements with no metrics ("helped improve team performance")
- Responsibilities disguised as achievements ("responsible for managing...")
- Bullets over 20 words (English) or 25 words (Spanish)
- Repeating the same action verb across multiple bullets in the same role

---

## 5. EDUCATION

**English label:** `EDUCATION`
**Spanish label:** → see spanish-format.md

### Format:
Each entry on its own line:
`Degree/Certification Name | Institution | Month YYYY`

### Rules:
- List in reverse chronological order (most recent first)
- Include: degrees, diplomas, bootcamps, and relevant certifications
- For degrees, include field of study
- For scholarships, add a note (e.g., "Full Scholarship – GE Aviation")
- Do NOT include GPA unless specifically requested
- Do NOT include high school

### Example:
```
Machine Learning Operations Fundamentals | Google | Sep 2025
MS, Mechanical Design | CICATA | Full Scholarship – GE Aviation | Sep 2011–Sep 2014
Bachelor of Engineering | Tecnológico de Monterrey | Sep 2002–May 2007
```

---

## 6. LANGUAGES

**English label:** `LANGUAGES`
**Spanish label:** → see spanish-format.md

### Proficiency Scale:
Use exactly these three levels:
- **Native**
- **Fluent**
- **Intermediate**
- **Basic** (acceptable for very limited proficiency)

### Format:
Inline, pipe-separated:
`Language (Native) | Language (Fluent) | Language (Intermediate)`

Or with detail:
`English C1 (Fluent - Speaking & Writing) | Spanish (Native) | French (Basic)`

### Rules:
- Always list the user's native language
- Use the proficiency level the user provided — do not guess or upgrade levels
- If the job description is in a specific language, list that language first

---

## CRITICAL — Strict Source Fidelity Rule

This rule applies to ALL sections, especially bullet points in Work Experience.

Every bullet point MUST be directly traceable to the user's source resume. Claude must NOT:
- Infer, synthesize, or extrapolate actions or responsibilities not explicitly stated in the source
- Upgrade or embellish a role (e.g., adding "executive leadership advisory" if the source only mentions automation)
- Combine two separate facts into one bullet if the combination creates a new implied claim
- Use phrases like "advised leadership", "drove strategy", or "managed P&L" unless those exact concepts appear in the source

If the source resume does not contain enough strong bullets for a given role, use fewer bullets (minimum 2) rather than fabricating content.

**When in doubt: paraphrase the source closely. Never invent.**