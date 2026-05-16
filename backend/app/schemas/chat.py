from pydantic import BaseModel, Field
from typing import Optional


class ChatSendRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    course_id: Optional[str] = None
    chapter_index: Optional[int] = None


class ChatResponse(BaseModel):
    message_id: str
    conversation_id: str
    response: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    course_id: Optional[str] = None
    chapter_index: Optional[int] = None
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    context_source: Optional[str] = None
    created_at: str
