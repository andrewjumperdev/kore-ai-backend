"""Coach Agent (§04-01) — diagnosis. The single point where a client's system
is configured. Uses the niche's coach_questions to diagnose the business, then
produces the business profile, strategy, and the set of modules to enable.

CRITICAL RULE: never enables modules without completing the diagnosis.
"""
from __future__ import annotations

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.registry import register_agent
from app.core.enums import Module


class AgentCoach(BaseAgent):
    name = "coach"

    def role_instructions(self, ctx: AgentContext) -> str:
        questions = ctx.niche_config.get("coach_questions", [])
        return (
            "You onboard a new client by DIAGNOSING their business using the "
            f"niche's diagnostic questions: {questions}. From their answers, infer "
            "a complete, ready-to-use growth configuration for THIS niche. Be "
            "specific: concrete ICP, sharp value props, real objections + rebuttals. "
            "Then decide which system modules to enable for this client."
        )

    def output_contract(self) -> str:
        return (
            "Return JSON: {industry: string, "
            "icp: {description: string, pains: string[], triggers: string[]}, "
            "value_props: string[], "
            "objections: {objection: string, rebuttal: string}[], "
            "strategy: string, summary: string, "
            "diagnosis_complete: boolean, "
            f"enable_modules: string[] (subset of {[m.value for m in Module]})}}."
        )

    def shape_result(self, ctx: AgentContext, data: dict) -> AgentResult:
        """Traduce la salida del LLM, decidiendo si esto configura o solo responde.

        El Coach se invoca desde DOS lugares y hacen cosas muy distintas:

        * ``POST /onboarding/diagnose`` — manda ``answers`` con las respuestas al
          cuestionario del nicho. Esto SÍ configura al cliente.
        * El chat de ARIA en el dashboard — manda solo ``message``. Es una
          consulta: tiene que responder y NO tocar nada.

        La presencia de ``answers`` es la única señal que distingue los dos casos,
        y por eso es la que manda. No se delega en el ``diagnosis_complete`` del
        modelo por dos motivos opuestos y ambos reales: si dice ``false`` de más,
        deja al cliente trabado en el onboarding con cero módulos; si dice
        ``true`` de más —el default— convierte un "hola" del chat en un
        diagnóstico que PISA el perfil del negocio, los módulos habilitados y la
        fecha de diagnóstico. Ese segundo caso borraba justo lo que el cliente
        pagó en el setup fee.
        """
        is_diagnosis = bool(ctx.input.get("answers"))
        if not is_diagnosis:
            # Consulta: se responde y se sale sin efectos. `facts` va vacío a
            # propósito — el runner los persiste en memoria de largo plazo, y una
            # charla suelta no debería sedimentar como si fuera el diagnóstico.
            return AgentResult(
                agent=self.name,
                output=data,
                reply=data.get("summary") or data.get("reply"),
            )

        modules = data.get("enable_modules") or ctx.niche_config.get(
            "default_modules", [m.value for m in Module]
        )
        return AgentResult(
            agent=self.name,
            output=data,
            reply=data.get("summary"),
            facts={"business_profile": data},
            modules_to_enable=modules,
        )


register_agent(AgentCoach())
