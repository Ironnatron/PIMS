# PIMS feature and code guide

This guide explains what each current feature does and where to find its code.
It is for readers who are new to Django as well as developers maintaining PIMS.
For setup and deployment steps, see [README.md](README.md).

## 1. How a request moves through the application

When someone opens a page or submits a form, the usual path is:

1. **URL:** Django reads [config/urls.py](config/urls.py) and then
   [inventory/urls.py](inventory/urls.py) to find which code handles the address.
2. **View:** A view in [inventory/views.py](inventory/views.py) or
   [inventory/administration.py](inventory/administration.py) checks access and
   decides what to do.
3. **Form:** For submitted data, a form checks the values and reports errors.
   Inventory forms are in [inventory/forms.py](inventory/forms.py).
4. **Model:** A model in [inventory/models.py](inventory/models.py) describes how
   inventory information is stored in the database. Django's built-in models store
   users, groups and permissions.
5. **Template:** A template in [templates/](templates/) produces the HTML page.
   [templates/base.html](templates/base.html) provides the shared navigation and
   page layout.
6. **Response:** Django sends a page, a redirect or an error back to the browser.

An **ORM query** is Python code such as `Product.objects.filter(...)` that asks
Django to read or change database records. A **migration**, such as
[inventory/migrations/0001_initial.py](inventory/migrations/0001_initial.py),
describes database tables and constraints that Django creates with `migrate`.

### Example: adding a product

1. The browser requests `/products/add/`.
2. The URL named `product_add` selects `ProductCreateView`.
3. The view displays `ProductForm` using
   [templates/inventory/form.html](templates/inventory/form.html).
4. After the user submits it, the form validates and cleans the values.
5. Django saves a `Product` record and redirects to its detail page.
6. If validation fails, the same form is shown with error messages.

## 2. Sign in, sign out and access

**What it does:** Users sign in before accessing inventory. Only active staff can
use inventory screens; only active staff superusers can use the custom
administration screens.

**Code path:**

- [config/urls.py](config/urls.py) connects login, logout and password-change
  URLs to Django's built-in authentication views.
- [templates/registration/login.html](templates/registration/login.html) displays
  the sign-in form. Django checks the password and creates a login session.
- `StaffRequiredMixin` in [inventory/views.py](inventory/views.py) requires a
  login and checks the staff flag. Django's normal authentication backend excludes
  inactive users.
- `SuperuserRequiredMixin` in
  [inventory/administration.py](inventory/administration.py) checks the active,
  staff and superuser flags for custom administration.
- Logout uses a POST form in [templates/base.html](templates/base.html).
  Signed-in users can change their own password through Django's password-change
  views.

An unauthenticated user is redirected to login. A signed-in user without the
necessary access receives a **403 Forbidden** response.

## 3. Medicine and product management

**What it does:** Staff can add, edit, search, view and delete unused medicine
and other-product records. A product stores details such as SKU, name, generic
name, manufacturer, strength, dosage form, stock unit and reorder level.

**Code path:**

- `Product` in [inventory/models.py](inventory/models.py) defines the database
  fields. `kind` distinguishes medicine from another product.
- `ProductForm` in [inventory/forms.py](inventory/forms.py) defines the fields
  shown on the form. `clean_sku()` trims and uppercases the SKU and checks for
  a case-insensitive duplicate.
- `Product.clean()` checks that only medicines can be marked as requiring a
  prescription. It also prevents changing the stock unit once batches exist.
- `ProductListView`, `ProductDetailView`, `ProductCreateView`,
  `ProductUpdateView` and `ProductDeleteView` in
  [inventory/views.py](inventory/views.py) handle the screens.
- [product_list.html](templates/inventory/product_list.html) and
  [product_detail.html](templates/inventory/product_detail.html) display the
  catalog and a product's batches.

The database has a unique constraint on SKU. The form additionally checks
case-insensitively during normal form submissions. The prescription flag records
information; it does not implement prescription verification or dispensing.

## 4. Supplier management

**What it does:** Staff can manage supplier names, contacts, addresses, tax/GST
IDs, drug license numbers and active status.

**Code path:**

- `Supplier` in [inventory/models.py](inventory/models.py) defines the fields.
- `SupplierForm` in [inventory/forms.py](inventory/forms.py) prepares and validates
  the form, including Django's normal email validation.
- The `SupplierListView`, `SupplierDetailView`, `SupplierCreateView`,
  `SupplierUpdateView` and `SupplierDeleteView` classes in
  [inventory/views.py](inventory/views.py) handle the pages and submissions.
- [supplier_list.html](templates/inventory/supplier_list.html) shows the list;
  [supplier_detail.html](templates/inventory/supplier_detail.html) shows the
  supplier's batches.

