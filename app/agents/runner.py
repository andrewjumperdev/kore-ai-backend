"""AgentRunner — the orchestration seam between agents and the platform.

It is the ONLY place that decides what an agent's output is allowed to do. It
enforces the behavioral policy (P1–P8) via app.orchestrator.policy, applies
temperature changes, enables modules after diagnosis, routes human-review output
to escalations instead of sending, and emits the chain's events. Agents stay
pure.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentResult
from app.agents.context import AgentContext
from app.agents.registry import get_agent
from app.core.enums import LifecycleStage, Temperature
from app.core.logging import get_logger
from app.events.bus import event_bus
from app.events.types import EventName
from app.integrations.registry import get_channel
from app.memory.manager import MemoryManager
from app.models.agent_run import AgentRun
from app.models.contact import Contact
from app.models.tenant import Tenant
from app.orchestrator import policy
from app.orchestrator.escalation import EscalationService
from app.services.contact_service import ContactService

log = get_logger("runner")


class AgentRunner:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.contacts = ContactService(session, tenant_id)
        self.escalations = EscalationService(session, tenant_id)

    async def run(self, agent_name: str, payload: dict) -> AgentRun:
        agent = get_agent(agent_name)
        tenant = await self.session.get(Tenant, self.tenant_id)
        if tenant is None:
            raise policy.PolicyViolation("tenant inexistente")

        contact = await self._load_contact(payload)

        # ── P1/P2/P6 + module guards BEFORE running ──────────────────
        policy.check_pre_run(agent_name, tenant, contact)

        niche_config = await self._niche_config(tenant)
        conversation = None
        if contact is not None:
            conversation = await self.contacts.get_or_create_conversation(
                contact.id, payload.get("channel", "whatsapp")
            )

        ctx = AgentContext(
            tenant_id=self.tenant_id,
            session=self.session,
            memory=MemoryManager(self.session, self.tenant_id),
            business_profile=tenant.business_profile,
            niche_slug=await self._niche_slug(tenant),
            niche_config=niche_config,
            contact_id=contact.id if contact else None,
            conversation_id=conversation.id if conversation else None,
            current_temperature=contact.temperature if contact else Temperature.UNSET,
            input=payload,
        )

        started = time.perf_counter()
        run = AgentRun(
            tenant_id=self.tenant_id,
            agent=agent_name,
            contact_id=contact.id if contact else None,
            conversation_id=conversation.id if conversation else None,
            input=payload,
        )
        try:
            result = await agent.run(ctx)
            policy.assert_niche_aware(agent_name, result.output, tenant)
        except Exception as exc:
            run.status = "error"
            run.error = str(exc)
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            self.session.add(run)
            await self.session.flush()
            log.error("agent.failed", agent=agent_name, error=str(exc))
            raise

        run.status = "ok"
        run.output = result.to_dict()
        run.input_tokens = result.input_tokens
        run.output_tokens = result.output_tokens
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        self.session.add(run)
        await self.session.flush()

        await self._apply_side_effects(ctx, agent_name, result, tenant, contact)
        return run

    # ── helpers ──────────────────────────────────────────────────────

    async def _load_contact(self, payload: dict) -> Contact | None:
        cid = payload.get("contact_id")
        return await self.session.get(Contact, UUID(cid)) if cid else None

    async def _niche_config(self, tenant: Tenant) -> dict:
        if tenant.niche_id is None:
            return {}
        from app.services.niche_service import NicheService

        niche = await NicheService(self.session).get(tenant.niche_id)
        return niche.config if niche else {}

    async def _niche_slug(self, tenant: Tenant) -> str | None:
        if tenant.niche_id is None:
            return None
        from app.services.niche_service import NicheService

        niche = await NicheService(self.session).get(tenant.niche_id)
        return niche.slug if niche else None

    async def _apply_side_effects(
        self,
        ctx: AgentContext,
        agent_name: str,
        result: AgentResult,
        tenant: Tenant,
        contact: Contact | None,
    ) -> None:
        # 1) Coach completed diagnosis → enable modules + mark diagnosis done.
        if agent_name == "coach" and result.modules_to_enable:
            tenant.business_profile = result.facts.get("business_profile", tenant.business_profile)
            tenant.enabled_modules = result.modules_to_enable
            tenant.diagnosis_completed_at = datetime.now(timezone.utc)
            await event_bus.emit(
                self.session,
                EventName.DIAGNOSIS_COMPLETED,
                source="coach",
                subject_type="tenant",
                subject_id=str(tenant.id),
                payload={"enabled_modules": result.modules_to_enable},
            )

        # 2) Temperature classification (sdr initial / qualification definitive).
        if result.temperature in (Temperature.COLD, Temperature.WARM, Temperature.HOT) and contact:
            previous = contact.temperature
            contact.temperature = result.temperature
            contact.last_activity_at = datetime.now(timezone.utc)
            if agent_name == "qualification":
                contact.lifecycle_stage = LifecycleStage.QUALIFIED
            await event_bus.emit(
                self.session,
                EventName.TEMPERATURE_CHANGED,
                source=agent_name,
                subject_type="contact",
                subject_id=str(contact.id),
                payload={"from": previous, "to": result.temperature, "contact_id": str(contact.id)},
            )
            if agent_name == "qualification":
                await event_bus.emit(
                    self.session,
                    EventName.LEAD_QUALIFIED,
                    source=agent_name,
                    subject_type="contact",
                    subject_id=str(contact.id),
                    payload={"contact_id": str(contact.id), "temperature": result.temperature},
                )

        # 3) SDR finished intake → request qualification (chain step).
        if agent_name == "sdr" and result.needs_qualification and contact:
            await event_bus.emit(
                self.session,
                EventName.QUALIFICATION_NEEDED,
                source="sdr",
                subject_type="contact",
                subject_id=str(contact.id),
                payload={
                    "contact_id": str(contact.id),
                    "channel": ctx.input.get("channel", "whatsapp"),
                    "to": ctx.input.get("to"),
                },
            )

        # 4) Persist learned facts + remember the agent turn.
        for key, value in result.facts.items():
            await ctx.memory.long.remember(
                "contact",
                str(ctx.contact_id) if ctx.contact_id else None,
                key,
                value if isinstance(value, dict) else {"value": value},
            )
        if result.reply and ctx.conversation_id:
            await ctx.memory.short.append_turn(ctx.conversation_id, "assistant", result.reply)
            await ctx.memory.semantic.index(
                "conversation", result.reply, subject_id=str(ctx.contact_id)
            )

        # 5) Outbound messages — gated by P1; human-review agents never send.
        if not policy.requires_human_review(agent_name):
            for out in result.messages:
                policy.check_outbound_allowed(agent_name, contact)
                channel = get_channel(out.channel)
                send_result = await channel.send(to=out.to or "", body=out.body)
                if ctx.conversation_id:
                    await self.contacts.record_message(
                        conversation_id=ctx.conversation_id,
                        direction="outbound",
                        body=out.body,
                        role="assistant",
                        author_agent=agent_name,
                        meta={"provider": send_result.provider, "status": send_result.status},
                    )
                await event_bus.emit(
                    self.session,
                    EventName.MESSAGE_SENT,
                    source=agent_name,
                    subject_type="contact",
                    subject_id=str(ctx.contact_id) if ctx.contact_id else None,
                    payload={"channel": out.channel, "status": send_result.status},
                )

        # 6) Human escalations (P3) — proposals, content, price signals, etc.
        for esc in result.escalations:
            await self.escalations.raise_escalation(
                reason=esc.reason,
                title=esc.title,
                executive_summary=esc.executive_summary,
                source_agent=agent_name,
                contact_id=ctx.contact_id,
                payload=esc.payload,
            )

        # 7) Umbrella event.
        await event_bus.emit(
            self.session,
            EventName.AGENT_RESPONDED,
            source=agent_name,
            subject_type="contact",
            subject_id=str(ctx.contact_id) if ctx.contact_id else None,
            payload={
                "agent": agent_name,
                "contact_id": str(ctx.contact_id) if ctx.contact_id else None,
                "temperature": result.temperature,
                "escalations": len(result.escalations),
            },
        )
