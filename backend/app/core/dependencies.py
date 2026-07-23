from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def require_role(*roles: str):
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return role_checker


async def require_teacher_course_access(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify that a teacher owns or a TA is assigned to a course."""
    from app.models.course import Course, CourseStaff
    from sqlalchemy import exists

    if current_user.role == "teacher":
        owns = await db.scalar(select(exists().where(
            Course.id == course_id, Course.teacher_id == current_user.id
        )))
        if owns:
            return current_user
    if current_user.role == "ta":
        assigned = await db.scalar(select(exists().where(
            CourseStaff.course_id == course_id, CourseStaff.user_id == current_user.id,
            CourseStaff.role == "ta"
        )))
        if assigned:
            return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Course access denied")


# Convenience dependencies
RequireTeacher = require_role("teacher")
RequireTA = require_role("ta")
RequireStudent = require_role("student")
RequireTeacherOrTA = require_role("teacher", "ta")