An inactive supplier cannot be selected when creating a batch or receiving more
stock into an existing batch. A recorded license number is not automatically
verified.

## 5. Batches and expiry

**What it does:** Each batch links a product to a supplier and stores its batch
number, dates, physical quantity and purchase/selling price per stock unit.

**Code path:**

- `Batch` in [inventory/models.py](inventory/models.py) links to `Product` and
  `Supplier` using foreign keys. A product and batch-number pair must be unique.
- `BatchForm` in [inventory/forms.py](inventory/forms.py) allows only active
  products and suppliers for new batches. It checks that receipt is not in the
  future.
- `Batch.clean()` and database constraints check date relationships. The database
  also prevents negative quantities and prices.
- A new batch starts with quantity zero. After saving, `BatchCreateView` redirects
  to the stock-adjustment screen to record the receipt.
- `BatchForm` disables changes to product, supplier and batch number when editing
  an existing batch. Quantity is not editable on that form.
- `BatchListView` in [inventory/views.py](inventory/views.py) searches and
  filters batches; [batch_list.html](templates/inventory/batch_list.html) displays
  the results.

The expiry date is **inclusive**: a batch expiring today is not treated as expired
until the next day. Dates use the application's configured local timezone.
Batch lists show physical stock, including expired stock.

## 6. Stock adjustments and history

**What it does:** A user records a positive number to receive stock or a negative
number to remove stock, together with a reason. Every successful change records
the user, time and resulting balance.

**Code path:**

1. `BatchAdjustmentView` in [inventory/views.py](inventory/views.py) displays
   [adjustment.html](templates/inventory/adjustment.html).
2. `AdjustmentForm` in [inventory/forms.py](inventory/forms.py) checks the
   submitted number and reason.
3. The view calls `adjust_stock()` in [inventory/services.py](inventory/services.py).
4. The service checks that the change is nonzero, the reason is valid and the
   resulting quantity is within the allowed range. Positive changes are rejected
   for expired batches or inactive products/suppliers.
5. The service updates `Batch.quantity` and creates a `StockAdjustment` record
   from [inventory/models.py](inventory/models.py).
6. The page shows the current balance and the latest 50 adjustment records.

The service uses `transaction.atomic()` so the balance and history entry succeed
or fail together. It also uses `select_for_update()` to lock the batch while a
change is being made on PostgreSQL. SQLite local testing does not validate this
PostgreSQL locking behavior.

**Example:** A batch has 10 boxes. A `+5` adjustment with reason `Delivery` changes
the balance to 15 and records that result. A later `-2` adjustment records a balance
of 13. Attempting to remove more than 13 is rejected.

## 7. Dashboard, usable stock and alerts

**What it does:** The dashboard shows active product and supplier counts, a
low-stock watchlist, expiry alerts and recent stock adjustments.

**Code path:**

- `products_with_stock()` in [inventory/views.py](inventory/views.py) calculates
  each product's stock with `Sum`. It includes batches whose expiry date is today
  or later and whose supplier is active. `Coalesce` makes a missing total zero.
- `DashboardView` counts only active products for the product total and
  low-stock watchlist. A product is low when usable stock is **less than or equal
  to** its reorder level.
- An expiring batch has quantity greater than zero and an expiry date from today
  through the next 90 days, inclusive. An expired batch has quantity greater than
  zero and an expiry before today. These expiry alerts include stocked batches
  even when a product or supplier is inactive.
- The dashboard displays up to eight entries in each watchlist and the eight most
  recent adjustments. Links lead to the relevant filtered lists.
- [dashboard.html](templates/inventory/dashboard.html) displays the results.

For an inactive product, its detail page can still show the calculated stock
number, but the product is not on the active reorder watchlist and should not be
distributed.

## 8. Search, filters and pagination

**What it does:** Users can narrow lists instead of scrolling through all records.

**Code path:**

- List views read URL query parameters from `request.GET`.
- Product search checks name, SKU, generic name and manufacturer; filters include
  type, active status and low stock.
- Supplier search checks name, contact person, phone and email.
- Batch search checks batch number, product name/SKU and supplier name. Batch
  filters include usable, expiring and expired stock.
- Administration has search for users and groups.
- Each main list view uses `paginate_by = 20`. The shared
  [pagination.html](templates/inventory/pagination.html) changes the page number
  while retaining the other query parameters.

Search uses Django's `icontains` lookup for case-insensitive partial matching.

## 9. Deletion and history protection

**What it does:** Unused products and suppliers may be deleted. Records linked
to batches or stock history are protected so their history is not accidentally
removed.

**Code path:**

- `Batch.product` and `Batch.supplier` use `on_delete=models.PROTECT` in
  [inventory/models.py](inventory/models.py). `StockAdjustment` also protects
  its batch and user.
