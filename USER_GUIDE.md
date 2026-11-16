# PIMS user guide

PIMS helps pharmaceutical distributors keep a product catalog, supplier records,
batch details and stock-adjustment history in one place. This guide is for staff
using the application; for installation and deployment, see [README.md](README.md).

## Sign in and navigate

Sign in with the username and password provided by your administrator. Inventory
pages require an active staff account. The navigation menu provides:

- **Overview** — stock alerts and recent activity.
- **Medicines & products** — product catalog and usable stock.
- **Suppliers** — supplier contacts and supplied batches.
- **Batches & stock** — batch details, physical stock and adjustment history.
- **Administration** — user and group management (superusers only).

Use **Password** in the top bar to change your own password, and **Sign out** when
you are finished.

## Recommended setup

Set up the records in this order:

1. **Add a supplier.** Enter the supplier name and any available contact, address,
   tax/GST ID and drug-license details. The license number is stored as information;
   PIMS does not verify it.
2. **Add a product.** Enter a unique SKU and product name. For medicines, add
   details such as generic name, manufacturer, strength and dosage form as needed.
   Choose a stock-counting unit (for example, box, strip or bottle) and set a
   reorder level in that unit. Mark products inactive when they should no longer
   be distributed.
3. **Add a batch.** Select an active product and supplier, then enter the batch
   number, receipt date, expiry date and per-unit purchase and selling prices.
   Manufacture date is optional. A product cannot have two batches with the same
   batch number.
4. **Receive the stock.** Saving a new batch takes you to its stock-adjustment
   page. Record the received quantity as a positive adjustment and enter a clear
   reason, such as `Initial delivery`.

Use the same stock unit and currency consistently. Prices are stored per stock
unit, and PIMS does not convert currencies. A batch starts with zero quantity;
entering its details does not receive stock.

## Monitor stock

The **Overview** page summarizes active products and suppliers, products at or
below their reorder levels, batches expiring within 90 days and recent stock
activity. Follow a card or watchlist link to open the corresponding filtered list.
The expired-stock alert links to batches with remaining expired stock so you can
review and record its removal.

Use the search boxes and filters on product, supplier and batch lists to narrow
results. Lists are paginated; use the page links to move through results without
losing the selected filters.

Product and dashboard stock totals represent **usable stock**: they exclude expired
batches and batches from inactive suppliers. The reorder watchlist includes active
products only. Batch tables show **physical stock**, including expired stock, so
that it can be tracked and disposed of.

## Change stock and review history

Open **Batches & stock**, find the batch, and select **Adjust / history**. Enter:

- A nonzero quantity change in the product's stock unit. Use a positive number to
  receive stock or a negative number to remove it.
- A specific reason, such as `Supplier delivery`, `Damaged stock` or `Expiry
  disposal`.

Select **Record adjustment**. PIMS updates the batch balance and records the
change, resulting balance, reason, staff username and time. The page shows the
latest 50 adjustments for that batch. The Overview page also shows recent stock
activity.

You cannot reduce a batch below zero. Positive adjustments are not accepted for an
expired batch or one whose product or supplier is inactive. Expiry is inclusive:
a batch is usable through its expiry date and is treated as expired the following
day. Expired stock may be removed with a negative adjustment.

## Edit and retire records

Use **Edit** on a product, supplier or batch to update permitted details. Batch
product, supplier and batch number are fixed after creation, and quantity is
changed only through adjustments. A product's stock unit cannot be changed after
it has batches; create a new SKU if the pack/counting unit changes.

Products and suppliers with batch history cannot be deleted. Make them inactive
instead. Inactive products should not be distributed, and inactive suppliers
cannot be used for new batches or stock receipts. Batch deletion is not available
in the normal inventory screens. Records linked to stock history are retained to
preserve the audit trail.

## User and access administration

Only a superuser can open **Administration**. From **Users & access**, an
administrator can add or edit users, change account status, assign groups, reset
passwords and delete eligible accounts. Enable both **Active** and **Staff
status** for someone who needs PIMS inventory access. Grant **Superuser status**
only to trusted administrators.

All active staff members currently have full access to PIMS inventory screens.
Groups and individual permissions apply to Django admin, not to the inventory
screens. Superusers can also manage groups and their permissions from **Groups &
permissions**. Users referenced by stock history cannot be deleted; deactivate
them instead. The custom screen prevents deleting yourself or removing your own
administrator access.

Staff can change their own password using **Password** in the top bar. There is no
email-based password reset service; ask a superuser to reset the password if
needed. Share temporary passwords securely and have the user change the password
after signing in.

## Important limitations

PIMS is an inventory starter, not a validated regulatory or compliance system. It
does not verify supplier licenses, validate prescriptions, authorize dispensing,
or implement controlled-drug workflows. Purchase and sales orders, invoicing,
email password reset and currency conversion are not available. Follow applicable
local requirements and keep independent backups of the application database.
