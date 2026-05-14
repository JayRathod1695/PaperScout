import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _get_sender() -> dict:
    return {"name": settings.brevo_sender_name, "email": settings.brevo_sender_email}


async def send_results_email(
    email: str,
    job_id: str,
    paper_title: str,
    papers_found: int,
) -> None:
    """Send notification that search results are ready."""
    results_url = f"{settings.frontend_url}/search/{job_id}"
    title_display = paper_title or "your uploaded paper"
    subject = f"Your related papers are ready ({papers_found} found)"

    html = f"""
    <div style="font-family: system-ui, -apple-system, sans-serif; max-width: 520px; margin: 0 auto; color: #1a1a1a;">
        <h2 style="font-size: 20px; font-weight: 600; margin-bottom: 8px;">
            Your PaperScout results are ready
        </h2>
        <p style="color: #555; margin-bottom: 16px;">
            We found <strong>{papers_found} related papers</strong> for:
        </p>
        <p style="background: #f5f5f5; padding: 12px 16px; border-radius: 8px; font-style: italic; color: #333; margin-bottom: 20px;">
            {title_display}
        </p>
        <p style="color: #555; margin-bottom: 24px;">
            Each paper has been triaged and scored for relevance to your research goal.
        </p>
        <a href="{results_url}"
           style="display: inline-block; background: #000; color: #fff; padding: 12px 28px;
                  border-radius: 8px; text-decoration: none; font-weight: 500; font-size: 15px;">
            View Results ->
        </a>
        <p style="color: #aaa; font-size: 12px; margin-top: 32px; border-top: 1px solid #eee; padding-top: 16px;">
            PaperScout · built by a researcher, for researchers
        </p>
    </div>
    """

    await _send(email, subject, html)


async def send_failure_email(email: str, job_id: str, error: str) -> None:
    """Send notification that search job failed."""
    html = f"""
    <div style="font-family: system-ui, sans-serif; max-width: 520px; margin: 0 auto;">
        <h2 style="font-size: 18px;">Something went wrong with your PaperScout search</h2>
        <p style="color: #555;">
            Your related paper search encountered an issue. This is usually caused by a 
            temporary external service outage.
        </p>
        <p style="color: #555;">You can try again from the app.</p>
        <p style="color: #aaa; font-size: 11px; margin-top: 20px;">
            Job ID: {job_id}<br/>Error: {error[:200]}
        </p>
    </div>
    """
    await _send(email, "PaperScout search encountered an issue", html)


async def _send(to_email: str, subject: str, html_content: str) -> None:
    """Internal: POST to Brevo API."""
    if not settings.brevo_api_key:
        logger.info(f"Skipping email to {to_email} because BREVO key is not configured")
        return

    payload = {
        "sender": _get_sender(),
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                BREVO_URL,
                json=payload,
                headers={
                    "api-key": settings.brevo_api_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
        logger.info(f"Email sent to {to_email}: '{subject}'")
    except Exception as exc:
        logger.error(f"Failed to send email to {to_email}: {exc}")