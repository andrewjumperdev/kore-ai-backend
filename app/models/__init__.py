"""SQLAlchemy models. Import side-effect registers everything on Base.metadata."""
from app.models.base import Base
from app.models.niche import Niche
from app.models.tenant import Tenant, TenantApiKey
from app.models.user import User
from app.models.lead import Lead
from app.models.contact import Contact, ContactActivity
from app.models.conversation import Conversation, Message
from app.models.event import Event
from app.models.memory import LongTermMemory, SemanticMemory
from app.models.billing import Subscription, Invoice
from app.models.escalation import Escalation
from app.models.agent_run import AgentRun

__all__ = [
    "Base",
    "Niche",
    "Tenant",
    "TenantApiKey",
    "User",
    "Lead",
    "Contact",
    "ContactActivity",
    "Conversation",
    "Message",
    "Event",
    "LongTermMemory",
    "SemanticMemory",
    "Subscription",
    "Invoice",
    "Escalation",
    "AgentRun",
]
