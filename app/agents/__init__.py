from app.agents.base import AgentResult, BaseAgent, EscalationIntent, OutboundMessage
from app.agents.context import AgentContext
from app.agents.registry import AGENT_REGISTRY, get_agent, register_agent

# Import implementations so they self-register on the registry. Order mirrors
# the §04 chain: Coach → SDR → Qualification → Follow-up → Proposal → Onboarding
# plus the always-on Orchestrator and the Content agent.
from app.agents.coach import AgentCoach
from app.agents.sdr import SDRAgent
from app.agents.qualification import QualificationAgent
from app.agents.followup import FollowUpAgent
from app.agents.proposal import ProposalAgent
from app.agents.onboarding import OnboardingAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.content import ContentAgent
from app.agents.customer_service import AgentCustomerService
from app.agents.icebreaker import IcebreakerAgent

__all__ = [
    "AgentResult",
    "BaseAgent",
    "EscalationIntent",
    "OutboundMessage",
    "AgentContext",
    "AGENT_REGISTRY",
    "get_agent",
    "register_agent",
    "AgentCoach",
    "SDRAgent",
    "QualificationAgent",
    "FollowUpAgent",
    "ProposalAgent",
    "OnboardingAgent",
    "OrchestratorAgent",
    "ContentAgent",
    "AgentCustomerService",
    "IcebreakerAgent",
]
