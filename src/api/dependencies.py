import hashlib

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.storage.database import ApiKey, get_db
from src.storage.repositories import get_api_key_by_hash

security = HTTPBearer()


async def get_current_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """
    Validate Bearer token against hashed API keys stored in the database.

    The raw key is never stored — only its HMAC-SHA-256 with the configured salt.
    Returns the ApiKey record if valid and active, raises 401 otherwise.
    """
    key = credentials.credentials
    settings = get_settings()
    key_hash = hashlib.sha256(f"{settings.api_key_salt}{key}".encode()).hexdigest()
    api_key = await get_api_key_by_hash(db, key_hash)
    if not api_key or not api_key.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return api_key
