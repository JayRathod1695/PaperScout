# PaperScout — Build Plan (Completed)

## Status: ✅ Core Complete

All phases shipped and working in production (local).

---

## What Was Built

### Phase 1 — Foundation ✅
- Supabase project with 4 tables: `profiles`, `analyses`, `search_jobs`, `related_papers`
- Row Level Security on all tables
- Google OAuth via Supabase Auth
- FastAPI backend scaffold with JWT middleware
- Pydantic settings, Supabase singleton client

### Phase 2 — Core Triage ✅
- PDF upload → PyMuPDF text extraction
- AI triage via NVIDIA NIM (`nvidia/nvidia-nemotron-nano-9b-v2`)
- Streaming response handling with thinking token separation
- Triage stored in `analyses` table
- `POST /api/analyze/file` endpoint

### Phase 3 — Frontend ✅
- Next.js 14 App Router with TypeScript
- Google OAuth login flow
- Dashboard — paper archive with verdict badges
- Upload page — PDF drag-drop only (arXiv URL + paste text preserved in code for future)
- Analyze page — animated TriageCard with Claim/Method/Catch/Steal/Verdict
- Framer Motion animations throughout

### Phase 4 — Search Agent ✅
- `POST /api/search-related` — creates job, launches BackgroundTask
- `run_search_agent()` pipeline:
  1. Extract keywords via LLM
  2. Search OpenAlex (up to 8 papers)
  3. Triage each paper sequentially with relevance scoring
  4. Store each paper immediately as it's processed (not batched)
  5. Update `papers_found` count live
- `GET /api/job/{id}` — poll job status + results
- `GET /api/search-jobs?analysis_id=` — list jobs for an analysis
- Frontend polls every 5s, papers appear one by one as they arrive

### Phase 5 — Email + Polish ✅
- Brevo transactional email on job completion
- Sender email configurable via `BREVO_SENDER_EMAIL` env var
- Email sent banner animation on results page
- "View Results →" button on analyze page if search already done
- Download/open PDF button on each related paper card

### Phase 6 — Hardening ✅
- Startup recovery: resets `pending`/`running` jobs to `failed` on server restart
- `DELETE /api/search-related/{analysis_id}/stuck` — manual job reset endpoint
- `POST /api/jobs/reset-stuck` — reset all stuck jobs for current user
- Rate limiting middleware per user per endpoint
- Retry with exponential backoff on all AI calls
- 120s timeout on each LLM call via `asyncio.wait_for`
- Robust JSON parser handles: missing `{`, markdown code blocks, text before/after JSON, trailing commas
- Fixed `.format()` → `.replace()` for prompts (abstracts contain `{}` chars)
- Fixed streaming bug: `elif` → `if` for content chunks (thinking + content in same chunk)

---

## Bug Fixes Log

| Bug | Root Cause | Fix |
|---|---|---|
| `list indices must be integers` | `result.data` is a list, code used it as dict | `row = result.data[0]` |
| `PGRST116` on search-related | `.single()` throws when 0 rows | Removed `.single()`, check `.data` list |
| 404 on search-related | `get_supabase()` (no user JWT) → RLS blocks reads | Switched to `get_user_supabase(token)` |
| 42501 RLS violation on insert | Service key client had user JWT set via `postgrest.auth()` | Use user token client for all ops in search route |
| Job stuck as `pending` after restart | Startup recovery only reset `running`, not `pending` | Reset both `pending` and `running` on startup |
| LLM response missing `{` | First content chunk dropped by `elif` when thinking+content in same chunk | Changed `elif delta.content` → `if delta.content` |
| `KeyError: '\n  "claim"'` | `.format()` on prompt with abstract containing `{}` | Switched all prompt building to `.replace()` |
| LLM returns `</</</<` garbage | Model token budget exhausted by thinking | Raised `max_tokens` to 4096, reduced `max_thinking_tokens` to 1024 |
| Service key sees 0 rows | Supabase project has RLS enforced for service role | All routes use user token client |

---

## Current Architecture

```
User
  │
  ▼
Next.js 14 (localhost:3000)
  │  Authorization: Bearer <Supabase JWT>
  ▼
FastAPI (localhost:8000)
  │
  ├── middleware/auth.py          JWT → user_id
  ├── routes/analyze.py           PDF → triage
  ├── routes/search.py            start search job
  ├── routes/jobs.py              poll job / list jobs
  │
  ├── services/model.py           NVIDIA NIM (streaming, thinking model)
  ├── services/openalex.py        OpenAlex paper search
  ├── services/agent.py           background pipeline
  └── services/email.py           Brevo email
  │
  ▼
Supabase PostgreSQL
  ├── analyses          (triage results)
  ├── search_jobs       (job queue + status)
  ├── related_papers    (8 papers per job)
  └── profiles          (user data)
```

---

## Configuration Reference

| Setting | File | Default | Notes |
|---|---|---|---|
| `MAX_RELATED_PAPERS` | `backend/.env` | `8` | Papers fetched + triaged per job |
| `AI_CALL_DELAY_SECONDS` | `backend/.env` | `4.5` | Delay between LLM calls |
| `BREVO_SENDER_EMAIL` | `backend/.env` | — | Must be verified in Brevo dashboard |
| Poll interval | `frontend/app/search/[jobId]/page.tsx` | `5000ms` | How often frontend polls job status |
| Triage field labels | `frontend/components/TriageCard.tsx` | — | Edit `fieldOrder` array |
| Upload modes | `frontend/components/UploadZone.tsx` | PDF only | Set `ACTIVE_MODE` or restore `VISIBLE_MODES` |

---

## Future Work (Not Built)

- arXiv URL input (code preserved in `UploadZone.tsx`, just hidden)
- Paste text input (code preserved in `UploadZone.tsx`, just hidden)
- Semantic Scholar as fallback search source (`services/semantic_scholar.py` exists)
- Deployment (Vercel + Railway or similar)
- Paper-to-paper comparison
- Bulk upload
- User settings page
