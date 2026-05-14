import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from db.client import get_supabase, init_supabase
from routes import analyze, jobs, search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def recover_orphaned_jobs() -> None:
    """
    On startup: mark any jobs stuck in 'running' or 'pending' as 'failed'.
    Both states mean the background task died with the previous server process.
    """
    try:
        sb = get_supabase()
        result = (
            sb.table("search_jobs")
            .update({
                "status": "failed",
                "error_message": "Server restarted during execution. Please retry.",
            })
            .in_("status", ["running", "pending"])
            .execute()
        )
        if result.data:
            logger.warning(f"Recovered {len(result.data)} orphaned job(s) on startup.")
    except Exception as exc:
        logger.error(f"Failed to recover orphaned jobs: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting PaperScout API...")
    try:
        init_supabase()
    except Exception as exc:
        logger.error(f"Supabase init failed on startup: {exc}")
        # Continue startup so health checks and local testing still work;
        # endpoints using Supabase should handle missing client at call time.
    else:
        try:
            await recover_orphaned_jobs()
        except Exception as exc:
            logger.error(f"Failed to recover orphaned jobs: {exc}")
    logger.info("PaperScout API ready.")
    yield
    logger.info("PaperScout API shutting down.")


app = FastAPI(
    title="PaperScout API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — only allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

# Routers
app.include_router(analyze.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")


@app.get("/health", tags=["health"])
async def health():
    """Health check — no auth required."""
    return {"status": "ok", "environment": settings.environment}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions."""
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
