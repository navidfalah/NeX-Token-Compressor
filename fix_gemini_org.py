import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from core.config import settings
from models.accounts import Organization, User
from models.dashboard import AIProvider

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def main():
    async with async_session() as session:
        # Get the first organization (assumed to be Navid's)
        org_result = await session.execute(select(Organization).limit(1))
        org = org_result.scalar_one_or_none()
        
        if org:
            # Update Gemini to belong to this org
            gem_result = await session.execute(select(AIProvider).where(AIProvider.name == "Gemini 2.5 Flash"))
            gemini = gem_result.scalar_one_or_none()
            if gemini:
                gemini.organization_id = org.id
                await session.commit()
                print(f"Updated Gemini to belong to org {org.id}")
            else:
                print("Gemini provider not found in DB.")
        else:
            print("No Organization found.")

if __name__ == "__main__":
    asyncio.run(main())
