import logging
import httpx
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
 ) -> str:
    """
    Verify the Supabase access token with Supabase Auth.
    Returns the user_id (UUID string) on success.
    Raises HTTP 401 on any auth failure.
    """
    token = credentials.credentials
    try:
        auth_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
        headers = {
            "Authorization": f"Bearer {token}",
            "apikey": settings.supabase_service_key,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(auth_url, headers=headers)

        if response.status_code != 200:
            logger.warning(
                "Supabase token validation failed: %s %s",
                response.status_code,
                response.text[:200],
            )
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        payload = response.json()
        user_id: str | None = payload.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user id")
        return user_id
    except httpx.RequestError as exc:
        logger.error(f"Supabase auth validation request failed: {exc}")
        raise HTTPException(status_code=401, detail="Authentication service unavailable")
