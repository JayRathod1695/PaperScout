import inspect
import logging

import httpx
from supabase import Client, create_client
from config import settings

logger = logging.getLogger(__name__)

_supabase_client: Client | None = None


def _patch_httpx_proxy_compat() -> None:
    """
    Supabase/gotrue may pass `proxy=` to httpx.Client on environments where
    the installed httpx only accepts `proxies=`. Map the argument so client
    initialization succeeds without changing the global package set.
    """
    for client_cls in (httpx.Client, httpx.AsyncClient):
        init = client_cls.__init__
        signature = inspect.signature(init)
        if "proxy" in signature.parameters or "proxies" not in signature.parameters:
            continue

        def patched_init(self, *args, __init=init, **kwargs):
            proxy = kwargs.pop("proxy", None)
            if proxy is not None and "proxies" not in kwargs:
                kwargs["proxies"] = proxy
            return __init(self, *args, **kwargs)

        client_cls.__init__ = patched_init  # type: ignore[assignment]


def init_supabase() -> None:
    """Initialize the Supabase client singleton. Call once on startup."""
    global _supabase_client
    _patch_httpx_proxy_compat()
    _supabase_client = create_client(
        settings.supabase_url,
        settings.supabase_service_key,
    )
    logger.info("Supabase client initialized.")


def get_supabase() -> Client:
    """Return the Supabase client singleton. Must call init_supabase() first."""
    if _supabase_client is None:
        raise RuntimeError("Supabase client not initialized. Call init_supabase() first.")
    return _supabase_client

def get_user_supabase(token: str) -> Client:
    """Return a fresh Supabase client acting on behalf of the user."""
    client = create_client(
        settings.supabase_url,
        settings.supabase_service_key,
    )
    client.postgrest.auth(token)
    return client
