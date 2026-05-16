from pydantic import BaseModel
from typing import Optional


class StudentUsageResponse(BaseModel):
    user_id: str
    student_id: str
    display_name: str
    total_chat_messages: int
    total_conversations: int
    last_active_at: Optional[str]
    total_login_count: int
    total_robot_questions: int
