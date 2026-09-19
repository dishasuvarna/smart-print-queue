# QueueDrop

A campus print-shop ordering and fulfillment platform. Students upload their own documents or order pre-approved lecturer handouts, pay online, and collect a printed copy using a pickup PIN. Professors submit handouts directly; the shop verifies and activates them before students can order. The shop manages the entire fulfillment queue — printing, batching, and marking orders complete — from a single dashboard.

**Live site:** https://smart-print-queue.onrender.com

---

## What it does

**For students**
- Upload a PDF directly, or browse/search shop-verified lecturer handouts by title, course, or lecturer name
- Choose copies, color mode (B&W / Full Color), and single- or double-sided printing
- Pay securely online (UPI, cards, netbanking, and more via Razorpay)
- Receive a pickup PIN and an email as soon as the order is ready for collection

**For professors**
- Submit a handout (file, title, course, semester, contact number, page count) directly through a dedicated login
- Freely edit the submission until the shop verifies and activates it
- Submissions are locked from further edits once live, preventing pricing or content changes mid-order

**For the shop**
- A live vendor dashboard shows all paid, unprinted orders — student uploads individually, handout orders automatically batched by title with combined copy counts
- One click opens a print-ready PDF, freshly stamped with the order number and pickup PIN on the first page — nothing is downloaded or stored locally
- Large handout batches split automatically into manageable print runs
- A persistent badge flags any handout awaiting verification
- Marking an order printed instantly notifies the student and clears completed files from storage

---

## How it works

| Layer | Technology | Role |
|---|---|---|
| Backend | Django | Core application, order logic, role-based admin |
| Background jobs | Celery + Redis (Upstash) | PDF validation, payment reconciliation, storage cleanup, notifications |
| Database | PostgreSQL (Supabase) | Orders, handouts, users |
| File storage | Supabase Storage | Uploaded PDFs and handouts, served independently of app restarts |
| Payments | Razorpay | Checkout, signature-verified webhooks, live settlement |
| Email | Brevo | Handout-verification and order-ready notifications |
| Hosting | Render | Web service, worker, and scheduler in one deployment |
| Uptime monitoring | UptimeRobot | Pings the live site every 5 minutes to prevent Render's free-tier instance from spinning down due to inactivity |

**Payment integrity:** every payment is confirmed server-to-server via a signature-verified Razorpay webhook — the checkout screen never determines order status on its own. Duplicate webhook deliveries are handled idempotently, and a scheduled reconciliation job catches any payment that succeeded without a webhook arriving.

**Storage lifecycle:** student-uploaded files are deleted the moment an order is printed, and again automatically if an order expires unpaid — keeping storage usage bounded over time. Handout files are shared across many orders and are retained until the shop removes them.

**Roles:** access is enforced at the account level — professors can submit and edit only their own handouts prior to verification; only the shop's account can activate a handout or access the fulfillment dashboard.

---

## Local development

```bash
cp .env.example .env
docker compose up -d          # Postgres + Redis for local development
python manage.py migrate
python manage.py runserver

# in separate terminals
celery -A config worker --loglevel=info --pool=solo
celery -A config beat --loglevel=info
```

## Environment variables

See `.env.example` for the full list, including database, Redis, Razorpay, Brevo, and Supabase Storage credentials.

## Deployment

Deployed on Render via `start.sh`, which runs the web server alongside the Celery worker and scheduler in a single service. Static and media files are served through WhiteNoise and Supabase Storage respectively.

Render's free tier spins the service down after periods of inactivity, which would otherwise cause a slow first response. To keep the app responsive, [UptimeRobot](https://uptimerobot.com) pings the live URL every 5 minutes, keeping the service continuously warm.

---

## Project structure

```
config/       Django settings, Celery app, URL routing
orders/       Order and Handout models, views, admin, background tasks, webhooks
notifications/  Email notifications via Brevo
```
