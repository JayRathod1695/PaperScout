import logging
from io import BytesIO

import httpx
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


async def extract_text_from_arxiv(url: str) -> tuple[str, str]:
    """
    Fetch a PDF from an arxiv URL and extract full text.
    Accepts both /abs/ and /pdf/ URL formats.
    Returns (extracted_text, title).
    Raises httpx.HTTPError on fetch failure.
    Raises ValueError if PDF text is empty (scanned/image-only PDF).
    """
    pdf_url = _normalize_to_pdf_url(url)
    logger.info(f"Fetching arxiv PDF from: {pdf_url}")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(pdf_url)
        response.raise_for_status()

    doc = fitz.open(stream=BytesIO(response.content), filetype="pdf")

    text_parts = []
    page_count = doc.page_count
    for page_index, page in enumerate(doc, start=1):
        page_text = page.get_text()
        page_preview = " ".join(page_text.split())[:40]
        if page_preview:
            logger.info(f"Arxiv page {page_index}/{page_count} preview: {page_preview}")
        else:
            logger.info(f"Arxiv page {page_index}/{page_count} preview: <no text extracted>")
        text_parts.append(page_text)

    full_text = "\n\n".join(text_parts).strip()

    if not full_text or len(full_text) < 200:
        doc.close()
        raise ValueError(
            "PDF appears to be image-only (scanned). Text extraction failed. "
            "Please paste the paper text manually."
        )

    # Try PDF metadata first, then heuristic
    title = doc.metadata.get("title", "").strip()
    if not title:
        title = _extract_title_heuristic(full_text)

    doc.close()
    logger.info(f"Extracted {len(full_text)} chars from arxiv PDF. Title: '{title[:60]}'")
    return full_text, title


def _normalize_to_pdf_url(url: str) -> str:
    """Convert any arxiv URL variant to the direct PDF URL."""
    # Remove trailing slash
    url = url.rstrip("/")
    # Convert /abs/ to /pdf/
    url = url.replace("/abs/", "/pdf/")
    # Ensure .pdf extension
    if not url.endswith(".pdf"):
        url += ".pdf"
    return url


def _extract_title_heuristic(text: str) -> str:
    """
    Attempt to extract paper title from extracted text.
    Title is usually in the first ~5 non-empty lines and is the longest.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()][:8]
    if not lines:
        return "Untitled Paper"
    # Filter out lines that look like page numbers or short noise
    candidates = [l for l in lines[:5] if len(l) > 10]
    if candidates:
        return max(candidates, key=len)[:200]
    return lines[0][:200]
