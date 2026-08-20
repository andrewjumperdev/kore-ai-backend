# 🚀 Deploy de KORE — Producción

Arquitectura: **Frontend en Vercel** + **Backend (API/worker/scheduler) + Postgres
+ Redis + Evolution en un VPS con Docker** detrás de Caddy (HTTPS automático).
Supabase ya está hosteado (auth).

Reemplazá en todos lados `tudominio.com` por tu dominio real.

---

## 0) Antes de empezar
- Un VPS Linux (Ubuntu 22.04+, **2–4 GB RAM**). Ej: Hetzner CX22, DigitalOcean.
- Tu dominio. Creá estos registros DNS:
  - `A  api.tudominio.com  → IP_DEL_VPS`   (backend)
  - El frontend usa el dominio de Vercel o `app.tudominio.com` (CNAME a Vercel).
- En el VPS, abrí puertos **80, 443** (y 22 para SSH).

### Generá los secretos primero
Con `KORE_ENV=production` la app **valida su configuración al arrancar y se
niega a levantar** si falta un secreto o quedó un default de desarrollo. Es
deliberado: preferimos un deploy que no arranca a uno que arranca inseguro.
Si el contenedor no levanta, `docker compose logs api` te dice exactamente cuál falta.

```bash
for k in KORE_SECRET_KEY KORE_PROVISIONING_SECRET KORE_ADMIN_API_KEY \
         KORE_CREDENTIALS_SECRET WEBHOOK_TOKEN POSTGRES_PASSWORD \
         EVOLUTION_DB_PASSWORD EVOLUTION_API_KEY; do
  echo "$k=$(openssl rand -hex 32)"
done
```

Guardá esa salida: `KORE_PROVISIONING_SECRET` va **igual en los dos lados**
(backend y Vercel).

---

## 1) Backend en el VPS

```bash
# instalar Docker
curl -fsSL https://get.docker.com | sh

# traer el código
git clone <TU_REPO> kore-ai-backend && cd kore-ai-backend

# configurar
cp .env.production.example .env
nano .env                      # pegá los secretos generados arriba + OPENAI_API_KEY
                               # y PUBLIC_BASE_URL=https://api.tudominio.com
nano Caddyfile                 # cambiá api.tudominio.com por tu dominio

# levantar todo (el servicio `migrate` corre las migraciones y recién ahí
# arrancan api/worker/scheduler)
docker compose -f docker-compose.prod.yml up -d --build
```

### Si el servidor ya tiene un reverse proxy

Con EasyPanel, Coolify o similar, los puertos 80/443 ya están ocupados y **no se
levanta un proxy propio**: la API se une a la red del proxy existente y declara
su ruta con labels (ver `docker-compose.prod.yml`). Solo hay que setear
`KORE_API_DOMAIN` y `PROXY_NETWORK` en el `.env`.

Comprobá que el proxy tomó la ruta:

```bash
# el proxy alcanza la API por la red interna
TRAEFIK=$(docker ps --format '{{.Names}}' | grep -i traefik | head -1)
docker exec "$TRAEFIK" wget -qO- http://kore-ai-backend-api-1:8000/health

# y desde afuera, con certificado
curl -s https://api.tudominio.com/health
```

El certificado tarda hasta ~1 min la primera vez. Verificá:
```bash
# 200 = API arriba y con Postgres + Redis sanos
curl -s https://api.tudominio.com/health/ready
```

> `/docs` (Swagger) está **apagado en producción**. Para prenderlo puntualmente:
> `KORE_DOCS_ENABLED=true` y reiniciá la API.

### Migraciones
El esquema lo maneja Alembic. El compose incluye un servicio `migrate` que corre
`alembic upgrade head` y termina; `api`, `worker` y `scheduler` esperan a que
salga con éxito, así nunca se sirve tráfico contra un esquema viejo.

