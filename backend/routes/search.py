import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db.client import get_user_supabase
from middleware.auth import get_current_user
from middleware.rate_limit import check_rate_limit
from models.requests import SearchRelatedRequest
from models.responses import SearchRelatedResponse
from services.agent import run_search_agent

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer()


@router.post("/search-related", response_model=SearchRelatedResponse)
async def search_related(
    request: SearchRelatedRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Trigger the background search agent.
    """
    check_rate_limit(user_id, "/api/search-related")

    token = credentials.credentials
    sb = get_user_supabase(token)

    # Verify analysis exists and belongs to user
    analysis = (
        sb.table("analyses")
        .select("id, title, abstract_excerpt")
        .eq("id", request.analysis_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not analysis.data:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analysis_row = analysis.data[0]

    # Prevent duplicate jobs
    existing = (
        sb.table("search_jobs")
        .select("id, status")
        .eq("analysis_id", request.analysis_id)
        .in_("status", ["pending", "running"])
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="A search job is already running for this paper",
        )

    # Resolve user's email from profiles (use request.email as fallback)
    profile = (
        sb.table("profiles").select("email").eq("id", user_id).execute()
    )
    resolved_email = None
    if profile.data and profile.data[0].get("email"):
        resolved_email = profile.data[0].get("email")
    else:
        resolved_email = request.email

    # Create job record
    job_result = (
        sb.table("search_jobs")
        .insert({
            "user_id": user_id,
            "analysis_id": request.analysis_id,
            "user_goal": request.user_goal,
            "email_to": resolved_email,
            "status": "pending",
        })
        .execute()
    )
    job_id = job_result.data[0]["id"]

    paper_text = analysis_row.get("abstract_excerpt") or ""
    analysis_title = analysis_row.get("title") or ""

    background_tasks.add_task(
        run_search_agent,
        job_id=job_id,
        paper_text=paper_text,
        user_goal=request.user_goal,
        email=resolved_email,
        analysis_title=analysis_title,
    )

    logger.info(f"Search job {job_id} queued for analysis {request.analysis_id}")
    return SearchRelatedResponse(job_id=job_id, status="pending")


@router.delete("/search-related/{analysis_id}/stuck")
async def reset_stuck_job(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Reset any stuck pending/running jobs for an analysis so a new search can be started."""
    sb = get_user_supabase(credentials.credentials)

    result = (
        sb.table("search_jobs")
        .update({"status": "failed", "error_message": "Manually reset by user"})
        .eq("analysis_id", analysis_id)
        .eq("user_id", user_id)
        .in_("status", ["pending", "running"])
        .execute()
    )

    count = len(result.data) if result.data else 0
    logger.info(f"Reset {count} stuck job(s) for analysis {analysis_id} by user {user_id}")
    return {"reset": count}