- `ProtectedDeleteView` in [inventory/views.py](inventory/views.py) catches the
  resulting `ProtectedError` and explains that the record should be made inactive.
- Deletion screens require a POST submission and display a confirmation first.
- The custom user-deletion screen similarly catches protected stock history.

Deactivation keeps the record and history. Batch deletion is not offered in the
normal inventory screens.

## 10. Administration: users, groups and permissions

**What it does:** Superusers use the separate Administration screen to create,
edit and delete users and groups, assign group or individual permissions, and
reset passwords. Django admin remains available as a fallback.

**Code path:**

- URLs beginning with `/administration/` in
  [inventory/urls.py](inventory/urls.py) select views in
  [inventory/administration.py](inventory/administration.py).
- `UserListView` and `GroupListView` list and search records.
- `ManagedUserCreationForm`, `ManagedUserChangeForm` and `ManagedGroupForm`
  validate user/group fields and selections. Django's `UserCreationForm` checks
  matching passwords and the configured password validators.
- Create/update views save changes. `UserPasswordView` uses Django's
  `SetPasswordForm`. Resetting a password invalidates the account's other sessions;
  a superuser resetting their own password keeps the current session.
- The custom user screens prevent deleting yourself or removing your own
  administrator access. The update/delete checks also protect the availability
  of an active staff superuser. Users referenced by stock history cannot be deleted.
- `record_admin_action()` records create, update, password-reset and delete events
  in Django's admin log. It does not record passwords.
- The screens are in
  [templates/inventory/administration/](templates/inventory/administration/).

**Important:** Every active staff member can currently manage all PIMS inventory,
regardless of group or individual permissions. Those permissions affect the
retained Django admin, not inventory screens. Custom administration requires
superuser status. The Django admin fallback is separate and can bypass the
custom screen's self-protection checks. Permissions that allow changing users or
groups in Django admin can grant powerful account-management access; assign them
only to trusted users.

## 11. Appearance and messages

**What it does:** The application provides a consistent layout, responsive pages,
validation errors and success/error messages.

**Code path:**

- [templates/base.html](templates/base.html) contains navigation, the main layout
  and Django's message display.
- [static/inventory/app.css](static/inventory/app.css) styles cards, tables, forms
  and mobile layouts.
- Django forms produce field and non-field errors. Views use
  `django.contrib.messages` to display success or failure after redirects.
- Templates use `{% csrf_token %}` in POST forms. Django's CSRF middleware checks
  the token before accepting those submissions.

## 12. Database, deployment and health check

**What it does:** The application can run locally for development or use
PostgreSQL and HTTPS settings when deployed.

**Code path:**

- [config/settings.py](config/settings.py) reads environment variables. With
  `DEBUG=True` and no `DATABASE_URL`, local development uses SQLite. Outside
  debug mode it requires a secret key and a PostgreSQL `DATABASE_URL`.
- The same settings configure trusted hosts/origins, secure cookies and HTTPS
  redirection. WhiteNoise serves collected static files.
- [render.yaml](render.yaml) describes a Render Free web service. Its build
  command installs dependencies and runs `collectstatic`; its start command runs
  migrations, optionally bootstraps an administrator, then starts Gunicorn.
- [bootstrap_admin.py](inventory/management/commands/bootstrap_admin.py) reads
  temporary `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables. It
  validates the password, creates the user if missing and never resets an
  existing account. Remove both variables after successful setup.
- The `health()` view in [inventory/views.py](inventory/views.py) runs `SELECT 1`
  against the database and returns `{"status": "ok"}` when it succeeds.

Render's web-service filesystem is temporary. Do not rely on its local SQLite
file for persistent inventory. Keep secrets out of source control and use a
separately managed PostgreSQL database with tested backups. See the deployment
section of [README.md](README.md) for details and free-tier limitations.

## 13. Tests

**What they do:** Automated tests check important behavior and help catch
regressions when code changes.

- [inventory/tests.py](inventory/tests.py) covers inventory access, record
  management, stock rules, expiry, pagination, CSRF and bootstrap behavior.
- [inventory/test_administration.py](inventory/test_administration.py) covers
  administration access, user/group management, passwords and protection rules.

Run them locally from PowerShell:

```powershell
$env:DEBUG = "True"
.\.venv\Scripts\python.exe manage.py test inventory
```

Tests use a separate test database. SQLite tests do not prove that simultaneous
stock adjustments are correctly locked on PostgreSQL; use a dedicated PostgreSQL
test database for production-equivalent database checks.

## 14. Features not implemented

Purchase/sales orders, invoicing, currency conversion, email password reset,
license verification, dispensing and regulatory-compliance workflows are not
implemented. Prices are stored as amounts without a currency field; use a
consistent currency. This application is not a validated regulatory system.
