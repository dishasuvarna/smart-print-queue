# Smart print queue — infrastructure starter kit

A drop-in config layer implementing "identical behavior locally and in
production": environment-driven settings, Postgres everywhere (dev
included), Redis-backed Celery with automatic retries, a signature-verified
and idempotent payment webhook, upload validation, and structured logging.
Built to sit inside your existing Django project without restructuring it —
copy these files into matching folders (`config/`, `orders/`,
`notifications/`) and wire up your own models, views, and templates around
them.

## What's included, mapped to each requirement

| # | Requirement | Where it's implemented |
|---|---|---|
| 1 | Postgres locally and in production | `docker-compose.yml` (local) + `config/settings.py` reading `DATABASE_URL` |
| 2 | Upstash in prod, local/Docker Redis in dev, same Celery config | `docker-compose.yml` + `config/settings.py` + `config/celery.py`, all via `REDIS_URL` |
| 3 | All config in environment variables | `.env.example` — the only file that differs between environments |
| 4 | Same Celery tasks in both environments | `orders/tasks.py`, `notifications/tasks.py` — no environment branching anywhere |
| 5 | Razorpay test → live is a key swap only | `config/settings.py` reads `RAZORPAY_KEY_ID/SECRET` from env; no code path depends on which mode they're from |
| 6 | Brevo email, queued through Celery | `notifications/tasks.py` |
| 7 | Webhook signature verification | `orders/webhooks.py` |
| 8 | Idempotent webhook processing | `orders/webhooks.py` — status check before processing |
| 9 | Automatic retry for critical tasks | `autoretry_for` + `retry_backoff` on every task in `orders/tasks.py` and `notifications/tasks.py` |
| 10 | PDF validation (MIME, magic bytes, size, page count) | `orders/validators.py` |
| 11 | Logging per subsystem | Named loggers (`orders.payments`, `orders.queue`, `orders.pdf`, `notifications.email`) in `config/settings.py` |
| 12 | Secure production settings via `DEBUG` | `config/settings.py` — `if not DEBUG:` block |
| 13 | Identical Django/Celery/Redis/Gunicorn config | Everything above reads from env vars, nothing is duplicated per-environment |
| 14 | GitHub auto-deploy | Render default behavior — see deployment steps below |
| 15 | Combined process documented as a free-tier trade-off | `start.sh`, plus "Moving off the combined process" section below |

## Local development

```bash
cp .env.example .env
docker compose up -d              # starts local Postgres + Redis
python manage.py migrate
python manage.py runserver

# in a second terminal
celery -A config worker --loglevel=info

# in a third terminal (only needed to test scheduled tasks)
celery -A config beat --loglevel=info

# in a fourth terminal, to receive Razorpay test-mode webhooks locally
ngrok http 8000
# then register <ngrok-url>/orders/webhook/ in Razorpay's test dashboard
```

Because `DATABASE_URL` and `REDIS_URL` point at the Docker containers
above with the exact same variable names production uses, this is genuinely
the same code path you'll run after deployment — not a simplified stand-in
for it.

## Production deployment (Render)

1. Push to GitHub. Create a new Web Service in Render from the repo —
   auto-deploy on push is on by default, so every push to `main` redeploys
   without manual steps (point 14).
2. Set the Render **Start Command** to `bash start.sh`.
3. Add environment variables in Render's dashboard (values only — same
   names as `.env.example`):
   - `DEBUG=False`
   - `DATABASE_URL` — from Supabase (Project Settings → Database → Connection string)
   - `REDIS_URL` — from Upstash (use the `rediss://` TLS URL, not `redis://`)
   - `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
   - `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL`, `SHOPKEEPER_EMAIL`
   - `ALLOWED_HOSTS=yourapp.onrender.com`
4. Register your webhook URL in Razorpay's dashboard:
   `https://yourapp.onrender.com/orders/webhook/`
5. Deploy. `DEBUG=False` alone switches on `SECURE_SSL_REDIRECT`, secure
   cookies, and HSTS — there's no separate production settings file to
   maintain (point 12).

## Going from test to live payments later

Change three values in Render's environment variables —
`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` —
from `rzp_test_...` to `rzp_live_...` after completing Razorpay KYC.
No code changes (point 5).

## Moving off the combined free-tier process later

`start.sh` runs Gunicorn, the Celery worker, and Celery Beat in a single
process as a documented cost-saving trade-off for Render's free tier
(point 15). When you move to paid hosting — a Render Background Worker,
Railway, a VPS — split it into three services, each running one of these
commands, completely unchanged:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
celery -A config worker --loglevel=info
celery -A config beat --loglevel=info
```

Nothing in `config/`, `orders/`, or `notifications/` needs to change —
only how these three commands are distributed across processes.

## Not included here (add to your existing project)

This kit intentionally leaves out `models.py`, `views.py` for the order
flow, `urls.py`, and templates/frontend — those are specific to your
existing codebase and shouldn't be dictated by an infrastructure layer.
`orders/tasks.py` and `orders/webhooks.py` assume an `Order` model with at
minimum: `status`, `razorpay_order_id`, `pickup_pin`, `page_count`,
`copies`, `student_email`, and `created_at` fields — adjust field names to
match your own model.
