"""Create the first teacher account without enabling public teacher signup.

Usage inside the backend container:
python -m app.create_teacher --student-id T00001 --phone 13800000001 --password 'change-me' --name 'Teacher'
"""
import argparse
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionFactory, init_db
from app.core.security import hash_password
from app.models.user import User


async def create_teacher(args):
    await init_db()
    async with AsyncSessionFactory() as db:
        existing = await db.scalar(select(User).where((User.student_id == args.student_id) | (User.phone == args.phone)))
        if existing:
            raise SystemExit("A user with this student ID or phone already exists")
        db.add(User(
            student_id=args.student_id,
            phone=args.phone,
            password_hash=hash_password(args.password),
            display_name=args.name or args.student_id,
            role="teacher",
        ))
        await db.commit()
    print(f"Created teacher account {args.student_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--phone", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="")
    asyncio.run(create_teacher(parser.parse_args()))