```bash
# sembrar los nichos
docker compose -f docker-compose.prod.yml run --rm --entrypoint python api -m scripts.seed_niches

# migrar a mano tras un git pull con cambios de esquema
docker compose -f docker-compose.prod.yml run --rm migrate
```

> **`seed_niches` es idempotente y hay que volver a correrlo** cada vez que
> cambian las preguntas del Coach o sus ejemplos: hace *upsert* por slug y
> reemplaza la config del nicho. Sin eso, los clientes existentes siguen viendo
> la calibración vieja (las preguntas del onboarding salen de ahí).

> **Venís de una instalación vieja hecha con `scripts/init_db.py`?** No hay nada
> que hacer: la migración `0001_baseline` detecta las tablas existentes, no toca
> nada y deja la base registrada en el historial de Alembic.

---

## 2) Frontend en Vercel
1. Importá el repo `agent-inmobi-app` en Vercel.
2. Cargá las **Environment Variables** (ver `.env.example` del frontend):

| Variable | Valor |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | tu URL de Supabase |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | tu `sb_publishable_…` |
| `SUPABASE_SERVICE_ROLE_KEY` | tu `sb_secret_…` |
| `KORE_BACKEND_URL` | `https://api.tudominio.com/api/v1` |
| `KORE_PROVISIONING_SECRET` | **el mismo valor que en el `.env` del backend** |
| `KORE_DEFAULT_NICHE` | `real-estate` |
| `STRIPE_SECRET_KEY` / `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | si vas a cobrar |

3. Deploy. Te queda en `https://tu-app.vercel.app` (o tu dominio).

> Si `KORE_PROVISIONING_SECRET` no coincide entre ambos lados, el onboarding
> falla al crear el tenant con un 401. Es el error de configuración más común.

---

## 3) Supabase (auth)
En el dashboard de Supabase → **Authentication → URL Configuration**:
- **Site URL**: la URL del frontend (Vercel).
- **Redirect URLs**: agregá `https://tu-app.vercel.app/**`.

(La migración `0003` de las columnas `kore_*` ya está aplicada en tu proyecto.)

---

## 4) Conectar WhatsApp + probar
1. Entrá al frontend → logueate → **Integraciones**.
2. **Conectar WhatsApp** → escaneá el QR. El webhook se auto-configura hacia
   `https://api.tudominio.com/api/v1/webhooks/evolution/{tenant}?token=…`
   (usa `PUBLIC_BASE_URL` y el `WEBHOOK_TOKEN`).
3. Escribile al número desde otro teléfono → el agente responde.
4. El lead aparece en el **CRM** con su temperatura y datos.

---

## 5) Cobrar con Stripe
1. En el dashboard de Stripe creá el endpoint de webhook:
   `https://api.tudominio.com/api/v1/billing/webhooks/stripe`
   Eventos: `checkout.session.completed`, `invoice.paid`,
   `invoice.payment_failed`, `customer.subscription.deleted`.
2. Copiá el *signing secret* a `STRIPE_WEBHOOK_SECRET` en el `.env`.
3. **Importante**: al crear el customer o la checkout session, seteá
   `metadata.tenant_id` con el UUID del tenant. Sin eso el webhook no sabe a
   quién acreditar el pago y descarta el evento.
4. Alta del plan (operación de operador, no del cliente):

```bash
curl -X POST https://api.tudominio.com/api/v1/billing/admin/subscription \
  -H "x-admin-key: $KORE_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"<uuid>","plan":"real-estate-growth","setup_fee_cents":150000,"mrr_cents":50000}'
```

El primer pago cobrado marca el setup como pagado → cierra el deal → dispara el
Onboarding Agent. Para un cobro fuera de Stripe (transferencia, efectivo) está
`POST /billing/admin/setup/paid` con la misma llave.

---

## 6) Operar
```bash
# logs
docker compose -f docker-compose.prod.yml logs -f api worker

# actualizar a una nueva versión (migrate corre solo antes que la API)
git pull && docker compose -f docker-compose.prod.yml up -d --build

# estado de salud
curl -s https://api.tudominio.com/health/ready

# reiniciar un servicio
docker compose -f docker-compose.prod.yml restart api
```

