"""
Firma-KI Gateway — API Key Authentication
Validates Bearer tokens against the APIKey model using SQLAlchemy.
"""
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from datetime import datetime

from models.dashboard import APIKey
from api.dependencies import get_db

class APIKeyAuthenticationError(Exception):
    pass

async def authenticate_api_key(request, db):
    """
    Extract and validate the API key from the Authorization header.
    Returns (api_key, organization) tuple.
    Raises APIKeyAuthenticationError on failure.
    """
    auth_header = request.headers.get('Authorization', '')

    if not auth_header.startswith('Bearer '):
        raise APIKeyAuthenticationError('Missing or invalid Authorization header. Use: Bearer <api_key>')

    key_value = auth_header[7:].strip()

    stmt = select(APIKey).options(
        selectinload(APIKey.organization)
    ).where(
        APIKey.key == key_value,
        APIKey.is_active == True,
    )
    
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise APIKeyAuthenticationError('Invalid or revoked API key.')

    # Update last used timestamp
    api_key.last_used_at = datetime.utcnow()
    await db.commit()

    return api_key, api_key.organization
