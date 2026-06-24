# KORE IA — El Sistema Operativo de Crecimiento

Infraestructura comercial automatizada con IA. Vende **modelos de negocio llave
en mano, replicables por nicho**, a clientes B2B: un sistema completo de
adquisición, seguimiento y conversión operado por agentes IA. No es una agencia
ni una herramienta — el cliente recibe un sistema funcionando.

Este backend implementa la arquitectura de tres capas, la cadena de agentes
(§04), las reglas del orquestador (§05), las métricas (§08) y los principios de
comportamiento P1–P8 (§10) como **restricciones forzables**, no sugerencias.

## Stack

FastAPI · PostgreSQL + pgvector · Redis · Dramatiq · SQLAlchemy 2.0 async ·
Anthropic Claude (wrapper propio, sin LangChain) · Stripe (setup + MRR) · Docker.

## Arquitectura de tres capas

| Capa | Nombre | Implementación |
|------|--------|----------------|
| 01 | Captura conversacional | [integrations/plaud.py](app/integrations/plaud.py) (transcripción+resumen+action items → CRM), [whatsapp](app/integrations/whatsapp.py)/[email](app/integrations/email.py), webhooks |
| 02 | Clasificación y seguimiento | [SDR](app/agents/sdr.py) + [Qualification](app/agents/qualification.py) (🔴🟡🟢) + [Follow-up](app/agents/followup.py) |
| 03 | Conversión y contenido | [Coach](app/agents/coach.py) + [Proposal](app/agents/proposal.py) + [Content](app/agents/content.py) |

## El modelo replicable (Andrew construye 1 vez por nicho)

La entidad de primer nivel es el **Nicho** ([models/niche.py](app/models/niche.py)):
una plantilla con prompts, señales de calificación, secuencias de follow-up,
plantillas de propuesta/contenido y límites de prompt (P8). Cada cliente
([Tenant](app/models/tenant.py)) es una **instancia** de un nicho (`niche_id`) y
hereda su configuración calibrada. Nichos de lanzamiento sembrados en
[scripts/seed_niches.py](scripts/seed_niches.py) (Plaud AR, Constructoras,
Abogados, Real Estate, Educación).

## Cadena de agentes (§04)

```
Coach (diagnóstico → habilita módulos)
  └─ lead.created → SDR (intake + temperatura inicial, SIN saliente · P1)
       └─ qualification.needed → Qualification (🔴/🟡/🟢; si no puede, 1 pregunta o escala)
            └─ lead.qualified ─┬─ 🟢 hot  → Proposal (prepara + escala a humano · P3/P6)
                               └─ 🟡/🔴   → Follow-up (secuencia del nicho)
  price_signal → Proposal ;  deal.closed → Onboarding ;  Orchestrator (siempre activo)
```

Agentes en [app/agents/](app/agents/); el [AgentRunner](app/agents/runner.py) es
el único lugar que decide qué puede ocurrir. **No hay agente "Setter"** — el
cierre es humano vía escalación.

## P1–P8 como restricciones forzables (§10)

[app/orchestrator/policy.py](app/orchestrator/policy.py) — el runner las aplica y
una violación lanza `PolicyViolation` (HTTP 422):

- **P1** primero calificar, luego comunicar → saliente bloqueada si `temperature == unset`.
- **P2/P8** nicho obligatorio → ningún agente corre sin nicho; output genérico rechazado.
- **P3** el humano decide lo crítico → Proposal/Content **preparan y escalan**, nunca auto-envían/publican ([escalation.py](app/orchestrator/escalation.py)).
- **P6** sin diagnóstico no hay propuesta → guard sobre `diagnosis_completed_at`.
- **P5** la BD es la memoria → [memory/](app/memory/) (Redis + Postgres + pgvector).
- **P7** nunca prometer autonomía 100% → inyectado en el system prompt.

## Reglas del orquestador (§05) y métricas (§08)

- [orchestrator/rules.py](app/orchestrator/rules.py): pipeline sin movimiento >7d → alerta; mismo lead >4x sin avance → pausa 30d + flag. Follow-up: máx. 2 intentos → pausa 30d ([followup_tasks.py](app/tasks/followup_tasks.py)).
- [orchestrator/metrics.py](app/orchestrator/metrics.py): leads/semana, % clasificación automática, distribución de temperatura, % frío, MRR, churn, leads Plaud — con thresholds/alertas.
- Barrido diario + facturación MRR mensual programados en [app/worker.py](app/worker.py).

## Billing (§08): setup + MRR

[billing/engine.py](app/billing/engine.py): suscripción con `setup_fee_cents` +
`mrr_cents`. `mark_setup_paid` → emite `deal.closed` → dispara Onboarding. Churn y
MRR agregados en métricas. (Se eliminó el cobro por contactos/mes.)

## Endpoints

`/niches` · `/tenants` · `/leads` · `/agents/run` · `/events` · `/escalations` ·
`/metrics` · `/billing/{subscription,setup/paid,summary}` ·
`/webhooks/{channel}/{tenant_id}` · `/webhooks/plaud/{tenant_id}`.

## Quickstart

```bash
cp .env.example .env                      # ANTHROPIC_API_KEY opcional (hay stub offline)
docker compose up -d db redis
pip install -e ".[dev]"

python -m scripts.init_db                 # extensión pgvector + tablas
python -m scripts.seed_niches             # nichos de lanzamiento (§03)
python -m scripts.demo_flow               # cadena completa inline (offline-safe)

uvicorn app.main:app --reload             # API en /docs
dramatiq app.worker                       # workers (otra terminal)
```

### Ejemplo de alta de cliente

```bash
# 1) Crear cliente como instancia de un nicho (P2)
curl -sX POST localhost:8000/api/v1/tenants -H 'content-type: application/json' \
  -d '{"name":"BB Desarrollos","slug":"bb","niche_slug":"constructoras"}'
KEY=kore_xxx   # de la respuesta

# 2) Coach diagnostica y habilita módulos
curl -sX POST localhost:8000/api/v1/agents/run -H "authorization: Bearer $KEY" \
  -H 'content-type: application/json' \
  -d '{"agent":"coach","payload":{"message":"Desarrollo residencial premium..."}}'

# 3) Plan: setup + MRR  → marcar setup pagado (deal → Onboarding)
curl -sX POST localhost:8000/api/v1/billing/subscription -H "authorization: Bearer $KEY" \
  -H 'content-type: application/json' \
  -d '{"plan":"constructoras-growth","setup_fee_cents":150000,"mrr_cents":49900}'
curl -sX POST localhost:8000/api/v1/billing/setup/paid -H "authorization: Bearer $KEY"

# 4) Lead → SDR → Qualification → (Proposal|Follow-up) automático
curl -sX POST localhost:8000/api/v1/leads -H "authorization: Bearer $KEY" \
  -H 'content-type: application/json' \
  -d '{"full_name":"Inversor","phone":"+5491133334444","channel":"whatsapp","source":"instagram"}'

# 5) Cola humana + métricas
curl -s localhost:8000/api/v1/escalations -H "authorization: Bearer $KEY"
curl -s localhost:8000/api/v1/metrics      -H "authorization: Bearer $KEY"
```

## Deployment

Una imagen, tres roles (`api`/`worker`/`scheduler`) vía
[docker/entrypoint.sh](docker/entrypoint.sh); [docker-compose.yml](docker-compose.yml)
levanta pgvector + Redis + API + workers + scheduler. Migraciones Alembic
(`entrypoint migrate`). Pendiente de endurecer (marcado en código): verificación
de firma de webhooks (canales + Stripe) y RLS de Postgres como segunda capa de
aislamiento.
