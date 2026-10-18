# Backend

## SQLite database path

The SQLite database defaults to `backend/db.sqlite3`. Set `DB_NAME` to an
absolute file path to run the backend against a separate database, such as an
isolated development or test database.

## Local PostgreSQL database

Copy `.env.example` to `.env` in this directory and set the local PostgreSQL
password there. `.env` is ignored by Git. Django loads it at startup; PostgreSQL
uses `DB_ENGINE=postgresql`, with `DB_NAME=db_nexora`, `DB_USER=postgres`,
`DB_HOST=127.0.0.1`, and `DB_PORT=5432` as the defaults. Apply the schema with:

```powershell
python manage.py migrate
```

Changing `DB_ENGINE` does not copy the existing SQLite data. The SQLite file is
left intact, so data transfer to PostgreSQL must be performed separately.

Production startup requires `DJANGO_ENV=production`, a strong
`DJANGO_SECRET_KEY`, explicit `DJANGO_ALLOWED_HOSTS`, `DJANGO_DEBUG=false`, and
`DB_ENGINE=postgresql`. Django refuses to start in production with SQLite or
MySQL; this prevents a missing production database setting from silently
selecting the local SQLite database. Configure PostgreSQL credentials and
production security settings through the deployment environment, not this
example file. The secret key must contain at least 50 characters and five
distinct characters. Verify the target database and take a restorable backup
before running migrations; do not point a production deployment at a developer
database.

## Functional roles

The assignable roles are **Administrateur**, **Gestionnaire de stock**, and
**Vendeur**. The role migration maps old `manager` users to `stock`, preserves
their accounts and related history, and deactivates old `viewer` accounts.
Legacy consultation accounts must be explicitly assigned a functional role
before an administrator can reactivate them. Receipt and inventory validation,
direct stock movements, acquisition costs, and finance administration remain
restricted to administrators.

## Password reset email

In development (`DJANGO_DEBUG=true`), password-reset messages are written to the
backend console. For a deployed environment, provide these settings as process
environment variables:

| Variable | Purpose |
| --- | --- |
| `EMAIL_BACKEND` | Use `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` / `EMAIL_PORT` | SMTP server and port |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP credentials |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | Select the SMTP transport security mode |
| `DEFAULT_FROM_EMAIL` | Sender address displayed to recipients |
| `FRONTEND_BASE_URL` | Public frontend origin used in reset links |

`FRONTEND_BASE_URL` defaults to `http://localhost:5173`. Configure it to the
deployed frontend origin before sending real password-reset emails.

## Credit sales and customer payments

Each credit sale belongs to its customer and invoice. The credit list at
`GET /api/v1/payments/credits/` groups all credit sales by customer; its optional
`search` parameter accepts a customer name, phone number, or invoice number.
`GET /api/v1/payments/customer/<id>/credits/` returns the customer's invoices,
balances, and payment history.

Register a payment with `POST /api/v1/payments/`. If `sale` is specified, the
amount is applied only to that sale. Otherwise, the backend applies it to the
customer's oldest open credit invoices first and rejects amounts exceeding the
combined outstanding balance. Each allocation is stored separately and updates
the sale, invoice, credit ledger, and validated finance transaction in the same
database transaction.

The standard `POST /api/v1/sales/` endpoint also accepts an optional
`external_purchase` object on each sale line. This records the merchant, actual
unit cost, additional costs, delivery mode, and payment terms while keeping the
purchase linked to that sale line and invoice. A line with this object does not
consume internal stock; other catalogue lines in the same sale keep the normal
stock checks and movements. One-off lines without a catalogue product are
supported and do not create a permanent product or stock movement. The
`GET /api/v1/sales/external-suppliers/` endpoint returns only supplier IDs and
names to users authorized to create sales.

Immediate supplier terms make the payable due today but do not create a
treasury transaction. The actual payment is recorded later through the
supplier-payment workflow, where a grouped payment creates one validated
cash-flow transaction and allocations to the selected external purchases.