### Frenar al agente (urgencias)

Dos niveles, del más chico al más grande. Los dos actúan en la capa de política,
así que cortan **todos** los caminos —WhatsApp, cadenas por evento y llamadas
manuales—, no solo el que se ve en pantalla.

**Una conversación puntual** — desde el CRM, abrí el contacto y tocá *Tomar
control*. El agente deja de responderle a esa persona por 24 h (vence solo, para
que un contacto no quede abandonado en silencio). Por API:

```bash
curl -X POST "$API/contacts/<contact_id>/pause?hours=24" -H "Authorization: Bearer $TENANT_KEY"
curl -X POST "$API/contacts/<contact_id>/resume"          -H "Authorization: Bearer $TENANT_KEY"
```

**Toda la cuenta de un cliente** — corta por lo sano si el sistema se está
portando mal con los clientes finales de alguien, sin apagar la plataforma
entera. Es operación de operador: el cliente no puede reactivarse solo.

```bash
curl -X POST "$API/tenants/admin/active" -H "x-admin-key: $KORE_ADMIN_API_KEY"   -H "Content-Type: application/json" -d '{"tenant_id":"<uuid>","is_active":false}'
```

Con la cuenta apagada, cada intento queda en el log como `cs.halted` y no se
gasta un token de LLM.

### Backups
El servicio `backup` del compose hace un `pg_dump` comprimido cada 24 h en
`./backups/`, con retención de 14 días (`BACKUP_RETENTION_DAYS`). Escribe a un
archivo temporal y recién al terminar lo renombra, así un corte a mitad de dump
no deja un `.sql.gz` truncado haciéndose pasar por backup válido.

```bash
ls -lh backups/                                   # verificar que corren
docker compose -f docker-compose.prod.yml logs backup

# restaurar
gunzip -c backups/kore_2026-07-26_0300.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U kore kore
```

> El backup vive en el **mismo disco** que la base. Si el VPS se pierde, se
> pierden los dos. Sincronizá `./backups/` a almacenamiento externo (S3, rclone,
> Backblaze) y **probá una restauración** antes de confiar en ellos.

---

## Checklist de seguridad

Ya resuelto en el código:
- [x] Webhooks (Evolution, Plaud, canales genéricos) exigen secreto compartido;
      sin secreto configurado responden 503 en vez de aceptar el payload.
- [x] `POST /tenants` cerrado con `KORE_PROVISIONING_SECRET`.
- [x] Rate limiting con Redis: global por IP, por tenant en `/agents/run` y en
      los webhooks. Techo mensual de tokens por tenant (`KORE_TOKEN_QUOTA_MONTHLY`).
- [x] Facturación separada del tenant: un cliente ya no puede marcarse pagado.
      Los eventos de Stripe se verifican por firma y se deduplican.
- [x] Credenciales de integraciones por tenant cifradas en reposo.
- [x] Swagger apagado y CORS cerrado en producción.
- [x] La app no arranca con secretos por default en producción.
- [x] Postgres/Redis/Evolution sin puertos públicos.
- [x] Backups automáticos con retención.

A cargo del operador:
- [ ] Secretos fuertes y distintos entre sí (`openssl rand -hex 32`).
- [ ] `KORE_TOKEN_QUOTA_MONTHLY` con un número real apenas tengas clientes.
- [ ] Copia de los backups **fuera del VPS**, y una restauración probada.
- [ ] Firewall: solo 22/80/443 abiertos.
- [ ] `SENTRY_DSN` configurado para enterarte de los errores sin leer logs.

Pendiente conocido:
- [ ] RLS de Postgres como segunda capa del aislamiento entre tenants (hoy el
      scoping es a nivel de aplicación, vía el ContextVar de tenant).
