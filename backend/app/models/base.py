from app.models.user import User
from app.models.course import Course, Enrollment, CourseStaff, CourseChapter, CourseMaterial
from app.models.conversation import Conversation, Message
from app.models.robot import RobotStatus, RobotQuestion
from app.models.usage_log import UsageLog, AuditLog, RefreshToken
from app.models.file_asset import FileAsset
from app.models.academic import Assignment, Submission, AttendanceSession, AttendanceRecord, Announcement
from app.models.messaging import MessagePermission, DirectThread, DirectMessage
from app.models.bridge import (
    BridgeModulePack, BridgeMaterial, BridgeChunk, BridgeStaffSolution,
    BridgeGlossaryTerm, BridgeTutorSession, BridgeLearningEvent, BridgeDailyAggregate,
    BridgeConcept, BridgeTemplate, BridgeRegressionPrompt,
)

__all__ = [
    "User",
    "Course",
    "Enrollment",
    "CourseStaff",
    "CourseChapter",
    "CourseMaterial",
    "Conversation",
    "Message",
    "RobotStatus",
    "RobotQuestion",
    "UsageLog",
    "AuditLog",
    "RefreshToken",
    "FileAsset",
    "Assignment",
    "Submission",
    "AttendanceSession",
    "AttendanceRecord",
    "Announcement",
    "MessagePermission",
    "DirectThread",
    "DirectMessage",
    "BridgeModulePack",
    "BridgeMaterial",
    "BridgeChunk",
    "BridgeStaffSolution",
    "BridgeGlossaryTerm",
    "BridgeTutorSession",
    "BridgeLearningEvent",
    "BridgeDailyAggregate",
    "BridgeConcept",
    "BridgeTemplate",
    "BridgeRegressionPrompt",
]
