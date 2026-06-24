"""DEPRECATED — contact metering removed in the KORE IA spec alignment.

KORE IA monetizes setup fee + MRR (§08), not contacts/month. Engagement volume
is now a *business metric* surfaced by app.orchestrator.metrics, not a billing
input. Kept as a thin shim only so stale imports fail loudly with guidance.
"""
from __future__ import annotations


class UsageTracker:  # pragma: no cover - intentionally inert
    def __init__(self, *_, **__):
        raise NotImplementedError(
            "Contact-based billing was removed. Use app.billing.engine.BillingEngine "
            "(setup + MRR) and app.orchestrator.metrics for engagement metrics."
        )
