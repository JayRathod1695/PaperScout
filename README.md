# PaperScout

AI-powered academic paper triage and related paper discovery.

Drop a PDF → get a brutally honest triage (claim, method, catch, verdict, steal) + 8 ranked related papers → emailed to you.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, Framer Motion |
| Backend | FastAPI, Python 3.11, Uvicorn |
| Database | Supabase (PostgreSQL + Auth + RLS) |
| AI Model | NVIDIA NIM — `nvidia/nvidia-nemotron-nano-9b-v2` (OpenAI-compatible) |
| Paper Search | OpenAlex API |
| Email | Brevo transactional email |

---

## Running Locally

**Terminal 1 — Backend:**
```bash
cd backend
python3.11 -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

App runs at `http://localhost:3000`

---

## Environment Setup

### Backend — `backend/.env`
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...          # service_role key
SUPABASE_JWT_SECRET=your-jwt-secret
AI_MODEL_API_KEY=nvapi-...           # NVIDIA NIM key
OPENALEX_API_KEY=your-key
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=you@gmail.com     # must be verified in Brevo
BREVO_SENDER_NAME=PaperScout
FRONTEND_URL=http://localhost:3000
ENVIRONMENT=development
MAX_RELATED_PAPERS=8
AI_CALL_DELAY_SECONDS=4.5
```

### Frontend — `frontend/.env.local`
```
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...  # anon/public key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Project Structure

```
paperscout/
├── backend/
│   ├── main.py               # App init, CORS, startup recovery, router mounts
│   ├── config.py             # All env vars via pydantic-settings
│   ├── db/
│   │   ├── client.py         # Supabase client singleton + user client factory
│   │   └── migrations/       # SQL schema
│   ├── middleware/
│   │   ├── auth.py           # JWT verification → user_id
│   │   └── rate_limit.py     # Per-user rate limiting
│   ├── models/
│   │   ├── requests.py       # Pydantic request bodies
│   │   └── responses.py      # Pydantic response bodies
│   ├── routes/
│   │   ├── analyze.py        # POST /analyze, GET /analyses, GET /analyses/{id}
│   │   ├── search.py         # POST /search-related, DELETE /search-related/{id}/stuck
│   │   └── jobs.py           # GET /job/{id}, PATCH /job/{id}/cancel, GET /search-jobs, POST /jobs/reset-stuck
│   ├── services/
│   │   ├── model.py          # AI: triage_paper, extract_keywords, triage_with_relevance
│   │   ├── openalex.py       # OpenAlex paper search
│   │   ├── arxiv.py          # arXiv PDF fetch (preserved, not exposed in UI)
│   │   ├── email.py          # Brevo transactional email
│   │   └── agent.py          # run_search_agent() — full pipeline orchestrator
│   ├── utils/
│   │   ├── retry.py          # @retry_with_backoff decorator
│   │   └── text.py           # Text utilities
│   └── requirements.txt
│
└── frontend/
    ├── app/
    │   ├── layout.tsx         # Root layout with providers
    │   ├── page.tsx           # Root redirect
    │   ├── login/             # Google OAuth login
    │   ├── dashboard/         # Paper archive list
    │   ├── upload/            # PDF upload + triage
    │   ├── analyze/[id]/      # Triage result + "Find Related" CTA
    │   └── search/[jobId]/    # Live job progress + related papers
    ├── components/
    │   ├── ui/                # Button, Badge, Spinner, Toast, Skeleton
    │   ├── NavBar.tsx
    │   ├── TriageCard.tsx     # Animated triage display
    │   ├── GoalInput.tsx      # Research goal form
    │   ├── UploadZone.tsx     # PDF drag-drop (URL/text preserved for future)
    │   └── PaperCardSkeleton.tsx
    ├── lib/
    │   ├── api.ts             # All backend API calls
    │   ├── supabase.ts        # Supabase browser client
    │   └── pdf.ts             # PDF.js helper
    ├── context/
    │   └── AuthContext.tsx    # Session state + useAuth()
    └── types/
        └── index.ts           # All TypeScript interfaces
```

---

## Key Features

- **PDF-only upload** — drag & drop a PDF, get instant AI triage
- **Triage card** — Claim · Method · Catch · Steal · Verdict (Read / Skim / Skip)
- **Related paper search** — 8 papers from OpenAlex, each triaged + relevance-scored by AI
- **Live results** — papers appear one by one as AI processes them (5s polling)
- **Email notification** — Brevo sends results when job completes
- **View previous results** — analyze page shows "View Results →" if a search was already done
- **Stuck job recovery** — server restart auto-resets pending/running jobs; manual reset endpoint available
- **Rate limiting** — per-user per-endpoint limits

---

## Architecture Notes

- Backend uses `get_user_supabase(token)` for all user-facing reads (RLS enforced via user JWT)
- Background agent uses `get_supabase()` (service key) for writes — bypasses RLS intentionally
- AI model is a thinking model; `reasoning_content` chunks are tracked separately from `content` chunks in the stream
- Paper abstracts from OpenAlex may contain `{` `}` — all prompt formatting uses `.replace()` not `.format()`
- Orphaned jobs (server restart mid-job) are reset to `failed` on startup
