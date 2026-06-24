from fastapi import APIRouter

from app.api.v1 import (
    agents,
    billing,
    customer_service,
    escalations,
    events,
    integrations,
    leads,
    metrics,
    niches,
    tenants,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(niches.router, prefix="/niches", tags=["niches"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(
    customer_service.router, prefix="/customer-service", tags=["customer-service"]
)
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(escalations.router, prefix="/escalations", tags=["escalations"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
