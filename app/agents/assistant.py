"""ARIA — el asistente del dashboard.

Responde dudas del dueño de la cuenta sobre su propio sistema: qué hace un
módulo, qué significa una métrica, por qué un lead quedó frío, qué conviene
revisar. Habla con el CLIENTE de KORE, no con los leads de ese cliente.

**Por qué es un agente aparte y no el Coach.** Antes el chat del dashboard corría
el Coach, y el Coach configura: devolvía módulos y perfil, y el runner los
escribía en el tenant. Un "hola" alcanzaba para reemplazar el diagnóstico
completo por el texto de un saludo. La separación no es cosmética — este agente
es *estructuralmente incapaz* de configurar nada, porque su ``shape_result``
nunca devuelve ``modules_to_enable`` ni ``facts``, que son las dos únicas
puertas por las que el runner escribe en el tenant.

Reconfigurar es un acto explícito y tiene su propio camino: el formulario de
diagnóstico (``POST /onboarding/diagnose``) y el botón de rehacerlo.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.registry import register_agent


class AssistantAgent(BaseAgent):
    name = "assistant"

    def role_instructions(self, ctx: AgentContext) -> str:
        modules = ", ".join(ctx.input.get("enabled_modules") or []) or "ninguno todavía"
        return (
            "Sos ARIA, la asistente del panel de KORE. Hablás con el DUEÑO de la "
            "cuenta sobre su propio sistema: le explicás qué hace cada módulo, qué "
            "significan sus métricas y qué le conviene revisar. Respondé en "
            "español rioplatense, en 2 o 3 frases, concreto y sin vender.\n"
            f"Módulos activos de este cliente: {modules}.\n"
            "Usás el perfil del negocio y la conversación previa como contexto. "
            "NO configurás nada: si te piden cambiar el rubro o rehacer el "
            "diagnóstico, explicá que se hace desde Cuenta → Rehacer mi "
            "diagnóstico. Si no sabés algo del sistema, decilo; no lo inventes."
        )

    def output_contract(self) -> str:
        return 'Return JSON: {reply: string}.'

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        # Solo `reply`. Sin `modules_to_enable` ni `facts`: son las dos puertas
        # por las que el runner escribiría en el tenant, y este agente no las usa.
        return AgentResult(
            agent=self.name,
            output=data,
            reply=data.get("reply") or data.get("summary") or "",
        )


register_agent(AssistantAgent())
