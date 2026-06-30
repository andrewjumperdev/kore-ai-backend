"""Icebreaker Agent — genera el cold email B2B personalizado (port del 'Agente
creador de Email IceBreaker' del flujo n8n).

Recibe el texto + colores del sitio del prospecto (vía ctx.input) y devuelve
{subject, html}. La persona (remitente, empresa, CTA) sale de la config.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.registry import register_agent
from app.core.config import settings

_SIGNATURE = """<tr><td style="padding:20px; border-top:1px solid #e0e0e0;">
<table width="100%"><tr>
<td width="80" valign="top"><img src="https://i.ibb.co/sp0pQ4VM/image.png" alt="{sender}" width="60" style="border-radius:50%; display:block;"></td>
<td valign="top" style="padding-left:10px; font-size:14px; line-height:1.4; color:#555;">
<strong>{sender}</strong><br>CEO de {company}<br></td></tr></table></td></tr>"""


class IcebreakerAgent(BaseAgent):
    name = "icebreaker"

    def role_instructions(self, ctx: AgentContext) -> str:
        # Persona por-tenant (viene del dashboard vía payload); fallback al .env.
        persona = ctx.input.get("persona") or {}
        sender = persona.get("sender_name") or settings.icebreaker_sender_name
        company = persona.get("company") or settings.icebreaker_company
        cta = persona.get("cta_url") or settings.icebreaker_cta_url
        sig = _SIGNATURE.format(sender=sender, company=company)
        return (
            "Actúas como experto en ventas B2B especializado en cold emailing para "
            "una empresa que ofrece soluciones de IA y automatización de procesos. "
            "Recibís el contenido y los colores de la web del prospecto (en el bloque "
            "TRIGGER/INBOUND: campos site_text y colors) para personalizar al máximo.\n\n"
            "Generá un ICEBREAKER que abra un correo en frío: capta la atención desde "
            "la primera línea, genera curiosidad/identificación y provoca respuesta. "
            "NO suene genérico ni robótico; NO digas que vendés ni que representás una "
            "empresa al inicio. Breve (5-7 frases). Habla en primera persona, tuteá. "
            "Mencioná que son especialistas en implementar IA en negocios como el suyo. "
            f"Terminá con un CTA en formato BOTÓN que enlace a {cta} (responder al email). "
            "Usá colores minimalistas que generen confianza (podés inspirarte en los "
            "colores de su web). Incluí al final: 'Un saludo, "
            f"{sender}, CEO de {company}'.\n\n"
            f"Incluí SIEMPRE esta firma HTML al final del cuerpo: {sig}"
        )

    def output_contract(self) -> str:
        return (
            "Devolvé JSON: {subject: string (asunto en texto plano, sin emojis raros), "
            "html: string (email completo en HTML bien estructurado, bonito, con "
            "encabezados/negritas, el botón de CTA y la firma)}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        # Compat con el n8n: aceptamos ASUNTO/HTML o subject/html.
        subject = data.get("subject") or data.get("ASUNTO") or ""
        html = data.get("html") or data.get("HTML") or ""
        return AgentResult(agent=self.name, output={"subject": subject, "html": html, "_niche": data.get("_niche")})


register_agent(IcebreakerAgent())
