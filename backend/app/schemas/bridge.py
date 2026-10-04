"""Public web tutor contract. Never accept a client-supplied module on a tutor turn."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["en", "zh"]
GroundingStatus = Literal["GROUNDED", "INSUFFICIENT EVIDENCE"]
DialogueStage = Literal[
    "greeting", "diagnosis", "probing", "hinting", "struggle", "check", "explain", "celebrate"
]


class SessionCreate(BaseModel):
    module_id: str = Field(min_length=1, max_length=36)
    language: Language = "en"


class SourceReference(BaseModel):
    source_id: str
    document: str
    page: int | None = None
    reference: str


class SessionResponse(BaseModel):
    session_token: str
    module_id: str
    language: Language
    expires_at: datetime
    lock_status: bool
    stage: Literal["greeting"] = "greeting"
    avatar_state: Literal["encouraging"] = "encouraging"
    welcome: str
    grounding_status: Literal["INSUFFICIENT EVIDENCE"] = "INSUFFICIENT EVIDENCE"
    sources: list[SourceReference] = Field(default_factory=list)


class TutorRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    language: Language | None = None


class LearningState(BaseModel):
    concept_key: str | None = None
    scaffold_count: int = 0
    mastery: bool = False


class TutorResponse(BaseModel):
    response: str
    stage: DialogueStage
    avatar_state: Literal["questioning", "thinking", "encouraging", "explaining", "cautioning", "celebrating"]
    grounding_status: GroundingStatus
    sources: list[SourceReference] = Field(default_factory=list)
    language: Language
    practice: str | None = None
    lock_status: bool = False
    learning_state: LearningState = Field(default_factory=LearningState)
