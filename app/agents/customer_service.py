"""Customer Service Agent (atención al cliente) — el "cerebro" del flujo FAUSTO.

Responde a los mensajes entrantes del cliente, califica (cargo + empresa + dolor),
propone horarios de demo/consultoría y prepara la reserva. Es un agente PURO: no
toca el calendario ni envía emails — solo decide y devuelve una intención de
reserva estructurada. La ejecución (Google Calendar + email + voz + WhatsApp) la
hace CustomerServiceService leyendo `output["booking"]`.

Niche-aware (P2/P8): el tono, el producto y los límites salen del nicho del cliente
y de su business_profile (diagnóstico del Coach). Nunca promete autonomía 100% (P7).
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent, EscalationIntent
from app.agents.registry import register_agent
from app.core.enums import EscalationReason


class AgentCustomerService(BaseAgent):
    name = "customer_service"

    def role_instructions(self, ctx: AgentContext) -> str:
        tone = ctx.niche_config.get("tone", "profesional, cálido y directo")
        return (
            "Sos el agente de atención al cliente y ventas. Tu objetivo es responder "
            "de forma resolutiva y, cuando haya interés, AGENDAR una demo/consultoría "
            f"corta (20-30 min) con la persona. Tono: {tone}. "
            "IMPORTANTE: el usuario puede haber enviado VARIOS mensajes combinados en "
            "un solo texto — leé TODO y respondé a todos los puntos en UNA sola "
            "respuesta coherente. Usá su nombre si lo tenés. "
            "FLUJO: 1) responder/generar interés, 2) calificar (cargo + tamaño de "
            "empresa + dolor actual), 3) ofrecer demo y proponer 2-3 horarios REALES "
            "tomados del bloque de DISPONIBILIDAD que se te entrega, 4) al confirmar, "
            "pedir nombre completo + email + empresa y devolver la reserva. "
            "Nunca propongas horarios fuera de la disponibilidad ni en días cerrados."
        )

    def output_contract(self) -> str:
        return (
            "Devolvé JSON: {"
            "reply: string (el texto a enviar al cliente), "
            "intent: 'engage'|'qualify'|'propose'|'book'|'handoff', "
            "qualification: {role: string, company_size: string, pain: string} | null, "
            "booking: {"
            "  action: 'none'|'propose'|'confirm', "
            "  proposed_slots: string[] (ISO 8601, vacío si no aplica), "
            "  selected_slot: string|null (ISO 8601 cuando action='confirm'), "
            "  attendee_name: string|null, attendee_email: string|null, "
            "  attendee_company: string|null, summary: string|null "
            "}, "
            "needs_human: boolean (true si pide algo fuera de tu alcance)}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        booking = data.get("booking") or {}
        escalations = []
        if data.get("needs_human"):
            escalations.append(
                EscalationIntent(
                    reason=EscalationReason.CLOSE_READY,
                    title="Atención al cliente: requiere intervención humana",
                    executive_summary=str(data.get("reply", ""))[:500],
                    payload={"intent": data.get("intent"), "booking": booking},
                )
            )
        return AgentResult(
            agent=self.name,
            output=data,
            reply=data.get("reply"),
            facts={"last_intent": {"value": data.get("intent")}},
            escalations=escalations,
        )


register_agent(AgentCustomerService())
