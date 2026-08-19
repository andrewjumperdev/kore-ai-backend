"""Stripe wrapper for setup (one-time) + subscription (recurring). Kept thin and
optional — every call no-ops when no API key is configured. The engine owns the
domain state; Stripe is the money rail and the source of payment webhooks."""
from __future__ import annotations

import stripe

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConfigurationError, IntegrationError
from app.core.logging import get_logger

log = get_logger("stripe")
stripe.api_key = settings.stripe_api_key


class StripeClient:
    def is_configured(self) -> bool:
        return bool(settings.stripe_api_key)

    async def ensure_customer(self, *, email: str, name: str) -> str | None:
        if not self.is_configured():
            return None
        try:
            customer = stripe.Customer.create(email=email, name=name)
            return customer["id"]
        except stripe.StripeError as exc:  # pragma: no cover - network
            raise IntegrationError(
                "Stripe customer create failed", details={"error": str(exc)}
            ) from exc

    async def create_subscription(self, *, customer_id: str, price_id: str) -> str | None:
        if not self.is_configured():
            return None
        try:
            sub = stripe.Subscription.create(
                customer=customer_id, items=[{"price": price_id}]
            )
            return sub["id"]
        except stripe.StripeError as exc:  # pragma: no cover - network
            raise IntegrationError(
                "Stripe subscription failed", details={"error": str(exc)}
            ) from exc

    async def create_setup_invoice(self, *, customer_id: str, amount_cents: int) -> str | None:
        """One-time setup charge as a standalone invoice item + invoice."""
        if not self.is_configured():
            return None
        try:
            stripe.InvoiceItem.create(
                customer=customer_id, amount=amount_cents, currency="usd",
                description="KORE IA — setup",
            )
            invoice = stripe.Invoice.create(customer=customer_id, auto_advance=True)
            return invoice["id"]
        except stripe.StripeError as exc:  # pragma: no cover - network
            raise IntegrationError(
                "Stripe setup invoice failed", details={"error": str(exc)}
            ) from exc

    def verify_webhook(self, payload: bytes, signature: str) -> dict:
        """Valida la firma de Stripe sobre el cuerpo CRUDO y devuelve el evento.

        Fail-closed: sin secreto configurado no se acepta el evento, porque
        cualquiera podría postear un `invoice.paid` falso y activarse la cuenta.
        """
        if not settings.stripe_webhook_secret:
            raise ConfigurationError("STRIPE_WEBHOOK_SECRET no configurado")
        try:
            return stripe.Webhook.construct_event(
                payload, signature, settings.stripe_webhook_secret
            )
        except stripe.SignatureVerificationError as exc:
            log.warning("stripe.bad_signature")
            raise AuthenticationError(
                "Invalid Stripe signature", details={"error": str(exc)}
            ) from exc
        except ValueError as exc:
            raise IntegrationError(
                "Malformed Stripe payload", details={"error": str(exc)}
            ) from exc


stripe_client = StripeClient()
