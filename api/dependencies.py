from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from core.database import AsyncSessionLocal
from models.dashboard import APIKey
from models.accounts import Organization, User

security = HTTPBearer()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def authenticate_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = None
):
    """
    Dependency to authenticate the API Key sent in the Bearer token.
    FastAPI will automatically inject the DB session from get_db, but we need Depends(get_db)
    Wait, Depends isn't allowed in def params here without Depends, so redefining properly:
    """
    pass # I will put pure logic in the router or proper Depends logic below

from fastapi import Depends

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> tuple[APIKey, Organization]:
    
    token = credentials.credentials
    if not token.startswith("fk-"):
        raise HTTPException(status_code=401, detail="Invalid API Key format. Must start with 'fk-'")

    stmt = select(APIKey).options(selectinload(APIKey.organization), selectinload(APIKey.linked_provider)).where(
        APIKey.key == token,
        APIKey.is_active == True
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or revoked API Key.")

    return api_key, api_key.organization
