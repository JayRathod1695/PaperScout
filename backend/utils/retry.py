import asyncio
import functools
import logging

logger = logging.getLogger(__name__)


def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """
    Decorator for async functions. Retries with exponential backoff on any exception.
    Usage: @retry_with_backoff(max_retries=3, base_delay=5.0)
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"[Retry] {func.__name__} attempt {attempt + 1}/{max_retries} "
                            f"failed: {exc}. Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