## Reporting and business intelligence

The existing Django reporting endpoints are shared by both frontends; they are
not a separate analytics data store. Reports are available under
`/api/v1/reports/` and `/api/core/reports/`:

| Endpoint | Access | Scope |
| --- | --- | --- |
| `reports/sales/` | Administrators and users with the sales permission | Sales, actual payments, products sold and time trends; sales-role users are always restricted to their own sales |
| `reports/inventory/` | Users with the inventory permission | StockItem balances, authorized locations, movements and sales-based rotation; acquisition costs are not returned |
| `reports/purchases/` | Users with the purchases permission | Purchase orders and received receipts, plus confirmed external purchases, paid amounts and supplier balances; cancelled purchases are excluded and external purchases are explicitly not counted as stock |
| `reports/credits/` | Users with the payments permission | Credit and customer sales report, subject to the sales-role own-sales restriction |
| `reports/finance/` | Users with the finance permission | Cashflow, customer credit balance and external supplier payables as separate values |

Sales reports accept `start_date`/`end_date` (also `date_from`/`date_to` or
`start`/`end`) and `period=day|week|month|quarter|year`. Inventory reports use
the same date filters for movement and rotation analysis; without an explicit
date range, `period_days` defaults to 90 and accepts values from 1 through 365.
`location` is applied only within the authenticated user's accessible
locations.

The finance report's cash inflows and outflows use the requested date range.
Its outstanding credit balance is a current snapshot of open credit sales, not
a historical balance for that date range; external supplier payables are also a
current snapshot, reduced only by validated supplier payments. Both amounts
remain separate from each other and from cash outflows, and the response
includes the snapshot date and scopes.

Rotation labels use explicit operational heuristics: at least one unit sold per
day is `fast`, a positive lower rate is `slow`, and no recorded sales is
`dormant`. Days of stock are current StockItem units divided by average daily
sales for the selected period. A reorder signal means stock is at or below the
configured alert threshold or estimated coverage is seven days or less; it is
an indicator, not a forecast. Sales without an assigned location and products
without a StockItem in the permitted scope are excluded from this analysis.
Returns are not separately modeled in this calculation.

Purchase reports use actual receipt item quantities and receipt-level
acquisition costs. Orders remain distinct from stock receipts. The application
does not yet persist purchase currency on orders or receipts, so cross-currency
supplier comparisons are unavailable and are identified as such in the
response. Historical profitability is likewise not presented as available
until per-sale acquisition cost is captured.

## Credit reminders and WhatsApp delivery

Credit reminders are grouped into one weekly message per customer and only
include partial credit sales with an outstanding balance. The default schedule
is Friday at 17:00 in `Africa/Conakry`; an administrator or manager can change
the enabled state, weekday, and time in **Paramètres → Notifications & rappels
de crédit**. Paid/cancelled sales and customers with no open balance are
excluded. A customer phone number is required when recording a credit sale.

The backend command below must be run by the host scheduler every five minutes.
It checks whether the configured weekly reminder time has passed, creates at
most one reminder per customer and ISO week, and sends due payment confirmations
and reminders. Failed sends are recorded with their error and attempt count and
retried with backoff (up to five attempts).

```powershell
Set-Location <backend-directory>
<python-executable> manage.py process_credit_notifications
```

For Windows deployments, create a Task Scheduler task that runs this command
every five minutes, with the backend directory as its working directory. Set
the task's overlap policy to **Do not start a new instance**. On Linux, the
equivalent cron entry is:

```cron
*/5 * * * * cd /path/to/backend && /path/to/venv/bin/python manage.py process_credit_notifications
```

Configure a real WhatsApp provider before enabling delivery. Store
`whatsapp_api_endpoint`, `whatsapp_api_key` and `whatsapp_sender_id` as
`AppSetting` records (the API key is sent as a Bearer token). Provider
configuration is not bundled with the application; until it exists, WhatsApp
notifications remain in retry/failed status and are never marked as sent.
Payment recording is independent of WhatsApp availability.
