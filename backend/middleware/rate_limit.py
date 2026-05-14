import time
import logging
from collections import defaultdict
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# In-memory store: {user_id: [(timestamp, endpoint), ...]}
_request_log: dict[str, list[tuple[float, str]]] = defaultdict(list)

LIMITS = {
    "/api/analyze": (10, 3600),        # 10 per hour
    "/api/search-related": (3, 3600),  # 3 per hour
}


def check_rate_limit(user_id: str, endpoint: str) -> None:
    """
    Check if user has exceeded rate limit for this endpoint.
    Raises HTTP 429 if exceeded.
    Simple in-memory — resets on server restart (fine for demo).
    """
    if endpoint not in LIMITS:
        return

    max_requests, window_seconds = LIMITS[endpoint]
    now = time.time()
    cutoff = now - window_seconds

    # Clean old entries for this user
    _request_log[user_id] = [
        (ts, ep) for ts, ep in _request_log[user_id]
        if ts > cutoff
    ]

    # Count requests to this specific endpoint in window
    count = sum(1 for ts, ep in _request_log[user_id] if ep == endpoint)

    if count >= max_requests:
        logger.warning(f"Rate limit hit for user {user_id} on {endpoint}")
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {max_requests} requests per hour for this endpoint.",
        )

    # Record this request
    _request_log[user_id].append((now, endpoint))
