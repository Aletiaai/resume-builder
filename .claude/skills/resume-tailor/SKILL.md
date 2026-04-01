---
name: resume-tailor
description: >
  Use this skill whenever the user wants to build, tailor, optimize, or rewrite a resume
  for a specific job. Triggers include: "build me a resume", "tailor my resume", "update my resume
  for this job", "rewrite my CV", "optimize my resume", "help me apply for this role",
  "create a Spanish resume", "create an English resume", or any request combining a resume/CV
  with a job description or role. Always use this skill when a job description is provided,
  even if the user doesn't explicitly say "build a resume".
  Outputs a formatted .docx file ready to upload to Google Docs.
---

# Resume Builder Skill

Builds a tailored, formatted resume in English or Spanish as a `.docx` file based on:
1. The user's base resume (provided at runtime)
2. A target job description provided by the user

---

## Step 1 — Determine Language

Ask the user if they want the resume in **English** or **Spanish** if not already specified.

- English → follow English section titles and rules in this file
- Spanish → read `references/spanish-format.md` for section titles and Spanish-specific rules

---

## Step 2 — Load Base Resume & Analyze Inputs

### Base Resume
Use the base resume provided at runtime — it is passed directly in the prompt as the source of truth.

### From the Job Description, extract:
- Target job title
- Required hard skills and technologies
- Required soft skills
- Key responsibilities
- Company name and industry

### From the Base Resume, extract:
- All work experiences (company, title, dates, bullet points)
- Education history
- Skills inventory
- Languages
- Certifications / awards

---

## Step 3 — Build Each Section

Build sections in this order. Read `references/section-rules.md` for detailed writing rules for each section.

> ⚠️ **Source Fidelity:** Every bullet must be directly traceable to the source resume. Never infer, upgrade, or fabricate content. See the CRITICAL rule at the bottom of `references/section-rules.md`.

> ⚠️ **ATS Compatibility:** Do NOT use border lines on section headers. Plain bold text only. See `references/formatting.md`.

### English Section Titles (in order):
1. **Header**
2. **Summary**
3. **Key Skills**
4. **Relevant Work Experience**
5. **Education**
6. **Languages**

### Spanish Section Titles → see `references/spanish-format.md`

---

## Step 4 — Generate the .docx File

Use the `python-docx` library. Follow ALL formatting rules in `references/formatting.md`.

### Key formatting rules (quick reference):
- Font: **Arial** throughout
- Font color: **#111111** on every run (matches Google Docs default)
- Name (header): **16pt, bold, centered**
- Contact line: **9pt, centered**
- Section headers: **11pt, bold, ALL CAPS** — no border lines (ATS safe)
- Body text: **10pt**
- Text alignment: **JUSTIFIED** on all body paragraphs (except name and contact line)
- Job title lines: **10pt, bold** (Company | Title) with dates right-aligned using tab stops
- Bullet points: **10pt**, use proper list numbering (never raw unicode `•`)
- Margins: **top: 720, bottom: 720, left: 900, right: 900** (DXA)
- Page size: **US Letter** (12240 x 15840 DXA)

### Output filename:
`FirstName-LastName-resume-MonYY-XX.docx` (English)
`FirstName-LastName-CV-MonYY-XX.docx` (Spanish)
where `MonYY` = current month + 2-digit year, `XX` = first 2 letters of target company name.

- The generated .docx is returned as bytes by `docx_service.py`
- It is stored in Supabase Storage under the user's folder
- A signed download URL is returned to the frontend for the user to download

---

## Step 5 — Validate

After generating the .docx, `docx_service.py` validates the file structure:
- Confirm the file opens without XML errors
- Confirm all sections are present (Summary, Experience, Skills, Education, Languages)
- Confirm no placeholder text like `[AGREGAR VALOR]` exists without a red highlight and comment

If validation fails, attempt to regenerate once before returning an error to the orchestrator.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/section-rules.md` | Always — writing rules for every section |
| `references/spanish-format.md` | When building a Spanish resume |
| `references/formatting.md` | Always — full formatting spec for the .docx |