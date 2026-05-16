"""Seed demo accounts: teacher, TA, and a test student."""
from app.core.security import hash_password
from app.models.user import User


DEMO_USERS = [
    {
        "student_id": "T00001",
        "phone": "13800000001",
        "password": "123456",
        "display_name": "张老师",
        "role": "teacher",
    },
    {
        "student_id": "TA0001",
        "phone": "13800000002",
        "password": "123456",
        "display_name": "李助教",
        "role": "ta",
    },
    {
        "student_id": "20240001",
        "phone": "13800000003",
        "password": "123456",
        "display_name": "王同学",
        "role": "student",
    },
]


async def seed_demo_accounts(db):
    """Create demo accounts if they don't exist. Call during startup."""
    from sqlalchemy import select

    for u in DEMO_USERS:
        result = await db.execute(select(User).where(User.student_id == u["student_id"]))
        if result.scalar_one_or_none():
            continue  # already exists
        user = User(
            student_id=u["student_id"],
            phone=u["phone"],
            password_hash=hash_password(u["password"]),
            display_name=u["display_name"],
            role=u["role"],
        )
        db.add(user)
        print(f"[SEED] Created {u['role']} account: {u['student_id']} / {u['password']}")

    await db.flush()
