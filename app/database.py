from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_url)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]


async def get_db() -> AsyncIOMotorDatabase:
    return get_database()


async def ensure_indexes() -> None:
    db = get_database()
    await db.users.create_index("username", unique=True)
    await db.users.create_index("domain", unique=True)
    await db.nodes.create_index("parent_id")
    await db.nodes.create_index("updated_by")
    await db.nodes.create_index([("name", "text"), ("content", "text")])
    await db.history.create_index("node_id")


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
