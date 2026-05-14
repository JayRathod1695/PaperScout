import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from middleware.auth import get_current_user
from models.responses import JobStatusResponse, RelatedPaper, Triage
from db.client import get_user_supabase

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBearer()


@router.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Poll job status and return results when done."""
    sb = get_user_supabase(credentials.credentials)

    job = (
        sb.table("search_jobs")
        .select("*")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not job.data:
        raise HTTPException(status_code=404, detail="Job not found")

    row = job.data[0]
    papers = []
    if row["status"] == "done":
        results = (
            sb.table("related_papers")
            .select("*")
            .eq("job_id", job_id)
            .order("relevance_score", desc=True)
            .execute()
        )
        papers = [
            RelatedPaper(
                id=p["id"],
                title=p["title"],
                authors=p["authors"] or [],
                url=p.get("url"),
                year=p.get("year"),
                triage=Triage(**p["triage"]),
                relevance_score=p["relevance_score"],
                relevance_reason=p.get("relevance_reason"),
            )
            for p in results.data
        ]

    return JobStatusResponse(
        job_id=job_id,
        status=row["status"],
        error_message=row.get("error_message"),
        papers_found=row.get("papers_found", 0),
        papers=papers,
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )


@router.patch("/job/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Cancel a pending job. Cannot cancel already-running jobs."""
    sb = get_user_supabase(credentials.credentials)

    job = (
        sb.table("search_jobs")
        .select("id, status")
        .eq("id", job_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not job.data:
        raise HTTPException(status_code=404, detail="Job not found")

    row = job.data[0]
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="Can only cancel pending jobs")

    sb.table("search_jobs").update({"status": "cancelled"}).eq("id", job_id).execute()
    return {"status": "cancelled"}


@router.post("/jobs/reset-stuck")
async def reset_all_stuck_jobs(
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Reset all stuck pending/running jobs for the current user."""
    sb = get_user_supabase(credentials.credentials)

    result = (
        sb.table("search_jobs")
        .update({"status": "failed", "error_message": "Force reset by user"})
        .eq("user_id", user_id)
        .in_("status", ["pending", "running"])
        .execute()
    )

    count = len(result.data) if result.data else 0
    logger.info(f"Force-reset {count} stuck job(s) for user {user_id}")
    return {"reset": count, "message": f"Reset {count} stuck job(s). You can now start a new search."}


@router.get("/search-jobs")
async def list_jobs_for_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """List search jobs for a given analysis_id, most recent first."""
    sb = get_user_supabase(credentials.credentials)

    result = (
        sb.table("search_jobs")
        .select("id, status, papers_found, created_at, completed_at")
        .eq("analysis_id", analysis_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    return {"jobs": result.data or []}
