import asyncio
import logging
from datetime import datetime, timezone

from config import settings
from db.client import get_supabase
from services.email import send_failure_email, send_results_email
from services.model import extract_keywords, triage_with_relevance
from services.openalex import search_papers, search_papers_multi_query

logger = logging.getLogger(__name__)


async def run_search_agent(
    job_id: str,
    paper_text: str,
    user_goal: str,
    email: str,
    analysis_title: str,
) -> None:
    """
    Full search pipeline. Runs as a FastAPI BackgroundTask.
    """
    sb = get_supabase()
    now = lambda: datetime.now(timezone.utc).isoformat()

    logger.info(f"[Job {job_id}] Starting search agent")

    try:
        sb.table("search_jobs").update(
            {
                "status": "running",
                "started_at": now(),
            }
        ).eq("id", job_id).execute()

        logger.info(f"[Job {job_id}] Extracting keywords...")
        keywords = await asyncio.wait_for(extract_keywords(paper_text), timeout=120)
        logger.info(f"[Job {job_id}] Keywords extracted: {keywords}")

        if not keywords:
            raise ValueError("Keyword extraction returned empty list")

        await asyncio.sleep(1)
        logger.info(f"[Job {job_id}] Searching OpenAlex with keywords: {keywords}")
        papers = await search_papers(keywords, max_results=settings.max_related_papers)
        logger.info(f"[Job {job_id}] OpenAlex returned {len(papers)} papers")

        if len(papers) < 3:
            logger.info(f"[Job {job_id}] Only {len(papers)} results, trying broader search...")
            broader_keywords = keywords[:3]
            papers = await search_papers_multi_query(
                [broader_keywords, keywords[-3:]],
                max_results=settings.max_related_papers,
            )
            logger.info(f"[Job {job_id}] Broader search returned {len(papers)} papers")

        logger.info(f"[Job {job_id}] Found {len(papers)} candidate papers")

        if not papers:
            sb.table("search_jobs").update(
                {
                    "status": "done",
                    "papers_found": 0,
                    "completed_at": now(),
                }
            ).eq("id", job_id).execute()
            await send_results_email(email, job_id, analysis_title, 0)
            logger.info(f"[Job {job_id}] No papers found. Marked done.")
            return

        related_papers: list[dict] = []
        papers_stored = 0

        for i, paper in enumerate(papers):
            logger.info(
                f"[Job {job_id}] Triaging paper {i + 1}/{len(papers)}: '{paper['title'][:60]}'"
            )

            try:
                triage_result = await asyncio.wait_for(
                    triage_with_relevance(
                        title=paper["title"],
                        abstract=paper["abstract"],
                        user_goal=user_goal,
                    ),
                    timeout=120,
                )

                record = {
                    "job_id": job_id,
                    "title": paper["title"],
                    "authors": paper["authors"],
                    "url": paper["url"],
                    "year": paper["year"],
                    "abstract_excerpt": paper["abstract"][:300],
                    "triage": {
                        "claim": triage_result["claim"],
                        "method": triage_result["method"],
                        "catch": triage_result["catch"],
                        "verdict": triage_result["verdict"],
                        "verdict_reason": triage_result["verdict_reason"],
                        "steal": triage_result["steal"],
                    },
                    "relevance_score": float(triage_result["relevance_score"]),
                    "relevance_reason": triage_result.get("relevance_reason", ""),
                }

                # Store immediately — don't wait until all papers are done
                sb.table("related_papers").insert(record).execute()
                papers_stored += 1
                related_papers.append(record)

                # Update running count so frontend can show progress
                sb.table("search_jobs").update(
                    {"papers_found": papers_stored}
                ).eq("id", job_id).execute()

                logger.info(
                    f"[Job {job_id}] Stored paper {papers_stored}: '{paper['title'][:50]}' "
                    f"(relevance={record['relevance_score']:.2f})"
                )

            except Exception as exc:
                logger.warning(
                    f"[Job {job_id}] Failed to triage '{paper['title'][:50]}': {exc}"
                )
                continue

            if i < len(papers) - 1:
                await asyncio.sleep(settings.ai_call_delay_seconds)

        sb.table("search_jobs").update(
            {
                "status": "done",
                "papers_found": papers_stored,
                "completed_at": now(),
            }
        ).eq("id", job_id).execute()

        await send_results_email(email, job_id, analysis_title, papers_stored)

        logger.info(f"[Job {job_id}] Complete. {papers_stored} papers stored.")

    except Exception as exc:
        error_msg = str(exc)[:500]
        logger.error(f"[Job {job_id}] FAILED: {exc}", exc_info=True)

        try:
            sb.table("search_jobs").update(
                {
                    "status": "failed",
                    "error_message": error_msg,
                    "completed_at": now(),
                }
            ).eq("id", job_id).execute()
        except Exception as db_exc:
            logger.error(f"[Job {job_id}] Could not update job to failed: {db_exc}")

        try:
            await send_failure_email(email, job_id, error_msg)
        except Exception as email_exc:
            logger.error(f"[Job {job_id}] Could not send failure email: {email_exc}")