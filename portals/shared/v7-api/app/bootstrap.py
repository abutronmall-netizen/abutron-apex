from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Base, Customer, Role
from app.security import hash_password


async def bootstrap_admin() -> None:
    email = os.getenv("ABUTRON_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ABUTRON_BOOTSTRAP_ADMIN_PASSWORD", "")
    full_name = os.getenv("ABUTRON_BOOTSTRAP_ADMIN_NAME", "Abutron Administrator").strip()

    if not email or not password:
        raise SystemExit(
            "ABUTRON_BOOTSTRAP_ADMIN_EMAIL and ABUTRON_BOOTSTRAP_ADMIN_PASSWORD are required"
        )
    if len(password) < 12:
        raise SystemExit("Bootstrap admin password must contain at least 12 characters")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        existing = await db.scalar(select(Customer).where(Customer.email == email))
        if existing:
            existing.role = Role.ADMIN
            existing.is_active = True
            existing.full_name = full_name
            existing.password_hash = hash_password(password)
            await db.commit()
            print(f"Updated administrator: {email}")
            return

        admin = Customer(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role=Role.ADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        print(f"Created administrator: {email}")


if __name__ == "__main__":
    asyncio.run(bootstrap_admin())
