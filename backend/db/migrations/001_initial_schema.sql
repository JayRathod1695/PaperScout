-- ============================================================
-- PROFILES TABLE
-- ============================================================
CREATE TABLE public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    display_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-create profile on new user signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
        NEW.raw_user_meta_data->>'avatar_url'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- ANALYSES TABLE
-- ============================================================
CREATE TABLE public.analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    title TEXT,
    source_url TEXT,
    abstract_excerpt TEXT,
    triage JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_analyses_user_id ON public.analyses(user_id);
CREATE INDEX idx_analyses_created_at ON public.analyses(created_at DESC);

-- ============================================================
-- SEARCH JOBS TABLE
-- ============================================================
CREATE TABLE public.search_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    analysis_id UUID NOT NULL REFERENCES public.analyses(id) ON DELETE CASCADE,
    user_goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed', 'cancelled')),
    error_message TEXT,
    papers_found INTEGER DEFAULT 0,
    email_to TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_search_jobs_user_id ON public.search_jobs(user_id);
CREATE INDEX idx_search_jobs_status ON public.search_jobs(status);
CREATE INDEX idx_search_jobs_analysis_id ON public.search_jobs(analysis_id);

-- ============================================================
-- RELATED PAPERS TABLE
-- ============================================================
CREATE TABLE public.related_papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES public.search_jobs(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    authors TEXT[],
    url TEXT,
    year INTEGER,
    abstract_excerpt TEXT,
    triage JSONB NOT NULL,
    relevance_score FLOAT NOT NULL CHECK (relevance_score >= 0 AND relevance_score <= 1),
    relevance_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_related_papers_job_id ON public.related_papers(job_id);
CREATE INDEX idx_related_papers_relevance ON public.related_papers(relevance_score DESC);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.search_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.related_papers ENABLE ROW LEVEL SECURITY;

-- Profiles: users see only their own
CREATE POLICY "Users see own profile" ON public.profiles
    FOR ALL USING (auth.uid() = id);

-- Analyses: users see only their own
CREATE POLICY "Users see own analyses" ON public.analyses
    FOR ALL USING (auth.uid() = user_id);

-- Search jobs: users see only their own
CREATE POLICY "Users see own jobs" ON public.search_jobs
    FOR ALL USING (auth.uid() = user_id);

-- Related papers: users see papers from their own jobs
CREATE POLICY "Users see own related papers" ON public.related_papers
    FOR SELECT USING (
        job_id IN (SELECT id FROM public.search_jobs WHERE user_id = auth.uid())
    );
