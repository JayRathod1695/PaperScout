import logging
from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
security = HTTPBearer()

def get_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    return credentials.credentials
