import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import io
from collections.abc import AsyncGenerator

import pytest


@pytest.fixture
def image_bytes() -> bytes:
    try:
        from PIL import Image
    except ModuleNotFoundError:
        pytest.skip("Pillow not installed")
    image = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
async def client() -> AsyncGenerator[object, None]:
    try:
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    except ModuleNotFoundError as exc:
        pytest.skip(f"Missing test dependency: {exc.name}")

    from app.db.base import Base
    from app.db.database import get_db
    from app.main import app

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()
