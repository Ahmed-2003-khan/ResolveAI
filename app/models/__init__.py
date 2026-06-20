# Import all models so Alembic's autogenerate picks them up
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.base import Base  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.eval_run import EvalResult, EvalRun  # noqa: F401
from app.models.kb_chunk import KBChunk  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.semantic_cache import SemanticCache  # noqa: F401
from app.models.user_profile import UserProfile  # noqa: F401

__all__ = [
    "Base",
    "Conversation",
    "Message",
    "KBChunk",
    "UserProfile",
    "AuditLog",
    "EvalRun",
    "EvalResult",
    "SemanticCache",
]
