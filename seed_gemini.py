import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from core.config import settings
from models.accounts import Organization, User
from models.dashboard import AIProvider, APIKey, AuditLog

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def main():
    async with async_session() as session:
        result = await session.execute(select(AIProvider).where(AIProvider.name == "Gemini 2.5 Flash"))
        exists = result.scalar_one_or_none()
        if not exists:
            gemini = AIProvider(
                organization_id=1,
                name="Gemini 2.5 Flash",
                provider_type="gemini",
                api_base_url="https://generativelanguage.googleapis.com",
                api_key="your_gemini_api_key_here",
                model_name="gemini-2.5-flash",
                is_active=True,
                is_system=True
            )
            session.add(gemini)
            await session.commit()
            print("Successfully added Gemini 2.5 Flash")
        else:
            print("Gemini already exists")

if __name__ == "__main__":
    asyncio.run(main())
