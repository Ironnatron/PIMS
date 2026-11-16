# PIMS - Pharmaceutical Inventory Management

Django application for pharmaceutical distributors. Initial scope: medicine/product
management, suppliers, batches, expiry tracking and auditable stock adjustments.
Purchase/sales orders, invoicing, tax calculations and regulatory workflows are not
implemented in this release.

For a simple explanation of how each feature works in code, see
[FEATURE_CODE_GUIDE.md](FEATURE_CODE_GUIDE.md).
For day-to-day instructions for staff, see the [PIMS user guide](USER_GUIDE.md).

## Features

- Staff login; superusers manage accounts, groups and permissions in the PIMS
  Administration screen.
- Medicine and other-product catalog: SKU, generic name, manufacturer, strength,
  dosage form, counting unit, prescription flag and reorder level.
- Supplier contacts, address, tax/GST ID, drug license number and active status.
- Batch identity, supplier, receipt/manufacture/expiry dates, per-unit buy/sell prices.
  Use one consistent currency for all prices; this release does not convert currencies.
- Dashboard: low stock, 90-day expiry alerts, expired stock and recent adjustments.
- Search, filters and pagination; responsive UI without external CDN dependencies.
- Positive/negative stock adjustments with reason, actor, timestamp and resulting
  balance. PostgreSQL row locks serialize concurrent adjustments; changes and history
  commit together. Batches start at zero stock.
- Expired or inactive records cannot receive stock. Expired stock can be removed
  through a negative adjustment. Expiry is inclusive through the specified date.
- Usable product stock excludes expired batches and inactive suppliers. Only active
  products appear on the reorder watchlist. Batch tables show physical stock including
  unusable stock so that disposal can be tracked.
- Product/supplier records with batch history cannot be deleted. Deactivate them
  instead. Batch identity and quantity cannot be edited through the record form.
  Product counting units cannot change once batches exist; create a new SKU for a
  different pack size to preserve the meaning of the stock history.

This is an inventory starter, **not a validated regulatory/compliance system**.
It does not verify licenses, enforce controlled-drug regulations, or authorize
dispensing. Review applicable local requirements before business use.

## Local setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEBUG = "True"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Visit http://127.0.0.1:8000 and sign in with the account you created. Local development
uses SQLite. No demo accounts or preconfigured passwords are included.
Environment variables must be set in each new shell; `.env.example` is reference
only and is not automatically loaded.

### Load demonstration data

