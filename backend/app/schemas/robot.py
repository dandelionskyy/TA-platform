from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RobotStatusResponse(BaseModel):
    robot_name: str
    status: str
    battery_pct: int
    position_x: Optional[float]
    position_y: Optional[float]
    position_label: Optional[str]
    last_seen_at: Optional[str]
    total_questions_today: int = 0


class RobotQuestionResponse(BaseModel):
    id: str
    student_id: Optional[str]
    student_name: Optional[str]
    question_text: str
    response_text: Optional[str]
    created_at: str
