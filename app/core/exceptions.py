"""Domain exceptions mapped to HTTP responses by a single handler."""
from __future__ import annotations


class KoreError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str | None = None, *, details: dict | None = None):
        self.message = message or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(KoreError):
    status_code = 404
    code = "not_found"


class TenantContextMissing(KoreError):
    status_code = 400
    code = "tenant_context_missing"


class AuthenticationError(KoreError):
    status_code = 401
    code = "unauthenticated"


class PermissionDenied(KoreError):
    status_code = 403
    code = "permission_denied"


class QuotaExceeded(KoreError):
    """Raised by the billing engine when a hard usage cap is hit."""

    status_code = 402
    code = "quota_exceeded"


class IntegrationError(KoreError):
    status_code = 502
    code = "integration_error"


class AgentExecutionError(KoreError):
    status_code = 500
    code = "agent_execution_error"


class PolicyViolation(KoreError):
    """Raised when an agent action breaks an invariant behavioral principle
    (P1–P8). These are hard constraints enforced by the orchestrator, never
    suggestions."""

    status_code = 422
    code = "policy_violation"
