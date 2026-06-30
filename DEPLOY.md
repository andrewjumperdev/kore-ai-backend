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

---

## 1) Backend en el VPS

```bash
# instalar Docker
curl -fsSL https://get.docker.com | sh

# traer el código
git clone <TU_REPO> kore-ai-backend && cd kore-ai-backend

# configurar
cp .env.production.example .env
nano .env                      # completá OPENAI_API_KEY, KORE_SECRET_KEY, EVOLUTION_API_KEY,
                               # EVOLUTION_WEBHOOK_TOKEN y PUBLIC_BASE_URL=https://api.tudominio.com
nano Caddyfile                 # cambiá api.tudominio.com por tu dominio

# levantar todo
docker compose -f docker-compose.prod.yml up -d --build
```

Caddy saca el certificado HTTPS solo (puede tardar ~1 min). Verificá:
```bash
curl -s https://api.tudominio.com/docs -o /dev/null -w "%{http_code}\n"   # 200
```

### Inicializar la base (una sola vez)
Crea las tablas (incluye `prospects`, `tenant_integrations`, etc.) y siembra los nichos:
```bash
docker compose -f docker-compose.prod.yml run --rm --entrypoint python api -m scripts.init_db
docker compose -f docker-compose.prod.yml run --rm --entrypoint python api -m scripts.seed_niches
```

---

## 2) Frontend en Vercel
1. Importá el repo `agent-inmobi-app` en Vercel.
2. Cargá las **Environment Variables**:

| Variable | Valor |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | tu URL de Supabase |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | tu `sb_publishable_…` |
| `SUPABASE_SERVICE_ROLE_KEY` | tu `sb_secret_…` |
| `KORE_BACKEND_URL` | `https://api.tudominio.com/api/v1` |
| `KORE_DEFAULT_NICHE` | `real-estate` |
| `STRIPE_SECRET_KEY` / `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | si vas a cobrar |

3. Deploy. Te queda en `https://tu-app.vercel.app` (o tu dominio).

---

## 3) Supabase (auth)
En el dashboard de Supabase → **Authentication → URL Configuration**:
- **Site URL**: la URL del frontend (Vercel).
- **Redirect URLs**: agregá `https://tu-app.vercel.app/**`.

(La migración `0003` de las columnas `kore_*` ya está aplicada en tu proyecto.)

---

## 4) Conectar WhatsApp + probar
1. Entrá al frontend → logueate → **Integraciones**.
2. **Conectar WhatsApp** → escaneá el QR. (El webhook ya apunta solo a
   `https://api.tudominio.com/api/v1/webhooks/evolution/{tenant}` gracias a
   `PUBLIC_BASE_URL`.)
3. Escribile al número desde otro teléfono → el agente responde.
4. El lead aparece en el **CRM** con su temperatura y datos.

---

## 5) Operar
```bash
# logs
docker compose -f docker-compose.prod.yml logs -f api worker

# actualizar a una nueva versión
git pull && docker compose -f docker-compose.prod.yml up -d --build

# backup de Postgres (programalo en cron)
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U kore kore > backup_$(date +%F).sql

# reiniciar un servicio
docker compose -f docker-compose.prod.yml restart api
```

---

## Checklist de seguridad (recomendado)
- [ ] `KORE_SECRET_KEY` y `EVOLUTION_API_KEY` fuertes (`openssl rand -hex 32`).
- [ ] `EVOLUTION_WEBHOOK_TOKEN` seteado (asegura el webhook entrante).
- [ ] Postgres/Redis/Evolution **sin puertos públicos** (ya es así en el compose de prod).
- [ ] Backups de Postgres automáticos.
- [ ] Firewall: solo 22/80/443 abiertos.
- [ ] (Pendiente en el código, marcado) verificación de firma de webhooks de Stripe y RLS de Postgres como 2da capa.
