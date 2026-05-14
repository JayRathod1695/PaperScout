import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request

from db.client import get_supabase, get_user_supabase
from middleware.auth import get_current_user
from middleware.rate_limit import check_rate_limit
from models.requests import AnalyzeRequest
from models.responses import AnalysesListResponse, AnalysisSummary, AnalyzeResponse, Triage
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()
from services.arxiv import extract_text_from_arxiv
from services.pdf import extract_text_from_pdf_bytes
from services.model import triage_paper

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_paper(
    request: AnalyzeRequest,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Triage a paper from raw text or arxiv URL."""
    check_rate_limit(user_id, "/api/analyze")
    text = request.text
    title: str | None = None
    source_url = request.source_url

    # --- Input: arxiv URL ---
    if source_url and not text:
        try:
            text, title = await extract_text_from_arxiv(source_url)
        except Exception as exc:
            logger.error(f"Failed to fetch arxiv paper '{source_url}': {exc}")
            raise HTTPException(
                status_code=422,
                detail=f"Could not fetch or parse paper from URL: {exc}",
            )

    # --- Validate text ---
    if not text or len(text.strip()) < 100:
        raise HTTPException(
            status_code=422,
            detail="Paper text is too short to analyze (minimum 100 characters).",
        )

    from config import settings
    if len(text) > settings.max_text_length:
        text = text[:settings.max_text_length]
        logger.warning(f"Paper text truncated to {settings.max_text_length} chars for user {user_id}")

    # --- Triage via AI ---
    try:
        triage_result = await triage_paper(text)
    except NotImplementedError:
        raise HTTPException(
            status_code=501,
            detail="AI model not configured. Open services/model.py and plug in your model.",
        )
    except Exception as exc:
        logger.error(f"AI triage failed: {exc}")
        raise HTTPException(status_code=502, detail="AI service temporarily unavailable. Please retry.")

    # --- Derive title if not extracted ---
    if not title:
        # Use first 100 chars of claim as fallback title
        title = triage_result.get("claim", "")[:100] or "Untitled Paper"

    # --- Store in DB (abstract_excerpt only — never full text) ---
    token = credentials.credentials
    sb = get_user_supabase(token)
    try:
        result = (
            sb.table("analyses")
            .insert({
                "user_id": user_id,
                "title": title,
                "source_url": source_url,
                "abstract_excerpt": text[:500],
                "triage": triage_result,
            })
            .execute()
        )
        analysis_id = result.data[0]["id"]
    except Exception as exc:
        logger.error(f"DB insert failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save analysis.")

    logger.info(f"Analysis {analysis_id} created for user {user_id}")
    return AnalyzeResponse(
        analysis_id=analysis_id,
        title=title,
        triage=Triage(**triage_result),
    )




@router.post("/analyze/file", response_model=AnalyzeResponse)
async def analyze_pdf_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Triage a paper from an uploaded PDF file."""
    check_rate_limit(user_id, "/api/analyze/file")
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    try:
        file_bytes = await file.read()
        text = extract_text_from_pdf_bytes(file_bytes)
    except Exception as exc:
        logger.error(f"Failed to extract text from PDF: {exc}")
        raise HTTPException(status_code=422, detail="Could not read or extract text from this PDF.")
        
    if not text or len(text.strip()) < 100:
        raise HTTPException(
            status_code=422,
            detail="Could not extract enough text from this PDF. It may be image-only.",
        )
        
    from config import settings
    if len(text) > settings.max_text_length:
        text = text[:settings.max_text_length]
        logger.warning(f"PDF text truncated to {settings.max_text_length} chars for user {user_id}")

    try:
        triage_result = await triage_paper(text)
    except Exception as exc:
        logger.error(f"AI triage failed: {exc}")
        raise HTTPException(status_code=502, detail="AI service temporarily unavailable. Please retry.")

    title = file.filename or "Uploaded PDF Document"

    token = credentials.credentials
    sb = get_user_supabase(token)
    try:
        result = (
            sb.table("analyses")
            .insert({
                "user_id": user_id,
                "title": title,
                "source_url": None,
                "abstract_excerpt": text[:500],
                "triage": triage_result,
            })
            .execute()
        )
        analysis_id = result.data[0]["id"]
    except Exception as exc:
        logger.error(f"DB insert failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save analysis.")

    logger.info(f"Analysis {analysis_id} created from PDF for user {user_id}")
    return AnalyzeResponse(
        analysis_id=analysis_id,
        title=title,
        triage=Triage(**triage_result),
    )


@router.get("/analyses", response_model=AnalysesListResponse)
async def list_analyses(
    limit: int = 20,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Return paginated list of the authenticated user's analyses."""
    token = credentials.credentials
    sb = get_user_supabase(token)
    result = (
        sb.table("analyses")
        .select("id, title, source_url, triage, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    total_result = (
        sb.table("analyses")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )

    analyses = []
    for row in result.data:
        job_check = (
            sb.table("search_jobs")
            .select("id")
            .eq("analysis_id", row["id"])
            .limit(1)
            .execute()
        )
        analyses.append(
            AnalysisSummary(
                id=row["id"],
                title=row.get("title"),
                source_url=row.get("source_url"),
                triage=row["triage"],
                created_at=row["created_at"],
                has_search_job=bool(job_check.data),
            )
        )

    return AnalysesListResponse(
        analyses=analyses,
        total=total_result.count or 0,
    )


@router.get("/analyses/{analysis_id}", response_model=AnalyzeResponse)
async def get_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Return a single analysis. 404 if not found or not owned by user."""
    token = credentials.credentials
    sb = get_user_supabase(token)
    result = (
        sb.table("analyses")
        .select("*")
        .eq("id", analysis_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    row = result.data[0]
    return AnalyzeResponse(
        analysis_id=row["id"],
        title=row.get("title"),
        triage=Triage(**row["triage"]),
    )
