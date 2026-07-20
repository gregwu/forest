"""Create the initial admin user. Usage: python scripts/seed_admin.py <username> <password> <domain>"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.auth import hash_password
from app.database import get_database


async def main():
    if len(sys.argv) != 4:
        print("Usage: python scripts/seed_admin.py <username> <password> <domain>")
        sys.exit(1)

    username, password, domain = sys.argv[1:4]
    db = get_database()

    existing = await db.users.find_one({"username": username})
    if existing:
        print(f"User '{username}' already exists.")
        return

    await db.users.insert_one(
        {"username": username, "password_hash": hash_password(password), "domain": domain, "is_admin": True}
    )
    print(f"Created admin user '{username}'.")


if __name__ == "__main__":
    asyncio.run(main())