For a demo or an empty development database, run:

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo_data
```

The command prompts for and confirms a password for new accounts; newly created
demo accounts share it. Sign in as `demo_operator_1` or `demo_operator_2`. They are
active staff accounts with full inventory access, but are not administrators.
Choose a password that is not used elsewhere. The command is safe to rerun: it
does not reset existing demo passwords or overwrite existing demo records, and it
prints only a summary. Use this only in a demo/development database, not alongside
real inventory.

### First-use workflow

1. Add a supplier with its contact and license details.
2. Add a medicine/product. Choose a stock unit (e.g. strip, box, bottle) and use it
   consistently for quantities and per-unit prices.
3. Add a batch, then record a positive adjustment for the initial receipt.
4. Record negative adjustments for disposal, damage or returns with specific reasons.
5. Review the low-stock and expiry watchlists regularly.

Sign in as a superuser and select **Administration** in the sidebar. Create or edit
users, reset passwords, and create, edit or delete groups and their permissions.
Enable **Active** and **Staff status** for inventory access. Grant **Superuser
status** only to trusted administrators: superusers can manage every account and
group, including granting other users administrator access.

All active staff have full inventory-management access in this release, irrespective
of individual or group permissions. Those permissions control access in the retained
Django admin (`/admin/`); they do not restrict PIMS inventory screens or the custom
administration screen (which is superuser-only). Users with stock adjustment history
cannot be deleted; deactivate them instead. The custom screen prevents self-deletion
and removal of your own administrator access, and records administration changes in
the Django admin log. Django admin remains an independent fallback and can bypass
these custom-screen protections. Batch and adjustment admin screens are read-only.

Staff can change their own passwords; superusers can reset forgotten passwords in
Administration. Share temporary passwords securely. No email/password-reset service
is configured.

## Deploy on Render Free

As documented by Render, free web services spin down after 15 minutes idle, have an
ephemeral filesystem and are **not recommended for production applications**.
Free Render PostgreSQL expires after **30 days**. Never deploy this app with SQLite
on Render: inventory would be lost on restart/redeploy.

Use Render Free for evaluation with an external PostgreSQL provider (for example,
a currently available free Neon plan), or a paid persistent database for business
use. External providers have their own quotas, suspension and retention policies;
verify current terms and maintain independent backups.

### Prerequisites

1. Create a **private GitHub repository** for this project and push the source.
   Do not push `.venv`, `.env`, `db.sqlite3`, secrets or database backups.
2. Create an external PostgreSQL database. Get its SSL connection URL and store it
   privately. Never paste database credentials into chat or commit them.
3. Sign in to Render and authorize access to the repository.

### Blueprint deployment (recommended)

1. In Render, choose **New > Blueprint**, connect the repository and use `render.yaml`.
2. Confirm the web service plan is **Free**.
3. Enter the requested environment values directly in Render:
   - `DATABASE_URL`: external PostgreSQL URL with `?sslmode=require`.
   - `ADMIN_USERNAME`: the initial administrator username.
   - `ADMIN_PASSWORD`: a strong, unique temporary bootstrap password (at least
     eight characters, not common/numeric or similar to the username).
4. Apply the Blueprint. A secret key is generated automatically. Render's hostname
   automatically populates allowed hosts and CSRF trusted origins.
5. Wait for the build, migration and health check. Open the service URL and sign in.
6. **Remove `ADMIN_PASSWORD` and `ADMIN_USERNAME` from Render Environment settings
   immediately after the account is created.** Also remove their entries from
   `render.yaml` before a future Blueprint sync so it does not request them again.
   Change the initial password using the application's Password link.
7. Add suppliers/products and confirm an initial stock adjustment works.

The bootstrap command is idempotent: it never changes an existing account or password.
Render Free does not provide a service shell or pre-deploy commands, so migrations
and optional administrator bootstrap run in the start command before Gunicorn.
Use a single service instance for this setup. Do not share one database between
independently migrating deployments.

### Manual web-service deployment

Use these settings if you do not use the Blueprint:

| Setting | Value |
| --- | --- |
| Runtime | Python |
| Plan | Free |
| Build command | `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| Start command | `python manage.py migrate --noinput && python manage.py bootstrap_admin && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile -` |
| Health check | `/health/` |

Set `PYTHON_VERSION=3.12.8`, `DEBUG=False`, `DATABASE_URL`, `SECRET_KEY` (a long
random secret), and temporary `ADMIN_USERNAME`/`ADMIN_PASSWORD` directly in Render.
The `&&` syntax above is for Render's Linux runtime, not PowerShell.

For a custom domain also set `ALLOWED_HOSTS=inventory.example.com` and
`CSRF_TRUSTED_ORIGINS=https://inventory.example.com` (comma-separated for multiple
values). HTTPS redirection and secure cookies are enabled outside DEBUG.
`TIME_ZONE` defaults to `Asia/Kolkata`; change it to the distributor's local zone
before recording transactions. The database must be reachable from Render; use
the provider's supported SSL connection settings.

### Verification and troubleshooting

- `/health/` checks the database connection. Confirm it returns `{"status":"ok"}`.
- Login, add a supplier/product/batch, receive stock, then redeploy and verify the
  records remain. Test low-stock and expiry filters with representative records.
- An idle free service can take about a minute to wake up.
- Missing secret/database configuration fails startup explicitly; inspect Render logs.
- Database connection errors: check the URL, provider availability and network rules.
- Login CSRF errors on a custom domain: verify the HTTPS trusted origin.
- Invalid bootstrap password fails startup. Correct it in Render Environment settings;
  do not weaken password validation.
- Collect static files at build time; no local uploaded files are supported.
- Take regular provider-side PostgreSQL backups and test restoration. Application
  history is retained in the database, not in Render's ephemeral logs.

## Tests

```powershell
$env:DEBUG = "True"
.\.venv\Scripts\python.exe manage.py test inventory
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

For production-equivalent database testing, set `DATABASE_URL` to a **dedicated test
PostgreSQL database** whose user can create a test database, then run the same tests.
SQLite local tests do not validate PostgreSQL locking under concurrent requests.

## Deployment references

- [Render Django deployment](https://render.com/docs/deploy-django)
- [Render Free limitations](https://render.com/docs/free)
- [Neon plans](https://neon.com/pricing)
