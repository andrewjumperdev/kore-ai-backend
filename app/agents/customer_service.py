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

# Defaults FAUSTO (el user los puede sobreescribir TODOS desde el dashboard).
CS_AGENT_DEFAULTS: dict[str, str] = {
    "agent_name": "Fausto",
    "company_name": "Fausto®",
    "company_tagline": "Inteligencia Artificial que vende por ti",
    "objective": "agendar una demo o consultoría gratuita de 20-30 minutos con un tomador de decisiones",
    "about": "Consultora experta en implementación de IA generativa, automatizaciones "
    "inteligentes, chatbots con memoria, análisis predictivo y optimización de procesos.",
    "proof_points": "+200 proyectos entregados en 2024-2025. Clientes: bancos, e-commerce, "
    "logística, clínicas, universidades, fábricas, retailers. Resultados promedio: -70% tareas "
    "repetitivas, +45% eficiencia operativa, +30% cierre de ventas con agentes IA.",
    "meeting_duration": "20-30 minutos",
    "availability": "Lunes a viernes de 09:00 a 22:00",
    "tone": "profesional, directo y con autoridad",
    "emojis": "🔥 ✅ 📅 🚀 💼",
    "language": "español neutro",
    "flow": "1) Presentarte y generar curiosidad. 2) Calificar: cargo + tamaño de empresa + "
    "dolor actual. 3) Ofrecer la demo/consultoría gratuita. 4) Mostrar 2-3 horarios reales de "
    "los próximos días (tomados del bloque DISPONIBILIDAD). 5) Preguntar la zona horaria del "
    "cliente. 6) Al acordar, confirmar nombre completo + cargo + empresa + email y agendar.",
    "rules": "Nunca agendes en slots ocupados ni días cerrados. Si el slot no está libre, ofrecé "
    "el siguiente disponible. Siempre confirmá nombre completo + cargo + empresa + email "
    "corporativo antes de agendar.",
}


def merged_agent_config(cfg: dict | None) -> dict:
    """Config efectiva: lo que cargó el user + defaults FAUSTO para lo que falte."""
    cfg = cfg or {}
    return {k: (cfg.get(k) or v) for k, v in CS_AGENT_DEFAULTS.items()}


class AgentCustomerService(BaseAgent):
    name = "customer_service"

    def role_instructions(self, ctx: AgentContext) -> str:
        c = merged_agent_config(ctx.input.get("agent_config"))
        return (
            f"Sos {c['agent_name']}, el agente de ventas/atención de {c['company_name']} "
            f"({c['company_tagline']}). {c['about']}\n"
            f"OBJETIVO: {c['objective']}.\n"
            f"SOBRE LA EMPRESA (usalo para generar autoridad): {c['proof_points']}\n"
            f"REUNIONES: duración {c['meeting_duration']}. Disponibilidad: {c['availability']}. "
            "Proponé SIEMPRE horarios reales del bloque DISPONIBILIDAD que se te entrega; "
            "nunca en días cerrados u ocupados. Preguntá la zona horaria del cliente.\n"
            f"ESTILO: tono {c['tone']}. Idioma: {c['language']}. Emojis estratégicos: "
            f"{c['emojis']}. Usá el nombre del contacto.\n"
            "IMPORTANTE: el usuario puede haber enviado VARIOS mensajes combinados en un solo "
            "texto — leé TODO y respondé a todos los puntos en UNA sola respuesta coherente.\n"
            f"FLUJO OBLIGATORIO: {c['flow']}\n"
            f"REGLAS CRÍTICAS: {c['rules']} Al confirmar, devolvé la reserva con "
            "action='confirm', selected_slot, attendee_name, attendee_email y attendee_company."
        )

    def output_contract(self) -> str:
        return (
            "Devolvé JSON: {"
            "reply: string (el texto a enviar al cliente), "
            "intent: 'engage'|'qualify'|'propose'|'book'|'handoff', "
            "temperature: 'hot'|'warm'|'cold'|'unset' (CLASIFICÁ SIEMPRE: hot=listo "
            "para agendar o alto interés; warm=interesado pero falta info; cold=solo "
            "curiosea; unset=todavía no hay señales), "
            "qualification: {name: string|null, role: string|null, company: string|null, "
            "company_size: string|null, pain: string|null, email: string|null} "
            "(capturá TODO dato que el cliente mencione, aunque sea parcial), "
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
        temp = data.get("temperature")
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
            # El runner persiste la temperatura en el contacto del CRM + emite evento.
            temperature=temp if temp in ("hot", "warm", "cold") else None,
            facts={"qualification": data.get("qualification") or {}},
            escalations=escalations,
        )


register_agent(AgentCustomerService())
